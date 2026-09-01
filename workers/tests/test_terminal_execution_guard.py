"""Validate-first terminal guard on the file-processing batch path.

A batch delivered for an execution that is already terminal (COMPLETED/ERROR/
STOPPED) must be skipped, not reprocessed — otherwise a stale/redelivered batch
arriving after the reaper recovered the execution resurrects it to EXECUTING and
re-runs its files (double LLM / destination write). These tests pin:
  * the guard fires for terminal statuses (PG) and is a no-op on Celery,
  * the guard runs at its real call site, before the EXECUTING status write,
  * a terminal batch is skipped WITHOUT pre-create / processing,
  * the skip result counts skipped files as failed and carries the bypass marker,
  * run_batch_with_barrier bypasses the barrier decrement on a marked result.
"""

from __future__ import annotations

import types
from unittest import mock

import pytest
from unstract.core.data_models import ExecutionStatus

from queue_backend.pg_barrier import SKIPPED_TERMINAL_EXECUTION_KEY

from file_processing.tasks import (
    _raise_if_execution_terminal,
    _run_batch_stages,
    _setup_execution_context,
    _terminal_skip_result,
    _TerminalExecutionSkip,
)

TERMINAL = [
    ExecutionStatus.COMPLETED.value,
    ExecutionStatus.ERROR.value,
    ExecutionStatus.STOPPED.value,
]
ACTIVE = [ExecutionStatus.PENDING.value, ExecutionStatus.EXECUTING.value]


@pytest.mark.parametrize("status", TERMINAL)
def test_guard_raises_for_terminal_on_pg(status):
    with pytest.raises(_TerminalExecutionSkip) as exc:
        _raise_if_execution_terminal({"status": status}, "exec-1", is_pg=True)
    assert exc.value.execution_id == "exec-1"
    assert exc.value.status == status


@pytest.mark.parametrize("status", ACTIVE)
def test_guard_passes_for_active_on_pg(status):
    # Must NOT raise for PENDING/EXECUTING.
    _raise_if_execution_terminal({"status": status}, "exec-1", is_pg=True)


@pytest.mark.parametrize("status", TERMINAL)
def test_guard_is_noop_on_celery_path(status):
    # is_pg=False (Celery) → NEVER raises, even for terminal statuses. This is
    # what keeps the Celery flow behaviorally unchanged.
    _raise_if_execution_terminal({"status": status}, "exec-1", is_pg=False)


def test_missing_status_on_pg_warns_and_proceeds():
    # A missing status is fail-open (no raise) but surfaced as a warning, since
    # it signals a degraded execution-fetch response rather than an active run.
    with mock.patch("file_processing.tasks.logger") as log:
        _raise_if_execution_terminal({}, "exec-1", is_pg=True)
    log.warning.assert_called_once()


def test_guard_fires_at_real_call_site_before_status_write():
    """Exercises the real wiring the mocked-setup tests skip: the is_pg forward
    chain and the guard's placement in _setup_execution_context — after the
    execution fetch, before the EXECUTING status write."""
    api_client = mock.Mock()
    api_client.get_workflow_execution.return_value = types.SimpleNamespace(
        success=True, data={"execution": {"status": ExecutionStatus.ERROR.value}}
    )
    file_data = mock.Mock(
        execution_id="exec-9", workflow_id="wf-1", organization_id="org-1"
    )
    batch_data = mock.Mock(files=[mock.Mock()], file_data=file_data)

    with (
        mock.patch("file_processing.tasks.StateStore"),
        mock.patch("file_processing.tasks.create_api_client", return_value=api_client),
        mock.patch("file_processing.tasks.create_organization_context"),
        pytest.raises(_TerminalExecutionSkip),
    ):
        _setup_execution_context(batch_data, "task-1", is_pg=True)

    # The guard fired BEFORE the EXECUTING status write.
    api_client.update_workflow_execution_status.assert_not_called()


def _fake_batch_data(n_files: int = 3, org: str = "org-1"):
    """A FileBatchData stand-in: real list for len(), mock file_data for org."""
    file_data = mock.Mock()
    file_data.organization_id = org
    return mock.Mock(files=[mock.Mock() for _ in range(n_files)], file_data=file_data)


