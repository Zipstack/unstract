"""Existing endpoints keep their paths, params, response keys and behaviour:
the new keys only append, the old test endpoints store nothing, and list
queries do not grow with the row count.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.serializers import (
    AdapterInstanceSerializer,
    AdapterListSerializer,
)
from adapter_processor_v2.views import AdapterInstanceViewSet, AdapterViewSet
from connector_processor.views import ConnectorViewSet
from connector_v2.serializers import ConnectorInstanceSerializer
from connector_v2.views import ConnectorInstanceViewSet
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from workflow_manager.endpoint_v2.serializers import WorkflowEndpointSerializer

from connection_check.constants import ConnectionStatus
from connection_check.models import AdapterTestResult, ConnectorTestResult
from connection_check.tests.base import (
    NEW_KEYS,
    ConnectionCheckTestBase,
    mock_connector_kit,
    mock_llm,
)

# Keys the endpoints returned before this change, in order.
ADAPTER_LIST_KEYS = [
    "id",
    "adapter_id",
    "adapter_name",
    "adapter_type",
    "created_by",
    "created_at",
    "modified_at",
    "description",
    "is_friction_less",
    "is_available",
    "is_deprecated",
    "icon",
    "model",
    "created_by_email",
    "owner_emails",
    "is_owner",
    "co_owners_count",
]
ADAPTER_DETAIL_KEYS = [
    "id",
    "shared_groups",
    "created_at",
    "modified_at",
    "adapter_name",
    "adapter_id",
    "adapter_metadata",
    "adapter_type",
    "is_active",
    "shared_to_org",
    "is_friction_less",
    "is_usable",
    "is_available",
    "deprecation_metadata",
    "description",
    "organization",
    "created_by",
    "modified_by",
    "is_deprecated",
    "icon",
    "created_by_email",
]
CONNECTOR_KEYS = [
    "id",
    "connector_metadata",
    "icon",
    "created_by_email",
    "shared_groups",
    "created_at",
    "modified_at",
    "connector_name",
    "connector_id",
    "connector_version",
    "connector_mode",
    "shared_to_org",
    "organization",
    "created_by",
    "modified_by",
    "is_owner",
    "co_owners_count",
    "owner_emails",
]
PAGE_KEYS = ["count", "next", "previous", "results"]


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class UnchangedResponseTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.adapter = self.make_adapter("llm")
        self.connector = self.make_connector("bucket")
        self.store_result(AdapterTestResult, self.adapter, ConnectionStatus.FAILED, "x")
        self.context = {"request": SimpleNamespace(user=self.owner)}

    def _assert_appended(self, rep: Any, keys: list[str], before: Any) -> None:
        self.assertEqual(list(rep), keys + NEW_KEYS)
        self.assertEqual({key: rep[key] for key in keys}, dict(before))

    def test_adapter_list_and_detail_only_append(self, _ctx: Any) -> None:
        before_row = AdapterListSerializer(self.adapter, context=self.context).data
        before_detail = AdapterInstanceSerializer(self.adapter).data
        bare = self.call(AdapterInstanceViewSet, "get", "list")
        paged = self.call(AdapterInstanceViewSet, "get", "list", path="/?page=1")
        detail = self.call(AdapterInstanceViewSet, "get", "retrieve", pk=self.adapter.pk)

        self._assert_appended(bare.data[0], ADAPTER_LIST_KEYS, before_row)
        self._assert_appended(paged.data["results"][0], ADAPTER_LIST_KEYS, before_row)
        self.assertEqual(list(paged.data), PAGE_KEYS + ["failing_count"])
        self._assert_appended(detail.data, ADAPTER_DETAIL_KEYS, before_detail)

    def test_connector_list_and_detail_only_append(self, _ctx: Any) -> None:
        before = ConnectorInstanceSerializer(self.connector, context=self.context).data
        bare = self.call(ConnectorInstanceViewSet, "get", "list")
        paged = self.call(ConnectorInstanceViewSet, "get", "list", path="/?page=1")
        detail = self.call(
            ConnectorInstanceViewSet, "get", "retrieve", pk=self.connector.pk
        )

        self._assert_appended(bare.data[0], CONNECTOR_KEYS, before)
        self._assert_appended(paged.data["results"][0], CONNECTOR_KEYS, before)
        self.assertEqual(list(paged.data), PAGE_KEYS + ["failing_count"])
        self._assert_appended(detail.data, CONNECTOR_KEYS, before)

    def test_bare_list_and_ignored_filter_values(self, _ctx: Any) -> None:
        self.make_adapter("untested")
        for viewset in (AdapterInstanceViewSet, ConnectorInstanceViewSet):
            unfiltered = self.call(viewset, "get", "list").data
            self.assertIsInstance(unfiltered, list)
            for query in ("?failing=false", "?failing=yes", "?last_test_status=junk"):
                response = self.call(viewset, "get", "list", path=f"/{query}")
                self.assertEqual(response.data, unfiltered, query)

    def test_nested_and_shared_serializers_gain_nothing(self, _ctx: Any) -> None:
        nested = WorkflowEndpointSerializer().fields["connector_instance"]
        self.assertIs(type(nested), ConnectorInstanceSerializer)
        connector = ConnectorInstanceSerializer(self.connector, context=self.context)
        adapter_row = AdapterListSerializer(self.adapter, context=self.context)
        for data in (connector.data, adapter_row.data):
            self.assertFalse(set(NEW_KEYS) & set(data))


class OldTestEndpointsTests(ConnectionCheckTestBase):
    def test_adapter_test_endpoint_unchanged(self) -> None:
        adapter = self.make_adapter("llm")
        with mock_llm(True):
            response = self.call(
                AdapterViewSet,
                "post",
                "test",
                data={
                    "adapter_id": adapter.adapter_id,
                    "adapter_type": "LLM",
                    "adapter_metadata": {**adapter.metadata, "adapter_name": "llm"},
                },
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"is_valid": True})
        self.assertFalse(AdapterTestResult.objects.exists())

    def test_connector_test_endpoint_unchanged(self) -> None:
        connector = self.make_connector("bucket")
        with mock_connector_kit(True):
            response = self.call(
                ConnectorViewSet,
                "post",
                "test",
                data={
                    "connector_id": connector.connector_id,
                    "connector_metadata": connector.connector_metadata,
                },
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"is_valid": True})
        self.assertFalse(ConnectorTestResult.objects.exists())


class ListQueryCountTests(ConnectionCheckTestBase):
    """The result table is joined into the list query, never read per row.

    Total list queries are not flat on main (connector ``shared_groups`` is
    read per row), so this counts the queries that touch the result table.
    """

    def _result_queries(self, viewset: Any, path: str, table: str) -> int:
        with CaptureQueriesContext(connection) as queries:
            response = self.call(viewset, "get", "list", path=path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sqls = [query["sql"] for query in queries.captured_queries]
        self.assertFalse([sql for sql in sqls if f'FROM "{table}"' in sql])
        return sum(table in sql for sql in sqls)

    def _assert_flat(self, viewset: Any, make: Any, result_model: Any) -> None:
        table = result_model._meta.db_table
        self.store_result(result_model, make("p0"), ConnectionStatus.FAILED, "x")
        for rows in (1, 5):
            for index in range(1, rows):
                profile = make(f"p{index}")
                if index % 2:
                    self.store_result(result_model, profile, ConnectionStatus.CONNECTED)
            # One joined list query; a paged list adds the failing_count query.
            self.assertEqual(self._result_queries(viewset, "/", table), 1)
            self.assertEqual(self._result_queries(viewset, "/?page=1", table), 2)

    def test_adapter_list(self) -> None:
        self._assert_flat(AdapterInstanceViewSet, self.make_adapter, AdapterTestResult)

    def test_connector_list(self) -> None:
        self._assert_flat(
            ConnectorInstanceViewSet, self.make_connector, ConnectorTestResult
        )
