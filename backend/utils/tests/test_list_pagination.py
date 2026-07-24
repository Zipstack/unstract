"""Pagination contract for the four shared list endpoints (UN-3770).

Workflows, Prompt Studio, adapters and connectors share one listing shape:
``for_user()`` sharing predicate -> ``.distinct()`` -> declarative ``ordering``
-> ``OptionalPagination``. These tests pin the three ways that combination can
silently serve wrong rows — non-deterministic page boundaries, duplicate rows
from the sharing predicate, and a search applied after the count.

DB-backed (Django ``TestCase``), so ``backend/conftest.py`` auto-marks these
``integration``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from typing import Any, NamedTuple

from adapter_processor_v2.views import AdapterInstanceViewSet
from connector_v2.views import ConnectorInstanceViewSet
from django.test import TestCase
from permissions.roles import ResourceRole
from permissions.tests.base import (
    CoOwnerOrgTestMixin,
    _build_adapter,
    _build_connector,
    _build_custom_tool,
    _build_workflow,
)
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from workflow_manager.workflow_v2.views import WorkflowViewSet


@lru_cache(maxsize=1)
def _live_llm_adapter_id() -> str:
    from unstract.sdk1.adapters.adapterkit import Adapterkit

    return next(
        a["id"] for a in Adapterkit().get_adapters_list() if a["adapter_type"] == "LLM"
    )


@lru_cache(maxsize=1)
def _live_connector_id() -> str:
    from unstract.connectors.connectorkit import Connectorkit

    return Connectorkit().get_connectors_list()[0]["id"]


def _prepare_adapter(obj: Any) -> None:
    """Make the row serialisable: real registry id, real encrypted metadata."""
    from cryptography.fernet import Fernet
    from django.conf import settings

    obj.adapter_id = _live_llm_adapter_id()
    fernet = Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))
    obj.adapter_metadata_b = fernet.encrypt(
        json.dumps({"model": "gpt-4o-mini"}).encode("utf-8")
    )


def _prepare_connector(obj: Any) -> None:
    obj.connector_id = _live_connector_id()


class ListEndpoint(NamedTuple):
    kind: str
    viewset: Any
    build: Any
    name_field: str
    # Adapter and connector rows are serialised against the live registry, so
    # the shared builders' placeholder ids error before paging is reached.
    prepare: Callable[[Any], None] | None = None


LIST_ENDPOINTS = [
    ListEndpoint("workflow", WorkflowViewSet, _build_workflow, "workflow_name"),
    ListEndpoint("custom_tool", PromptStudioCoreView, _build_custom_tool, "tool_name"),
    ListEndpoint(
        "adapter",
        AdapterInstanceViewSet,
        _build_adapter,
        "adapter_name",
        prepare=_prepare_adapter,
    ),
    ListEndpoint(
        "connector",
        ConnectorInstanceViewSet,
        _build_connector,
        "connector_name",
        prepare=_prepare_connector,
    ),
]


class ListPaginationContractTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.factory = APIRequestFactory()

    def _create(self, endpoint: ListEndpoint, name: str, owner=None) -> Any:
        """A resource named ``name``, owned (membership) by ``owner``."""
        owner = owner or self.owner
        obj = endpoint.build(self.org, owner)
        setattr(obj, endpoint.name_field, name)
        if endpoint.prepare:
            endpoint.prepare(obj)
        obj.save()
        obj.memberships.create(user=owner, role=ResourceRole.OWNER)
        return obj

    def _list(self, endpoint: ListEndpoint, user, **params: Any):
        view = endpoint.viewset.as_view({"get": "list"})
        request = self.factory.get("/x/", params)
        force_authenticate(request, user=user)
        response = view(request)
        assert response.status_code == status.HTTP_200_OK, response.data
        return response

    def _names(self, endpoint: ListEndpoint, rows) -> list[str]:
        return [row[endpoint.name_field] for row in rows]

    def test_pages_partition_the_result_set(self) -> None:
        """Page 2 must not repeat or drop rows from page 1.

        Without a deterministic ``ordering`` the two requests run independent
        queries, so rows can appear twice or vanish entirely between them.
        """
        for endpoint in LIST_ENDPOINTS:
            with self.subTest(kind=endpoint.kind):
                expected = {f"{endpoint.kind}-page-{i}" for i in range(5)}
                for name in sorted(expected):
                    self._create(endpoint, name)

                page1 = self._list(endpoint, self.owner, page=1, page_size=2)
                page2 = self._list(endpoint, self.owner, page=2, page_size=2)
                page3 = self._list(endpoint, self.owner, page=3, page_size=2)

                names1 = self._names(endpoint, page1.data["results"])
                names2 = self._names(endpoint, page2.data["results"])
                names3 = self._names(endpoint, page3.data["results"])

                assert page1.data["count"] == len(expected)
                assert not set(names1) & set(names2)
                assert set(names1) | set(names2) | set(names3) == expected

    def test_multi_predicate_share_yields_one_row(self) -> None:
        """A resource reachable by several sharing predicates lists once.

        ``for_user()`` ORs membership / org-share / group-share together; if any
        arm ever becomes a join instead of a PK subquery, the row duplicates and
        ``count`` overstates. Dedup is what ``.distinct()`` is there for.
        """
        for endpoint in LIST_ENDPOINTS:
            with self.subTest(kind=endpoint.kind):
                name = f"{endpoint.kind}-multi-share"
                obj = self._create(endpoint, name)
                # Reachable via membership AND org-share simultaneously.
                obj.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
                obj.shared_to_org = True
                obj.save()

                response = self._list(endpoint, self.viewer, page=1, page_size=10)

                assert self._names(endpoint, response.data["results"]).count(name) == 1
                assert response.data["count"] == 1

    def test_search_narrows_rows_and_count(self) -> None:
        """``?search=`` must filter before the count, not after paging."""
        for endpoint in LIST_ENDPOINTS:
            with self.subTest(kind=endpoint.kind):
                for i in range(3):
                    self._create(endpoint, f"{endpoint.kind}-alpha-{i}")
                for i in range(2):
                    self._create(endpoint, f"{endpoint.kind}-beta-{i}")

                response = self._list(
                    endpoint, self.owner, page=1, page_size=10, search="alpha"
                )

                names = self._names(endpoint, response.data["results"])
                assert response.data["count"] == 3
                assert all("alpha" in name for name in names)
