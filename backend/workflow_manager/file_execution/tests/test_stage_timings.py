"""WorkflowFileExecution.update_status timing behaviour (UN-3451).

Two things are proven here:

* ``execution_time`` passed by the worker is honoured. Before UN-3451 the
  argument was accepted and silently dropped, and every terminal update
  overwrote it with ``time_since(created_at)`` — which also counts the queue
  wait before a worker picked the file up, so every file over-reported.
* ``stage_timings`` is finalized on the way in: the queue wait the worker
  cannot measure is derived from ``created_at``, and the totals are restated
  against the persisted ``execution_time`` so the breakdown adds up to the
  duration the UI shows.

No database: ``save()`` is patched out, so these stay in the unit tier.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from unstract.core.stage_timings import WorkflowStage  # noqa: E402
from workflow_manager.file_execution.models import (  # noqa: E402
    WorkflowFileExecution,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus  # noqa: E402

CREATED_AT = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def _file_execution() -> WorkflowFileExecution:
    """An unsaved row with a fixed created_at, for arithmetic only."""
    fe = WorkflowFileExecution(file_name="invoice.pdf")
    fe.created_at = CREATED_AT
    return fe


def _worker_payload(started_offset: float = 4.0, **stages) -> dict:
    """A payload shaped like StageTimingCollector.to_dict()."""
    return {
        "version": 1,
        "started_at": (CREATED_AT + timedelta(seconds=started_offset)).timestamp(),
        "total": sum(stages.values()),
        "stages": dict(stages),
    }


class TestExecutionTimeIsHonoured:
    def test_worker_measurement_wins_over_time_since_created_at(self):
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(ExecutionStatus.COMPLETED, execution_time=12.5)

        assert fe.execution_time == 12.5

    def test_falls_back_to_time_since_created_at_when_not_supplied(self):
        """Terminal update with no measurement still records something."""
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            with patch(
                "workflow_manager.file_execution.models.CommonUtils.time_since",
                return_value=99.0,
            ):
                fe.update_status(ExecutionStatus.ERROR)

        assert fe.execution_time == 99.0

    def test_non_terminal_status_without_measurement_leaves_time_unset(self):
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(ExecutionStatus.EXECUTING)

        assert fe.execution_time is None

    def test_zero_is_a_measurement_not_a_missing_value(self):
        """A resumed/duplicate file legitimately reports 0.0."""
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            with patch(
                "workflow_manager.file_execution.models.CommonUtils.time_since",
                return_value=42.0,
            ):
                fe.update_status(ExecutionStatus.COMPLETED, execution_time=0.0)

        assert fe.execution_time == 0.0


class TestStageTimingsFinalization:
    def test_queue_wait_is_derived_from_created_at(self):
        fe = _file_execution()
        payload = _worker_payload(started_offset=4.0, tool_execution=10.0)

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=10.0,
                stage_timings=payload,
            )

        assert fe.stage_timings["stages"][WorkflowStage.QUEUE_WAIT] == 4.0
        # started_at is an implementation detail of the transport, not storage.
        assert "started_at" not in fe.stage_timings

    def test_total_is_the_whole_lifetime_not_just_processing(self):
        """``total`` = queue_wait + execution_time, because ``stages`` holds both.

        execution_time is processing only. Using it as the total would make the
        stage map sum to more than the total for any file that waited.
        """
        fe = _file_execution()
        payload = _worker_payload(
            started_offset=2.0, setup=0.5, tool_execution=9.0, destination=0.5
        )

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=10.0,
                stage_timings=payload,
            )

        timings = fe.stage_timings
        # queue_wait 2.0 + processing 10.0
        assert timings["total"] == 12.0
        # 12.0 - (2.0 + 0.5 + 9.0 + 0.5)
        assert timings["unaccounted"] == pytest.approx(0.0)
        assert fe.execution_time == 10.0

    def test_stages_never_sum_above_the_total(self):
        """The invariant every reader divides by. A queue wait used to break it."""
        fe = _file_execution()
        payload = _worker_payload(
            started_offset=30.0, setup=0.5, tool_execution=9.0, destination=0.5
        )

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=10.0,
                stage_timings=payload,
            )

        timings = fe.stage_timings
        assert sum(timings["stages"].values()) <= timings["total"]
        assert timings["stages"][WorkflowStage.QUEUE_WAIT] == 30.0
        assert timings["total"] == 40.0

    def test_unaccounted_never_negative(self):
        """Stages can outrun the total when spans overlap; don't report < 0."""
        fe = _file_execution()
        payload = _worker_payload(started_offset=1.0, tool_execution=50.0)

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=5.0,
                stage_timings=payload,
            )

        assert fe.stage_timings["unaccounted"] == 0.0

    def test_clock_skew_omits_queue_wait_rather_than_reporting_negative(self):
        fe = _file_execution()
        payload = _worker_payload(started_offset=-30.0, tool_execution=1.0)

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=1.0,
                stage_timings=payload,
            )

        assert WorkflowStage.QUEUE_WAIT not in fe.stage_timings["stages"]

    def test_tool_split_is_preserved(self):
        fe = _file_execution()
        payload = _worker_payload(started_offset=1.0, tool_execution=10.0)
        payload["tool_split"] = {"extraction": 6.0, "prompts": 4.0}

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=11.0,
                stage_timings=payload,
            )

        assert fe.stage_timings["tool_split"] == {"extraction": 6.0, "prompts": 4.0}

    def test_no_payload_leaves_field_untouched(self):
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(ExecutionStatus.COMPLETED, execution_time=1.0)

        assert fe.stage_timings is None

    def test_malformed_payload_is_stored_as_is_rather_than_raising(self):
        """Timing is diagnostic; a bad payload must not fail the status update."""
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=1.0,
                stage_timings={"stages": "not-a-dict"},
            )

        assert fe.status == ExecutionStatus.COMPLETED.value
        assert fe.stage_timings is not None

    @pytest.mark.parametrize("payload", [[1, 2], "nope", 7, True])
    def test_non_dict_payload_is_rejected_not_persisted(self, payload):
        """The field is a bare JSONField on the internal API; don't store junk."""
        fe = _file_execution()

        with patch.object(WorkflowFileExecution, "save"):
            fe.update_status(
                ExecutionStatus.COMPLETED,
                execution_time=1.0,
                stage_timings=payload,
            )

        assert fe.stage_timings is None
