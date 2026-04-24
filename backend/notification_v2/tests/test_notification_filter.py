"""Unit tests for the ``notify_on`` dispatch partition on notifications.

Covers both dispatch paths that fan out to ``NotificationHelper.send_notification``:

* ``APINotification.send`` — keyed on ``ExecutionStatus`` (ERROR, COMPLETED, STOPPED)
* ``PipelineNotification.send`` — keyed on ``Pipeline.PipelineStatus``
  (FAILURE, SUCCESS, INPROGRESS)

Follows the repo convention (see ``usage_v2/tests/test_helper.py``) of stubbing
Django-heavy modules at import time so the tests run without a live DB.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Module-level stubs — must be installed BEFORE importing the modules under
# test so Django's ORM imports resolve to our MagicMock-backed fakes.
# ---------------------------------------------------------------------------


def _ensure_mod(name: str) -> types.ModuleType:
    """Force-install a fresh stub module in ``sys.modules``."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    # Only stub leaf modules that pull in Django ORM. Parent packages
    # (api_v2, pipeline_v2, notification_v2, workflow_manager*) load normally.

    exec_enums = _ensure_mod("workflow_manager.workflow_v2.enums")

    class _ExecStatusNS:
        class ERROR:
            value = "ERROR"

        class COMPLETED:
            value = "COMPLETED"

        class STOPPED:
            value = "STOPPED"

    exec_enums.ExecutionStatus = _ExecStatusNS  # type: ignore[attr-defined]

    exec_models = _ensure_mod("workflow_manager.workflow_v2.models.execution")
    exec_models.WorkflowExecution = MagicMock(name="WorkflowExecution")  # type: ignore[attr-defined]

    api_models = _ensure_mod("api_v2.models")
    api_models.APIDeployment = MagicMock(name="APIDeployment")  # type: ignore[attr-defined]

    # notification_v2.models.Notification with a patchable ``objects``.
    notif_models = _ensure_mod("notification_v2.models")

    class _FakeNotification:
        objects = MagicMock(name="Notification.objects")

    notif_models.Notification = _FakeNotification  # type: ignore[attr-defined]

    # notification_v2.helper.NotificationHelper
    notif_helper = _ensure_mod("notification_v2.helper")

    class _FakeHelper:
        send_notification = MagicMock(name="NotificationHelper.send_notification")

    notif_helper.NotificationHelper = _FakeHelper  # type: ignore[attr-defined]

    # pipeline_v2.dto.PipelineStatusPayload
    pipeline_dto = _ensure_mod("pipeline_v2.dto")
    pipeline_dto.PipelineStatusPayload = MagicMock(name="PipelineStatusPayload")  # type: ignore[attr-defined]

    # pipeline_v2.models.Pipeline with a PipelineStatus text-choices surface.
    pipeline_models = _ensure_mod("pipeline_v2.models")

    class _PipelineStatus:
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"
        INPROGRESS = "INPROGRESS"

    class _FakePipeline:
        PipelineStatus = _PipelineStatus

    pipeline_models.Pipeline = _FakePipeline  # type: ignore[attr-defined]


_install_stubs()


# Now safe to import the modules under test.
from api_v2 import notification as api_notification_mod  # noqa: E402
from notification_v2.enums import NotificationTrigger  # noqa: E402
from notification_v2.helper import NotificationHelper  # noqa: E402
from notification_v2.models import Notification  # noqa: E402
from pipeline_v2 import notification as pipeline_notification_mod  # noqa: E402
from pipeline_v2.models import Pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_queryset(notifications: list[MagicMock]) -> MagicMock:
    """Return a MagicMock that mimics the chained QuerySet surface we use.

    Supports:
        qs.filter(notify_on=<value>)   -> qs with matching rows
        qs.exclude(notify_on=<value>)  -> qs with non-matching rows
        qs.exists()                    -> bool based on contents
        iter(qs)                       -> notifications
    """
    qs = MagicMock(name="qs")
    qs.__iter__ = lambda self: iter(notifications)

    def _filter(**kwargs):
        if "notify_on" in kwargs:
            target = kwargs["notify_on"]
            kept = [n for n in notifications if n.notify_on == target]
            return _make_queryset(kept)
        return _make_queryset(notifications)

    def _exclude(**kwargs):
        if "notify_on" in kwargs:
            target = kwargs["notify_on"]
            kept = [n for n in notifications if n.notify_on != target]
            return _make_queryset(kept)
        return _make_queryset(notifications)

    qs.filter.side_effect = _filter
    qs.exclude.side_effect = _exclude
    qs.exists.return_value = bool(notifications)
    qs.count.return_value = len(notifications)
    return qs


def _make_notification(*, notify_on: str) -> MagicMock:
    n = MagicMock(name="Notification")
    n.notify_on = notify_on
    return n


# ---------------------------------------------------------------------------
# APINotification — 3 modes × 3 statuses
# ---------------------------------------------------------------------------


