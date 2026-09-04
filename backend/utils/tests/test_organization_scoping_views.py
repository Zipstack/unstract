"""``filter_queryset_by_organization`` driven through the viewsets that use it.

test_organization_scoping pins the helper against a synthetic request. That
proves the helper fails closed, not that the ~15 production call sites reach it
with the context it needs, nor that a viewset opting out of
``OrganizationFilterBackend`` with ``skip_org_filter = True`` has anything left
scoping it.

These two viewsets are chosen because between them they cover both shapes the
call sites take: ``get_queryset()`` (five of the six internal viewsets) and a
``get_object()`` that deliberately bypasses ``get_queryset()`` for single-object
lookups (only FileExecutionInternalViewSet).

``X-Organization-ID`` is what ``InternalAPIAuthMiddleware`` turns into
``request.organization_id``. The middleware warns and continues when the header
is absent, so "no organization_id attribute" is a reachable request state and is
tested as one.
"""

import secrets

import pytest
from account_v2.models import Organization
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from workflow_manager.file_execution.internal_views import FileExecutionInternalViewSet
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_ABSENT = object()


@pytest.mark.django_db
class InternalViewSetOrgScopingTest(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.a = self._org_with_execution("a")
        self.b = self._org_with_execution("b")

    def _org_with_execution(self, tag: str):
        slug = f"org-{tag}-{secrets.token_hex(3)}"
        org = Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )
        workflow = Workflow._base_manager.create(
            workflow_name=f"wf-{slug}", organization=org
        )
        execution = WorkflowExecution._base_manager.create(
            workflow=workflow, status=ExecutionStatus.COMPLETED.value
        )
        file_execution = WorkflowFileExecution._base_manager.create(
            workflow_execution=execution,
            file_name=f"{slug}.pdf",
            status=ExecutionStatus.COMPLETED.value,
        )
        return org, workflow, execution, file_execution

    def _get(self, path: str, organization_id=_ABSENT):
        request = self.factory.get(path)
        # Set exactly what the middleware sets. Absent is a distinct state from
        # present-and-None, and production reads it with getattr(..., None).
        if organization_id is not _ABSENT:
            request.organization_id = organization_id
        return request

    # --- get_queryset() path: five of the six internal viewsets -------------

    def _list_executions(self, organization_id=_ABSENT):
        view = WorkflowExecutionInternalViewSet.as_view({"get": "list"})
        return view(self._get("/internal/workflow-execution/", organization_id))

    def _execution_ids(self, response) -> set[str]:
        results = response.data
        if isinstance(results, dict):
            results = results.get("results", results.get("data", []))
        return {str(row["id"]) for row in results}

    def test_list_without_the_header_serves_no_rows(self):
        """The header is optional at the middleware, so this is reachable."""
        response = self._list_executions()
        assert response.status_code == 200, response.data
        assert self._execution_ids(response) == set()

    def test_list_with_an_unresolvable_org_serves_no_rows(self):
        response = self._list_executions("org-that-does-not-exist")
        assert response.status_code == 200, response.data
        assert self._execution_ids(response) == set()

    def test_list_serves_only_the_callers_own_org(self):
        _, _, execution_a, _ = self.a
        _, _, execution_b, _ = self.b

        response = self._list_executions(self.a[0].organization_id)

        assert response.status_code == 200, response.data
        ids = self._execution_ids(response)
        assert str(execution_a.id) in ids
        assert str(execution_b.id) not in ids

    # --- get_object() path: bypasses get_queryset(), scopes independently ---

    def _retrieve_file_execution(self, pk, organization_id=_ABSENT):
        view = FileExecutionInternalViewSet.as_view({"get": "retrieve"})
        request = self._get(f"/internal/file-execution/{pk}/", organization_id)
        return view(request, id=str(pk))

    def test_retrieve_without_the_header_is_refused(self):
        _, _, _, file_execution = self.a
        response = self._retrieve_file_execution(file_execution.id)
        assert response.status_code == 404, response.data

    def test_retrieve_of_another_orgs_pk_is_refused(self):
        """Org A's context against an org B id: the whole point of the helper."""
        _, _, _, file_execution_b = self.b

        response = self._retrieve_file_execution(
            file_execution_b.id, self.a[0].organization_id
        )

        assert response.status_code == 404, response.data

    def test_retrieve_of_own_row_still_works(self):
        """Without this, a viewset that refused everything would pass above."""
        _, _, _, file_execution_a = self.a

        response = self._retrieve_file_execution(
            file_execution_a.id, self.a[0].organization_id
        )

        assert response.status_code == 200, response.data
        assert str(response.data["id"]) == str(file_execution_a.id)
