"""POST adapter/{id}/test/ and the stored-status fields and filters on the
adapter list and detail. Provider calls are mocked at the SDK boundary.
"""

from typing import Any
from unittest.mock import patch

from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet, AdapterViewSet
from rest_framework import status

from connection_check.constants import NOT_CONNECTED_REASON, ConnectionStatus
from connection_check.models import AdapterTestResult
from connection_check.tests.base import ConnectionCheckTestBase, mock_llm
from unstract.sdk1.exceptions import SdkError


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class AdapterTestAndRecordTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.adapter = self.make_adapter("llm")

    def _test(self, user: Any = None, adapter: Any = None) -> Any:
        adapter = adapter or self.adapter
        return self.call(
            AdapterInstanceViewSet, "post", "test_and_record", user, pk=adapter.pk
        )

    def _detail(self) -> dict[str, Any]:
        response = self.call(AdapterInstanceViewSet, "get", "retrieve", pk=self.adapter.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        data: dict[str, Any] = response.data
        return data

    def _list(self, query: str = "") -> Any:
        return self.call(AdapterInstanceViewSet, "get", "list", path=f"/{query}")

    def test_never_tested(self, _ctx: Any) -> None:
        detail = self._detail()

        self.assertEqual(detail["last_test_status"], "never_tested")
        self.assertIsNone(detail["last_tested_at"])
        self.assertIsNone(detail["last_failure_reason"])
        self.assertFalse(detail["tested_before_last_change"])

    def test_connected(self, _ctx: Any) -> None:
        with mock_llm(True) as llm:
            response = self._test()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ConnectionStatus.CONNECTED)
        self.assertIsNone(response.data["failure_reason"])
        # The stored metadata is tested, with the name and type added.
        metadata = llm.call_args.kwargs["adapter_metadata"]
        self.assertEqual(metadata["api_key"], "sk-test")
        self.assertEqual(metadata["adapter_name"], "llm")
        self.assertEqual(metadata["adapter_type"], "LLM")
        row = self.rows(self._list())[0]
        self.assertEqual(row["last_test_status"], ConnectionStatus.CONNECTED)
        self.assertEqual(row["last_tested_at"], response.data["tested_at"])
        self.assertFalse(row["tested_before_last_change"])

    def test_failed_stores_the_text_the_old_endpoint_returns(self, _ctx: Any) -> None:
        error = SdkError("Incorrect API key provided.", status_code=401)
        with mock_llm(error=error):
            old = self.call(
                AdapterViewSet,
                "post",
                "test",
                data={
                    "adapter_id": self.adapter.adapter_id,
                    "adapter_type": "LLM",
                    "adapter_metadata": {**self.adapter.metadata, "adapter_name": "llm"},
                },
            )
            response = self._test()

        self.assertEqual(old.status_code, status.HTTP_400_BAD_REQUEST)
        old_text = old.data["errors"][0]["detail"]
        self.assertEqual(old_text, "Error testing 'llm'. Incorrect API key provided.")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ConnectionStatus.FAILED)
        self.assertEqual(response.data["failure_reason"], old_text)
        detail = self._detail()
        self.assertEqual(detail["last_test_status"], ConnectionStatus.FAILED)
        self.assertEqual(detail["last_failure_reason"], old_text)

    def test_false_is_failed(self, _ctx: Any) -> None:
        with mock_llm(False):
            response = self._test()

        self.assertEqual(response.data["status"], ConnectionStatus.FAILED)
        self.assertEqual(response.data["failure_reason"], NOT_CONNECTED_REASON)

    def test_edit_after_test_is_flagged(self, _ctx: Any) -> None:
        with mock_llm(True):
            self._test()
        self.assertFalse(self._detail()["tested_before_last_change"])

        response = self.call(
            AdapterInstanceViewSet,
            "patch",
            "partial_update",
            data={"description": "edited"},
            pk=self.adapter.pk,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["tested_before_last_change"])
        self.assertTrue(self._detail()["tested_before_last_change"])

    def test_viewer_gets_403(self, _ctx: Any) -> None:
        AdapterInstance.objects.filter(pk=self.adapter.pk).update(shared_to_org=True)

        response = self._test(user=self.member)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(AdapterTestResult.objects.exists())

    def test_frictionless_adapter_gets_403(self, _ctx: Any) -> None:
        adapter = self.make_adapter("free", is_friction_less=True)

        response = self._test(adapter=adapter)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_org_gets_404(self, _ctx: Any) -> None:
        self.use_org(self.other_org)

        response = self._test()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.use_org(self.org)
        self.assertFalse(AdapterTestResult.objects.exists())


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class AdapterListFilterTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.failed = self.make_adapter("failed")
        self.connected = self.make_adapter("connected")
        self.untested = self.make_adapter("untested")
        self.store_result(AdapterTestResult, self.failed, ConnectionStatus.FAILED, "x")
        self.store_result(AdapterTestResult, self.connected, ConnectionStatus.CONNECTED)

    def _names(self, query: str) -> set[str]:
        response = self.call(AdapterInstanceViewSet, "get", "list", path=f"/{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["adapter_name"] for row in self.rows(response)}

    def test_failing_filter(self, _ctx: Any) -> None:
        self.assertEqual(self._names("?failing=true"), {"failed"})
        self.assertEqual(self._names("?failing=TRUE"), {"failed"})

    def test_last_test_status_filter(self, _ctx: Any) -> None:
        self.assertEqual(self._names("?last_test_status=connected"), {"connected"})
        self.assertEqual(self._names("?last_test_status=failed"), {"failed"})
        self.assertEqual(self._names("?last_test_status=never_tested"), {"untested"})

    def _page(self, query: str) -> Any:
        path = f"/?page=1&page_size=1{query}"
        return self.call(AdapterInstanceViewSet, "get", "list", path=path).data

    def test_failing_count_ignores_the_status_filters(self, _ctx: Any) -> None:
        self.assertEqual(self._page("")["count"], 3)
        self.assertEqual(list(self._page(""))[-1], "failing_count")
        for query in ("", "&failing=true", "&last_test_status=connected"):
            self.assertEqual(self._page(query)["failing_count"], 1, query)

    def test_failing_count_follows_the_other_filters(self, _ctx: Any) -> None:
        self.assertEqual(self._page("&search=fail")["failing_count"], 1)
        self.assertEqual(self._page("&search=connected")["failing_count"], 0)
