"""An aborted run still finishes: skipped and failed batches count down, and the
callback keeps STOPPED, bills finished files and leaves the pipeline status and
notifications to the abort. A re-run ignores the stopped run's markers (UN-4318).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

import callback.tasks as cb
import pytest
from shared.clients.base_client import APIRequestError
from shared.clients.execution_client import ExecutionAPIClient
from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from shared.processing.filter_pipeline import ActiveFileFilter
from unstract.core.data_models import ExecutionStatus
from unstract.workflow_execution.enums import LogState

from file_processing.tasks import (
    _run_batch_stages,
    _run_stages_under_barrier,
    _terminal_skip_result,
    _TerminalExecutionSkip,
)
from queue_backend import pg_barrier
from queue_backend.pg_barrier import SKIPPED_TERMINAL_EXECUTION_KEY

STOPPED = ExecutionStatus.STOPPED.value
ERROR = ExecutionStatus.ERROR.value
COMPLETED = ExecutionStatus.COMPLETED.value
_TASKS = "file_processing.tasks"
_REFUSAL = {"status": "skipped", "reason": "already_final", "new_status": STOPPED}


def _batch_data() -> Any:
    def data(index: int) -> dict[str, str]:
        return {"file_name": f"f{index}.pdf", "provider_file_uuid": f"uuid-{index}"}

    return SimpleNamespace(
        files=[["f0.pdf", data(0)], ("f1.pdf", data(1)), data(2), {"file_name": "x"}],
        file_data=SimpleNamespace(organization_id="org-1", workflow_id="wf-1"),
    )


def _skip_batch(status: str) -> dict[str, Any]:
    with (
        mock.patch(f"{_TASKS}._validate_and_parse_batch_data", return_value=_batch_data()),
        mock.patch(
            f"{_TASKS}._setup_execution_context",
            side_effect=_TerminalExecutionSkip("exec-1", status),
        ),
    ):
        return _run_batch_stages({"any": "payload"}, "task-1")


def test_a_stopped_runs_skipped_batch_counts_down() -> None:
    result = _skip_batch(STOPPED)

    assert SKIPPED_TERMINAL_EXECUTION_KEY not in result
    assert result["failed_files"] == 4


@pytest.mark.parametrize("status", [ERROR, COMPLETED])
def test_other_terminal_statuses_keep_the_marker(status: str) -> None:
    assert _skip_batch(status)[SKIPPED_TERMINAL_EXECUTION_KEY] is True


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


_PAYLOAD = {
    "files": [["f0.pdf", {}], ["f1.pdf", {}]],
    "file_data": {"execution_id": "e", "organization_id": "org-1"},
}


def _failing_batch(status: Any) -> Any:
    client = mock.Mock()
    client.get_workflow_execution_status.side_effect = [status]
    return (
        mock.patch(f"{_TASKS}._run_batch_stages", side_effect=RuntimeError("boom")),
        mock.patch(f"{_TASKS}.create_api_client", return_value=client),
    )


def test_a_batch_failing_after_the_abort_counts_down() -> None:
    stages, client = _failing_batch(STOPPED)
    context: Any = {"execution_id": "e", "batch_index": 0, "callback_descriptor": {}}
    with (
        stages,
        client,
        mock.patch.object(pg_barrier, "claim_batch", return_value=True),
        mock.patch.object(pg_barrier, "_barrier_pg_decrement") as decrement,
        mock.patch.object(pg_barrier, "_abort_barrier_in_body") as abort,
    ):
        pg_barrier.run_batch_with_barrier(
            context, lambda: _run_stages_under_barrier(_PAYLOAD, "task-1")
        )

    assert decrement.call_args.args[0]["failed_files"] == 2
    assert SKIPPED_TERMINAL_EXECUTION_KEY not in decrement.call_args.args[0]
    abort.assert_not_called()


@pytest.mark.parametrize(
    "status", [ExecutionStatus.EXECUTING.value, APIRequestError("500")], ids=["up", "down"]
)
def test_a_batch_failing_in_a_live_run_still_raises(status: Any) -> None:
    stages, client = _failing_batch(status)
    with stages, client, pytest.raises(RuntimeError, match="boom"):
        _run_stages_under_barrier(_PAYLOAD, "task-1")


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


def test_an_abort_after_the_callbacks_fetch_is_reported_as_stopped() -> None:
    api_client = mock.Mock()
    api_client.update_workflow_execution_status.side_effect = [
        SimpleNamespace(data=_REFUSAL),
        SimpleNamespace(data={"status": "updated"}),
    ]

    result = cb._update_execution_status_unified(
        api_client, "e1", COMPLETED, {"total_files": 2, "successful_files": 2}, "org-1"
    )

    calls = api_client.update_workflow_execution_status.call_args_list
    assert [c.kwargs["status"] for c in calls] == [COMPLETED, STOPPED]
    assert calls[1].kwargs["successful_files"] == 2
    assert calls[1].kwargs["error_message"] is None
    assert result["final_status"] == STOPPED


def test_an_accepted_write_keeps_its_status() -> None:
    api_client = mock.Mock()
    api_client.update_workflow_execution_status.return_value = SimpleNamespace(
        data={"status": "updated"}
    )

    result = cb._update_execution_status_unified(api_client, "e1", COMPLETED, {}, "org-1")

    assert api_client.update_workflow_execution_status.call_count == 1
    assert result["final_status"] == COMPLETED


def test_the_client_keeps_the_body_of_a_refused_write() -> None:
    client = ExecutionAPIClient.__new__(ExecutionAPIClient)
    with mock.patch.object(client, "post", return_value=dict(_REFUSAL)):
        response = client.update_workflow_execution_status("e1", COMPLETED)

    assert response.success is True
    assert cb._stopped_meanwhile(response) is True


@pytest.mark.parametrize(("status", "calls"), [(STOPPED, 0), (COMPLETED, 1)])
def test_only_the_abort_writes_a_stopped_runs_pipeline_status(
    status: str, calls: int
) -> None:
    context = cb.CallbackContext()
    context.pipeline_id = "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90"
    context.execution_id = "e1"
    context.organization_id = "org-1"
    context.api_client = mock.Mock()
    with mock.patch.object(cb, "_update_pipeline_directly") as update:
        cb._handle_pipeline_updates_unified(context, status, is_api_deployment=False)

    assert update.call_count == calls


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
    if status == STOPPED:
        assert result["reason"] == "handled_by_abort"
    else:
        assert result["status"] == "completed"


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
    ("publish", "creator"),
    [
        (cb._publish_final_workflow_ui_logs, "create_for_general_workflow"),
        (cb._publish_final_workflow_ui_logs_api, "create_for_api_workflow"),
    ],
    ids=["general", "api"],
)
@pytest.mark.parametrize(("status", "stopped"), [(STOPPED, True), (COMPLETED, False)])
def test_both_callbacks_pass_the_stop_to_the_final_log(
    publish: Any, creator: str, status: str, stopped: bool
) -> None:
    context = cb.CallbackContext()
    context.execution_id = "e1"
    context.organization_id = "org-1"
    context.pipeline_id = "p1"
    context.api_client = mock.Mock()
    context.api_client.get_workflow_execution.return_value = SimpleNamespace(
        success=True, data={"aggregated_usage_cost": 0}
    )
    workflow_logger = mock.Mock()
    with mock.patch.object(
        cb.WorkerWorkflowLogger, creator, return_value=workflow_logger
    ):
        publish(context=context, aggregated_results={}, execution_status=status)

    final = workflow_logger.publish_final_workflow_logs
    assert final.call_args.kwargs["stopped"] is stopped


def _active_files(status: Any) -> tuple[set[str], Any]:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.side_effect = [status]
    api_client.check_files_active_processing.return_value = SimpleNamespace(
        success=True, data={}
    )
    cache = mock.Mock()
    cache.get.return_value = {"data": {"execution_id": "old-run"}}
    files = {
        "u1:/a": {"uuid": "u1", "path": "/a"},
        "u2:/b": {"uuid": "u2", "path": "/b"},
    }
    with mock.patch(
        "shared.processing.filter_pipeline.RedisCacheBackend", return_value=cache
    ):
        found = ActiveFileFilter()._check_active_files_batch(
            files, "wf-1", "new-run", api_client
        )
    return found, api_client


def test_a_rerun_ignores_a_stopped_runs_markers() -> None:
    found, api_client = _active_files(STOPPED)

    assert found == set()
    api_client.get_workflow_execution_status.assert_called_once_with("old-run")


@pytest.mark.parametrize(
    "status", [ExecutionStatus.EXECUTING.value, APIRequestError("404")], ids=["live", "down"]
)
def test_other_runs_markers_stay_in_force(status: Any) -> None:
    found, _ = _active_files(status)

    assert found == {"u1:/a", "u2:/b"}


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
