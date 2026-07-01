"""UN-3662: validate-first terminal guard on the file-processing batch path.

A batch delivered for an execution that is already terminal (COMPLETED/ERROR/
STOPPED) must be skipped, not reprocessed — otherwise a stale/redelivered batch
arriving after the reaper recovered the execution resurrects it to EXECUTING and
re-runs its files (double LLM / destination write). These tests pin:
  * the guard fires for terminal statuses and passes for active/unknown ones,
  * a terminal batch is skipped WITHOUT pre-create / processing,
  * the skip result is a benign zero-work batch result.
"""

from __future__ import annotations

from unittest import mock

import pytest
from unstract.core.data_models import ExecutionStatus

from file_processing.tasks import (
    _raise_if_execution_terminal,
    _run_batch_stages,
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


@pytest.mark.parametrize("status", [*ACTIVE, None, ""])
def test_guard_passes_for_active_or_unknown_on_pg(status):
    # Must NOT raise for PENDING/EXECUTING (or a missing status → fail open).
    _raise_if_execution_terminal({"status": status}, "exec-1", is_pg=True)


@pytest.mark.parametrize("status", TERMINAL)
def test_guard_is_noop_on_celery_path(status):
    # is_pg=False (Celery) → NEVER raises, even for terminal statuses. This is
    # what keeps the Celery flow byte-for-byte unchanged (UN-3662).
    _raise_if_execution_terminal({"status": status}, "exec-1", is_pg=False)


def _fake_batch_data(n_files: int = 3, org: str = "org-1"):
    """A FileBatchData stand-in: real list for len(), mock file_data for org."""
    file_data = mock.Mock()
    file_data.organization_id = org
    return mock.Mock(files=[mock.Mock() for _ in range(n_files)], file_data=file_data)


def test_terminal_skip_result_is_zero_work():
    result = _terminal_skip_result(_fake_batch_data(n_files=4, org="org-9"))
    assert result["total_files"] == 4
    assert result["successful_files"] == 0
    assert result["failed_files"] == 0


def test_run_batch_stages_skips_terminal_without_processing():
    """Terminal execution → benign skip result, and NO pre-create / processing."""
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
        result = _run_batch_stages({"any": "payload"}, "task-1")

    pre_create.assert_not_called()
    process_files.assert_not_called()
    assert result["total_files"] == 2
    assert result["successful_files"] == 0
    assert result["failed_files"] == 0


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
        result = _run_batch_stages({"any": "payload"}, "task-1")

    pre_create.assert_called_once()
    process_files.assert_called_once()
    assert result["successful_files"] == 1
