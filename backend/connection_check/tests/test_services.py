"""The recording service: outcome, reason, logging, overwrite order, deletion,
organization and start time."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from adapter_processor_v2.models import AdapterInstance
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from connection_check.constants import (
    MAX_FAILURE_REASON_LENGTH,
    NOT_CONNECTED_REASON,
    UNEXPECTED_FAILURE_REASON,
    ConnectionStatus,
)
from connection_check.models import AdapterTestResult, ConnectorTestResult
from connection_check.services import run_and_record
from connection_check.tests.base import ConnectionCheckTestBase


def _raise(exc: Exception) -> Any:
    def run() -> bool:
        raise exc

    return run


class RunAndRecordTests(ConnectionCheckTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.adapter = self.make_adapter("llm")

    def test_connected(self) -> None:
        result = run_and_record(AdapterTestResult, self.adapter, lambda: True)

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.status, ConnectionStatus.CONNECTED)
        self.assertIsNone(stored.failure_reason)
        self.assertEqual(stored.tested_at, result.tested_at)

    def test_api_error_stores_its_detail(self) -> None:
        run_and_record(
            AdapterTestResult, self.adapter, _raise(APIException("Bad API key."))
        )

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.status, ConnectionStatus.FAILED)
        self.assertEqual(stored.failure_reason, "Bad API key.")

    def test_server_error_is_logged_with_its_traceback(self) -> None:
        with self.assertLogs("connection_check.services", level="WARNING") as logs:
            run_and_record(
                AdapterTestResult, self.adapter, _raise(APIException("Key not found."))
            )

        self.assertIn("APIException, status 500", logs.records[0].getMessage())
        self.assertNotIn("Key not found.", logs.records[0].getMessage())
        self.assertIn("Key not found.", logs.output[0])
        self.assertTrue(logs.records[0].exc_info)

    def test_input_error_is_logged_without_a_traceback(self) -> None:
        with self.assertLogs("connection_check.services", level="WARNING") as logs:
            run_and_record(
                AdapterTestResult, self.adapter, _raise(ValidationError("Bad API key."))
            )

        self.assertIn("ValidationError, status 400", logs.output[0])
        self.assertNotIn("Bad API key.", logs.output[0])
        self.assertFalse(logs.records[0].exc_info)

    def test_nested_error_detail_is_flattened(self) -> None:
        exc = ValidationError({"adapter_metadata": ["Image output is not allowed."]})

        run_and_record(AdapterTestResult, self.adapter, _raise(exc))

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.failure_reason, "Image output is not allowed.")

    def test_false_is_failed(self) -> None:
        run_and_record(AdapterTestResult, self.adapter, lambda: False)

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.status, ConnectionStatus.FAILED)
        self.assertEqual(stored.failure_reason, NOT_CONNECTED_REASON)

    def test_unexpected_error_is_failed_and_logged(self) -> None:
        with self.assertLogs("connection_check.services", level="ERROR") as logs:
            run_and_record(
                AdapterTestResult, self.adapter, _raise(RuntimeError("secret detail"))
            )

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.status, ConnectionStatus.FAILED)
        self.assertEqual(stored.failure_reason, UNEXPECTED_FAILURE_REASON)
        self.assertIn("RuntimeError", "\n".join(logs.output))

    def test_reason_is_trimmed(self) -> None:
        run_and_record(AdapterTestResult, self.adapter, _raise(APIException("x" * 900)))

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(len(stored.failure_reason), MAX_FAILURE_REASON_LENGTH)

    def test_later_result_overwrites_earlier(self) -> None:
        run_and_record(AdapterTestResult, self.adapter, _raise(APIException("down")))
        later = run_and_record(AdapterTestResult, self.adapter, lambda: True)

        stored = AdapterTestResult.objects.filter(profile=self.adapter)
        self.assertEqual(stored.count(), 1)
        self.assertEqual(stored[0].status, ConnectionStatus.CONNECTED)
        self.assertEqual(stored[0].tested_at, later.tested_at)
        self.assertIsNone(stored[0].failure_reason)

    def test_storing_leaves_other_profiles_alone(self) -> None:
        other = self.make_adapter("other")
        run_and_record(AdapterTestResult, other, _raise(APIException("down")))

        run_and_record(AdapterTestResult, self.adapter, lambda: True)

        stored = AdapterTestResult.objects.get(profile=other)
        self.assertEqual(stored.status, ConnectionStatus.FAILED)
        self.assertEqual(stored.failure_reason, "down")

    def test_older_test_does_not_replace_a_newer_result(self) -> None:
        def older() -> bool:
            # A newer test starts and is stored while this one runs.
            run_and_record(AdapterTestResult, self.adapter, lambda: True)
            return False

        run_and_record(AdapterTestResult, self.adapter, older)

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(stored.status, ConnectionStatus.CONNECTED)

    def test_profile_deleted_during_the_test_is_not_found(self) -> None:
        # Foreign keys are checked at commit, which a TestCase never reaches.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        def run() -> bool:
            AdapterInstance.objects.filter(pk=self.adapter.pk).delete()
            return True

        with self.assertLogs("connection_check.services", "WARNING") as logs:
            with self.assertRaises(NotFound):
                run_and_record(AdapterTestResult, self.adapter, run)

        self.assertIn("deleted during its connection test", logs.output[0])

    def test_organization_comes_from_the_profile(self) -> None:
        connector = self.make_connector("bucket")
        self.use_org(self.other_org)

        run_and_record(ConnectorTestResult, connector, lambda: True)

        self.use_org(self.org)
        stored = ConnectorTestResult.objects.get(profile=connector)
        self.assertEqual(stored.organization_id, self.org.id)

    def test_tested_at_is_the_start_time(self) -> None:
        start = timezone.now()

        with patch("connection_check.services.timezone.now", return_value=start) as now:

            def run() -> bool:
                now.return_value = start + timedelta(minutes=1)
                return True

            result = run_and_record(AdapterTestResult, self.adapter, run)

        stored = AdapterTestResult.objects.get(profile=self.adapter)
        self.assertEqual(result.tested_at, start)
        self.assertEqual(stored.tested_at, start)
