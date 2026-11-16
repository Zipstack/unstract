"""POST connector/{id}/test/ and the stored-status fields and filters on the
connector list and detail. The external system is mocked at the connector kit.
"""

from typing import Any
from unittest.mock import patch

from connector_auth_v2.models import ConnectorAuth
from connector_processor.views import ConnectorViewSet
from connector_v2.models import ConnectorInstance
from connector_v2.views import ConnectorInstanceViewSet
from django.utils import timezone
from rest_framework import status

from connection_check.constants import NOT_CONNECTED_REASON, ConnectionStatus
from connection_check.models import ConnectorTestResult
from connection_check.tests.base import ConnectionCheckTestBase, mock_connector_kit
from unstract.connectors.exceptions import ConnectorError


GOOGLE_DRIVE_ID = "gdrive|3ac4b966-9136-4261-944a-bdbfc51cd21c"
POSTGRESQL_ID = "postgresql|6db35f45-be11-4fd5-80c5-85c48183afbb"


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

    def test_edit_saved_while_loading_is_flagged(self) -> None:
        load = ConnectorInstanceViewSet.get_object

        def load_then_edit(view: Any) -> Any:
            connector = load(view)
            ConnectorInstance.objects.filter(pk=connector.pk).update(
                modified_at=timezone.now()
            )
            return connector

        with patch.object(ConnectorInstanceViewSet, "get_object", load_then_edit):
            with mock_connector_kit(True):
                self._test()

        self.assertTrue(self._detail()["tested_before_last_change"])


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
        self.assertEqual(self._names("?last_test_status=FAILED"), {"failed"})

    def test_status_filters_leave_other_actions_alone(self) -> None:
        connected = ConnectorInstance.objects.get(connector_name="connected")

        response = self.call(
            ConnectorInstanceViewSet,
            "get",
            "retrieve",
            path="/?failing=true",
            pk=connected.pk,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

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


class ConnectorStoredCredentialsTests(ConnectionCheckTestBase):
    def _test(self, connector: ConnectorInstance) -> Any:
        response = self.call(
            ConnectorInstanceViewSet, "post", "test_and_record", pk=connector.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def test_oauth_connector_tests_its_stored_tokens_without_a_refresh(self) -> None:
        login = {"provider": "google-oauth2", "uid": "uid-1", "access_token": "login"}
        auth = ConnectorAuth.objects.create(
            user=self.owner, provider="google-oauth2", uid="uid-1", extra_data=login
        )
        connector = self.make_connector("drive", connector_auth=auth)
        stored = {"access_token": "stored", "refresh_token": "stored-refresh"}
        ConnectorInstance.objects.filter(pk=connector.pk).update(
            connector_id=GOOGLE_DRIVE_ID, connector_metadata=stored
        )

        with (
            patch.object(ConnectorAuth, "get_and_refresh_tokens") as refresh,
            mock_connector_kit(True) as kit,
        ):
            self._test(connector)

        refresh.assert_not_called()
        self.assertEqual(kit.call_args.args[1], stored)

    def test_malformed_url_keeps_the_password_out_of_the_reason_and_the_log(
        self,
    ) -> None:
        connector = self.make_connector("db")
        for url, reason in (
            (
                "postgres:/alice:STANDINPW@db/prod",
                "Error while connecting to DB: The connection URL is not valid.",
            ),
            (
                "postgresql://alice:STANDINPW/STANDINPW@db/prod",
                "Error while connecting to DB: Could not connect. If the user name "
                "or password has special characters, percent-encode them.",
            ),
        ):
            with self.subTest(url=url):
                ConnectorInstance.objects.filter(pk=connector.pk).update(
                    connector_id=POSTGRESQL_ID,
                    connector_metadata={"connection_url": url},
                )
                connector.refresh_from_db()

                with self.assertLogs("connection_check.services", "WARNING") as logs:
                    response = self._test(connector)

                self.assertEqual(response.data["failure_reason"], reason)
                stored = ConnectorTestResult.objects.get(profile=connector)
                self.assertEqual(stored.failure_reason, reason)
                self.assertNotIn("STANDINPW", "\n".join(logs.output))