def test_terminal_skip_result_counts_and_marker():
    result = _terminal_skip_result(_fake_batch_data(n_files=4, org="org-9"))
    assert result["total_files"] == 4
    assert result["successful_files"] == 0
    # Skipped files count as failed, not left unaccounted → in-progress
    # (total - successful - failed) is 0, and they don't silently vanish.
    assert result["failed_files"] == 4
    # Marker tells run_batch_with_barrier to bypass the (already-gone) decrement.
    assert result[SKIPPED_TERMINAL_EXECUTION_KEY] is True


def test_run_batch_stages_skips_terminal_without_processing():
    """Terminal execution → skip result (failed=N + marker), NO pre-create / processing."""
    bd = _fake_batch_data(n_files=2, org="org-2")
    with (
        mock.patch(
            "file_processing.tasks._validate_and_parse_batch_data", return_value=bd
        ),
        mock.patch(
            "file_processing.tasks._setup_execution_context",
            side_effect=_TerminalExecutionSkip("exec-2", "ERROR"),
        ),
        mock.patch(
            "file_processing.tasks._refactored_pre_create_file_executions"
        ) as pre_create,
        mock.patch(
            "file_processing.tasks._process_individual_files"
        ) as process_files,
    ):
        result = _run_batch_stages({"any": "payload"}, "task-1", is_pg=True)

    pre_create.assert_not_called()
    process_files.assert_not_called()
    assert result["total_files"] == 2
    assert result["successful_files"] == 0
    assert result["failed_files"] == 2
    assert result[SKIPPED_TERMINAL_EXECUTION_KEY] is True


def test_barrier_bypasses_decrement_on_terminal_skip():
    """A terminal-skip result (marker set) must NOT decrement the barrier (the
    reaper already tore it down → a decrement would log a spurious ERROR) and
    must NOT abort."""
    from queue_backend import pg_barrier

    skip_result = {"failed_files": 2, SKIPPED_TERMINAL_EXECUTION_KEY: True}
    ctx = {"execution_id": "e", "batch_index": 0, "callback_descriptor": {}}
    with (
        mock.patch.object(pg_barrier, "claim_batch", return_value=True),
        mock.patch.object(pg_barrier, "_barrier_pg_decrement") as decrement,
        mock.patch.object(pg_barrier, "_abort_barrier_in_body") as abort,
    ):
        out = pg_barrier.run_batch_with_barrier(ctx, lambda: skip_result)

    decrement.assert_not_called()
    abort.assert_not_called()
    assert out is skip_result


def test_barrier_decrements_on_normal_result():
    """A normal (non-skip) result still decrements the barrier — the bypass is
    scoped strictly to the terminal-skip marker."""
    from queue_backend import pg_barrier

    normal = {"total_files": 1, "successful_files": 1, "failed_files": 0}
    ctx = {"execution_id": "e", "batch_index": 0, "callback_descriptor": {}}
    with (
        mock.patch.object(pg_barrier, "claim_batch", return_value=True),
        mock.patch.object(pg_barrier, "_barrier_pg_decrement") as decrement,
    ):
        out = pg_barrier.run_batch_with_barrier(ctx, lambda: normal)

    decrement.assert_called_once()
    assert out is normal


def test_run_batch_stages_proceeds_when_not_terminal():
    """Non-terminal execution → normal flow (setup → pre-create → process)."""
    bd = _fake_batch_data(n_files=1)
    with (
        mock.patch(
            "file_processing.tasks._validate_and_parse_batch_data", return_value=bd
        ),
        mock.patch(
            "file_processing.tasks._setup_execution_context",
            return_value="ctx",
        ),
        mock.patch(
            "file_processing.tasks._refactored_pre_create_file_executions",
            return_value="ctx",
        ) as pre_create,
        mock.patch(
            "file_processing.tasks._process_individual_files", return_value="ctx"
        ) as process_files,
        mock.patch(
            "file_processing.tasks._compile_batch_result",
            return_value={"total_files": 1, "successful_files": 1, "failed_files": 0},
        ),
    ):
        result = _run_batch_stages({"any": "payload"}, "task-1", is_pg=False)

    pre_create.assert_called_once()
    process_files.assert_called_once()
    assert result["successful_files"] == 1
