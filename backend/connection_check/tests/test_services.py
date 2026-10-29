"""The recording service: outcome, reason, upsert, organization and start time."""

from typing import Any

from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

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
        run_and_record(AdapterTestResult, self.adapter, lambda: True)

        stored = AdapterTestResult.objects.filter(profile=self.adapter)
        self.assertEqual(stored.count(), 1)
        self.assertEqual(stored[0].status, ConnectionStatus.CONNECTED)
        self.assertIsNone(stored[0].failure_reason)

    def test_organization_comes_from_the_profile(self) -> None:
        connector = self.make_connector("bucket")
        self.use_org(self.other_org)

        run_and_record(ConnectorTestResult, connector, lambda: True)

        self.use_org(self.org)
        stored = ConnectorTestResult.objects.get(profile=connector)
        self.assertEqual(stored.organization_id, self.org.id)

    def test_tested_at_is_the_start_time(self) -> None:
        seen: dict[str, Any] = {}
        before = timezone.now()

        def run() -> bool:
            seen["during"] = timezone.now()
            return True

        result = run_and_record(AdapterTestResult, self.adapter, run)

        self.assertLessEqual(before, result.tested_at)
        self.assertLessEqual(result.tested_at, seen["during"])
