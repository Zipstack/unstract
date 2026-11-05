"""An aborted run still finishes: skipped batches count down, and the callback
keeps STOPPED, bills finished files and does not notify again (UN-4318).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

import callback.tasks as cb
import pytest
from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from unstract.core.data_models import ExecutionStatus
from unstract.workflow_execution.enums import LogState

from file_processing.tasks import (
    _run_batch_stages,
    _terminal_skip_result,
    _TerminalExecutionSkip,
)
from queue_backend import pg_barrier
from queue_backend.pg_barrier import SKIPPED_TERMINAL_EXECUTION_KEY

STOPPED = ExecutionStatus.STOPPED.value
ERROR = ExecutionStatus.ERROR.value
COMPLETED = ExecutionStatus.COMPLETED.value
_TASKS = "file_processing.tasks"
_CLEANUP = "shared.workflow.execution.active_file_manager.cleanup_active_file_cache"


def _batch_data() -> Any:
    def data(index: int) -> dict[str, str]:
        return {"file_name": f"f{index}.pdf", "provider_file_uuid": f"uuid-{index}"}

    return SimpleNamespace(
        files=[["f0.pdf", data(0)], ("f1.pdf", data(1)), data(2), {"file_name": "x"}],
        file_data=SimpleNamespace(organization_id="org-1", workflow_id="wf-1"),
    )


def _skip_batch(status: str) -> tuple[dict[str, Any], Any]:
    with (
        mock.patch(f"{_TASKS}._validate_and_parse_batch_data", return_value=_batch_data()),
        mock.patch(
            f"{_TASKS}._setup_execution_context",
            side_effect=_TerminalExecutionSkip("exec-1", status),
        ),
        mock.patch(_CLEANUP) as cleanup,
    ):
        return _run_batch_stages({"any": "payload"}, "task-1"), cleanup


def test_a_stopped_runs_skipped_batch_clears_its_markers_and_counts_down() -> None:
    result, cleanup = _skip_batch(STOPPED)

    assert SKIPPED_TERMINAL_EXECUTION_KEY not in result
    assert result["failed_files"] == 4
    cleanup.assert_called_once_with(
        provider_file_uuids=["uuid-0", "uuid-1", "uuid-2"],
        workflow_id="wf-1",
        logger_instance=mock.ANY,
    )


@pytest.mark.parametrize("status", [ERROR, COMPLETED])
def test_a_run_the_reaper_finished_keeps_the_marker(status: str) -> None:
    result, cleanup = _skip_batch(status)

    assert result[SKIPPED_TERMINAL_EXECUTION_KEY] is True
    cleanup.assert_not_called()


@pytest.mark.parametrize(("status", "decrements"), [(STOPPED, 1), (ERROR, 0)])
def test_only_a_stopped_runs_batch_decrements(status: str, decrements: int) -> None:
    result = _terminal_skip_result(_batch_data(), status)
    context: Any = {"execution_id": "e", "batch_index": 0, "callback_descriptor": {}}
    with (
        mock.patch.object(pg_barrier, "claim_batch", return_value=True),
        mock.patch.object(pg_barrier, "_barrier_pg_decrement") as decrement,
        mock.patch.object(pg_barrier, "_abort_barrier_in_body") as abort,
    ):
        pg_barrier.run_batch_with_barrier(context, lambda: result)

    assert decrement.call_count == decrements
    abort.assert_not_called()


def _status_for(run_status: str, successful: int, failed: int) -> str:
    counts = {
        "total_files": successful + failed,
        "successful_files": successful,
        "failed_files": failed,
        "total_files_processed": successful + failed,
    }
    with (
        mock.patch.object(cb, "aggregate_file_batch_results", return_value=counts),
        mock.patch.object(
            cb.WallClockTimeCalculator, "calculate_execution_time", return_value=1.0
        ),
    ):
        _, status, _ = cb._determine_execution_status_unified(
            file_batch_results=[],
            api_client=mock.Mock(),
            execution_id="e1",
            organization_id="org-1",
            execution_context={"execution": {"status": run_status}},
        )
    return status


@pytest.mark.parametrize(("successful", "failed"), [(1, 9), (0, 10), (10, 0)])
def test_a_stopped_run_stays_stopped_whatever_the_counts(
    successful: int, failed: int
) -> None:
    assert _status_for(STOPPED, successful, failed) == STOPPED


@pytest.mark.parametrize(
    ("successful", "failed", "expected"), [(1, 9, COMPLETED), (0, 10, ERROR)]
)
def test_a_running_run_is_still_judged_by_its_counts(
    successful: int, failed: int, expected: str
) -> None:
    executing = ExecutionStatus.EXECUTING.value
    assert _status_for(executing, successful, failed) == expected


def test_a_missing_context_is_judged_by_its_counts() -> None:
    assert cb._was_stopped(None) is False
    assert cb._was_stopped({}) is False


@pytest.mark.parametrize(("status", "calls"), [(STOPPED, 0), (COMPLETED, 1)])
def test_a_stopped_run_is_not_notified_twice(status: str, calls: int) -> None:
    with mock.patch.object(cb, "handle_status_notifications") as notify:
        result = cb._handle_notifications_unified(
            api_client=mock.Mock(),
            status=status,
            organization_id="org-1",
            execution_id="e1",
            pipeline_id="p1",
        )

    assert notify.call_count == calls
    assert result["status"] == ("skipped" if status == STOPPED else "completed")


@pytest.mark.parametrize(("status", "commits"), [(STOPPED, 1), (ERROR, 0)])
def test_a_stopped_run_bills_only_its_finished_files(status: str, commits: int) -> None:
    context = cb.CallbackContext()
    context.execution_id = "e1"
    context.organization_id = "org-1"
    context.file_executions = [
        {"id": "done", "status": COMPLETED},
        {"id": "unfinished", "status": STOPPED},
    ]
    plugin = mock.MagicMock()
    with mock.patch("client_plugin_registry.get_client_plugin", return_value=plugin):
        cb._track_subscription_usage_if_available(context, status)

    commit = plugin.commit_batch_subscription_usage
    assert commit.call_count == commits
    if commits:
        assert commit.call_args.kwargs["file_execution_ids"] == ["done"]


@pytest.mark.parametrize(
    ("stopped", "state", "message"),
    [
        (True, LogState.ERROR, "Execution stopped"),
        (False, LogState.SUCCESS, "Executed successfully"),
    ],
)
def test_the_final_log_tells_a_stopped_run_apart(
    stopped: bool, state: LogState, message: str
) -> None:
    workflow_logger = WorkerWorkflowLogger.__new__(WorkerWorkflowLogger)
    with (
        mock.patch.object(workflow_logger, "publish_update_log") as update,
        mock.patch.object(workflow_logger, "publish_log"),
    ):
        workflow_logger.publish_final_workflow_logs(3, 1, 2, stopped=stopped)

    assert mock.call(state, message, mock.ANY) in update.call_args_list