class TestAPINotificationFilter:
    def _setup(self, *, status: str, notifications: list[MagicMock]):
        Notification.objects.filter.reset_mock()
        Notification.objects.filter.side_effect = None
        Notification.objects.filter.return_value = _make_queryset(notifications)
        NotificationHelper.send_notification.reset_mock()

        api = MagicMock(name="APIDeployment")
        api.api_name = "test-api"
        api.id = "api-uuid"

        execution = MagicMock(name="WorkflowExecution")
        execution.status = status
        execution.id = "exec-uuid"
        execution.error_message = "boom" if status == "ERROR" else None

        return api_notification_mod.APINotification(api=api, workflow_execution=execution)

    # --- ALL: fires on every status ---
    def test_all_fires_on_completed(self):
        n = _make_notification(notify_on=NotificationTrigger.ALL.value)
        self._setup(status="COMPLETED", notifications=[n]).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_all_fires_on_error(self):
        n = _make_notification(notify_on=NotificationTrigger.ALL.value)
        self._setup(status="ERROR", notifications=[n]).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_all_fires_on_stopped(self):
        n = _make_notification(notify_on=NotificationTrigger.ALL.value)
        self._setup(status="STOPPED", notifications=[n]).send()
        assert NotificationHelper.send_notification.call_count == 1

    # --- FAILURES_ONLY: fires on ERROR only ---
    def test_failures_only_suppressed_on_completed(self):
        n = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        self._setup(status="COMPLETED", notifications=[n]).send()
        NotificationHelper.send_notification.assert_not_called()

    def test_failures_only_fires_on_error(self):
        n = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        self._setup(status="ERROR", notifications=[n]).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_failures_only_suppressed_on_stopped(self):
        n = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        self._setup(status="STOPPED", notifications=[n]).send()
        NotificationHelper.send_notification.assert_not_called()

    # --- SUCCESS_ONLY: fires on COMPLETED only ---
    def test_success_only_fires_on_completed(self):
        n = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        self._setup(status="COMPLETED", notifications=[n]).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_success_only_suppressed_on_error(self):
        n = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        self._setup(status="ERROR", notifications=[n]).send()
        NotificationHelper.send_notification.assert_not_called()

    def test_success_only_suppressed_on_stopped(self):
        n = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        self._setup(status="STOPPED", notifications=[n]).send()
        NotificationHelper.send_notification.assert_not_called()

    # --- Mixed partition on a COMPLETED run: ALL + SUCCESS_ONLY fire, FAILURES_ONLY doesn't ---
    def test_mixed_partition_on_completed(self):
        all_mode = _make_notification(notify_on=NotificationTrigger.ALL.value)
        failures_only = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        success_only = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        notifier = self._setup(
            status="COMPLETED", notifications=[all_mode, failures_only, success_only]
        )
        with patch.object(api_notification_mod, "PipelineStatusPayload") as payload_cls:
            payload_cls.return_value.to_dict.return_value = {}
            notifier.send()

        assert NotificationHelper.send_notification.call_count == 1
        kwargs = NotificationHelper.send_notification.call_args.kwargs
        dispatched = sorted(n.notify_on for n in kwargs["notifications"])
        assert dispatched == ["ALL", "SUCCESS_ONLY"]


# ---------------------------------------------------------------------------
# PipelineNotification — 3 modes × 3 statuses
# ---------------------------------------------------------------------------


class TestPipelineNotificationFilter:
    def _setup(self, *, last_run_status: str, notifications: list[MagicMock]):
        Notification.objects.filter.reset_mock()
        Notification.objects.filter.side_effect = None
        Notification.objects.filter.return_value = _make_queryset(notifications)
        NotificationHelper.send_notification.reset_mock()

        pipeline = MagicMock(name="Pipeline")
        pipeline.id = "pipeline-uuid"
        pipeline.pipeline_name = "test-pipeline"
        pipeline.pipeline_type = "ETL"
        pipeline.last_run_status = last_run_status

        return pipeline_notification_mod.PipelineNotification(
            pipeline=pipeline, execution_id="exec-uuid", error_message=None
        )

    # --- ALL ---
    def test_all_fires_on_success(self):
        n = _make_notification(notify_on=NotificationTrigger.ALL.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.SUCCESS, notifications=[n]
        ).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_all_fires_on_failure(self):
        n = _make_notification(notify_on=NotificationTrigger.ALL.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.FAILURE, notifications=[n]
        ).send()
        assert NotificationHelper.send_notification.call_count == 1

    # --- FAILURES_ONLY ---
    def test_failures_only_suppressed_on_success(self):
        n = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.SUCCESS, notifications=[n]
        ).send()
        NotificationHelper.send_notification.assert_not_called()

    def test_failures_only_fires_on_failure(self):
        n = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.FAILURE, notifications=[n]
        ).send()
        assert NotificationHelper.send_notification.call_count == 1

    # --- SUCCESS_ONLY ---
    def test_success_only_fires_on_success(self):
        n = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.SUCCESS, notifications=[n]
        ).send()
        assert NotificationHelper.send_notification.call_count == 1

    def test_success_only_suppressed_on_failure(self):
        n = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        self._setup(
            last_run_status=Pipeline.PipelineStatus.FAILURE, notifications=[n]
        ).send()
        NotificationHelper.send_notification.assert_not_called()

    # --- Mixed partition on a SUCCESS run ---
    def test_mixed_partition_on_success(self):
        all_mode = _make_notification(notify_on=NotificationTrigger.ALL.value)
        failures_only = _make_notification(notify_on=NotificationTrigger.FAILURES_ONLY.value)
        success_only = _make_notification(notify_on=NotificationTrigger.SUCCESS_ONLY.value)
        notifier = self._setup(
            last_run_status=Pipeline.PipelineStatus.SUCCESS,
            notifications=[all_mode, failures_only, success_only],
        )
        with patch.object(
            pipeline_notification_mod, "PipelineStatusPayload"
        ) as payload_cls:
            payload_cls.return_value.to_dict.return_value = {}
            notifier.send()

        assert NotificationHelper.send_notification.call_count == 1
        kwargs = NotificationHelper.send_notification.call_args.kwargs
        dispatched = sorted(n.notify_on for n in kwargs["notifications"])
        assert dispatched == ["ALL", "SUCCESS_ONLY"]
