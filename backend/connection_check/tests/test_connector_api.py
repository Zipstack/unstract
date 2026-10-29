"""POST connector/{id}/test/ and the stored-status fields and filters on the
connector list and detail. The external system is mocked at the connector kit.
"""

from typing import Any
from unittest.mock import patch

from connector_auth_v2.models import ConnectorAuth
from connector_processor.views import ConnectorViewSet
from connector_v2.models import ConnectorInstance
from connector_v2.views import ConnectorInstanceViewSet
from rest_framework import status

from connection_check.constants import NOT_CONNECTED_REASON, ConnectionStatus
from connection_check.models import ConnectorTestResult
from connection_check.tests.base import ConnectionCheckTestBase, mock_connector_kit
from unstract.connectors.exceptions import ConnectorError


class ConnectorTestAndRecordTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.connector = self.make_connector("bucket")

    def _test(self, user: Any = None, connector: Any = None) -> Any:
        connector = connector or self.connector
        return self.call(
            ConnectorInstanceViewSet, "post", "test_and_record", user, pk=connector.pk
        )

    def _detail(self) -> dict[str, Any]:
        response = self.call(
            ConnectorInstanceViewSet, "get", "retrieve", pk=self.connector.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        data: dict[str, Any] = response.data
        return data

    def test_never_tested(self) -> None:
        detail = self._detail()

        self.assertEqual(detail["last_test_status"], "never_tested")
        self.assertIsNone(detail["last_tested_at"])
        self.assertIsNone(detail["last_failure_reason"])
        self.assertFalse(detail["tested_before_last_change"])

    def test_connected(self) -> None:
        with mock_connector_kit(True) as kit:
            response = self._test()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ConnectionStatus.CONNECTED)
        self.assertEqual(kit.call_args.args[1]["secret"], "s")
        detail = self._detail()
        self.assertEqual(detail["last_test_status"], ConnectionStatus.CONNECTED)
        self.assertEqual(detail["last_tested_at"], response.data["tested_at"])

    def test_failed_stores_the_text_the_old_endpoint_returns(self) -> None:
        error = ConnectorError("Access denied to bucket.", treat_as_user_message=True)
        with mock_connector_kit(error=error):
            old = self.call(
                ConnectorViewSet,
                "post",
                "test",
                data={
                    "connector_id": self.connector.connector_id,
                    "connector_metadata": self.connector.connector_metadata,
                },
            )
            response = self._test()

        self.assertEqual(old.status_code, status.HTTP_400_BAD_REQUEST)
        old_text = old.data["errors"][0]["detail"]
        self.assertEqual(old_text, "Access denied to bucket.")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ConnectionStatus.FAILED)
        self.assertEqual(response.data["failure_reason"], old_text)
        self.assertEqual(self._detail()["last_failure_reason"], old_text)

    def test_false_is_failed(self) -> None:
        with mock_connector_kit(False):
            response = self._test()

        self.assertEqual(response.data["status"], ConnectionStatus.FAILED)
        self.assertEqual(response.data["failure_reason"], NOT_CONNECTED_REASON)

    def test_edit_after_test_is_flagged(self) -> None:
        with mock_connector_kit(True):
            self._test()
        self.assertFalse(self._detail()["tested_before_last_change"])

        response = self.call(
            ConnectorInstanceViewSet,
            "patch",
            "partial_update",
            data={"connector_name": "renamed"},
            pk=self.connector.pk,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["tested_before_last_change"])
        self.assertTrue(self._detail()["tested_before_last_change"])

    def test_viewer_gets_403(self) -> None:
        ConnectorInstance.objects.filter(pk=self.connector.pk).update(
            shared_to_org=True
        )

        response = self._test(user=self.member)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ConnectorTestResult.objects.exists())

    def test_other_org_gets_404(self) -> None:
        self.use_org(self.other_org)

        response = self._test()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ConnectorListFilterTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        failed = self.make_connector("failed")
        connected = self.make_connector("connected")
        self.make_connector("untested")
        self.store_result(ConnectorTestResult, failed, ConnectionStatus.FAILED, "x")
        self.store_result(ConnectorTestResult, connected, ConnectionStatus.CONNECTED)

    def _names(self, query: str) -> set[str]:
        response = self.call(ConnectorInstanceViewSet, "get", "list", path=f"/{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["connector_name"] for row in self.rows(response)}

    def test_filters(self) -> None:
        self.assertEqual(self._names("?failing=true"), {"failed"})
        self.assertEqual(self._names("?last_test_status=connected"), {"connected"})
        self.assertEqual(self._names("?last_test_status=failed"), {"failed"})
        self.assertEqual(self._names("?last_test_status=never_tested"), {"untested"})

    def _page(self, query: str) -> Any:
        path = f"/?page=1&page_size=1{query}"
        return self.call(ConnectorInstanceViewSet, "get", "list", path=path).data

    def test_failing_count_ignores_the_status_filters(self) -> None:
        self.assertEqual(self._page("")["count"], 3)
        for query in ("", "&failing=true", "&last_test_status=connected"):
            self.assertEqual(self._page(query)["failing_count"], 1, query)

    def test_failing_count_follows_the_other_filters(self) -> None:
        self.assertEqual(self._page("&search=fail")["failing_count"], 1)
        self.assertEqual(self._page("&search=connected")["failing_count"], 0)


class ConnectorOAuthRefreshTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        tokens = {"access_token": "old", "refresh_token": "r"}
        self.auth = ConnectorAuth.objects.create(
            user=self.owner,
            provider="google-oauth2",
            uid="uid-1",
            extra_data={"provider": "google-oauth2", "uid": "uid-1", **tokens},
        )
        self.connector = self.make_connector("drive", connector_auth=self.auth)
        ConnectorInstance.objects.filter(pk=self.connector.pk).update(
            connector_metadata={**tokens, "site_url": "https://example.com"}
        )

    def _test_with_refresh(self, error: Exception | None = None) -> Any:
        def refresh(auth: ConnectorAuth, request: Any = None) -> Any:
            auth.extra_data = {**auth.extra_data, "access_token": "new"}
            if error:
                raise error
            return auth.extra_data, True

        with (
            patch.object(
                ConnectorAuth, "get_and_refresh_tokens", autospec=True, side_effect=refresh
            ),
            mock_connector_kit(True) as kit,
        ):
            response = self.call(
                ConnectorInstanceViewSet,
                "post",
                "test_and_record",
                pk=self.connector.pk,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return kit.call_args.args[1]

    def test_tokens_are_refreshed_before_the_test(self) -> None:
        credentials = self._test_with_refresh()

        self.assertEqual(credentials["access_token"], "new")
        self.assertEqual(credentials["site_url"], "https://example.com")

    def test_refresh_error_still_runs_the_test(self) -> None:
        with self.assertLogs("connector_processor", level="WARNING"):
            credentials = self._test_with_refresh(AttributeError("boom"))

        self.assertEqual(credentials["access_token"], "new")
        self.assertEqual(credentials["site_url"], "https://example.com")
