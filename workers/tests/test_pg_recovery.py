"""Tests for the shared terminal-ERROR recovery helper (mark_execution_error).

Pure unit tests with a mocked internal API client — no Postgres, no HTTP.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from queue_backend.pg_queue.recovery import mark_execution_error
from unstract.core.data_models import ExecutionStatus


def _api(*, success=True, raises=None):
    client = MagicMock()
    if raises is not None:
        client.update_workflow_execution_status.side_effect = raises
    else:
        client.update_workflow_execution_status.return_value = SimpleNamespace(
            success=success
        )
    return client


def test_marks_error_with_cascade_and_returns_true():
    client = _api(success=True)
    ok = mark_execution_error(client, "exec-1", "org-1", error_message="batch failed")
    assert ok is True
    client.update_workflow_execution_status.assert_called_once()
    _, kwargs = client.update_workflow_execution_status.call_args
    assert kwargs["execution_id"] == "exec-1"
    assert kwargs["organization_id"] == "org-1"
    assert kwargs["status"] == ExecutionStatus.ERROR.value
    assert kwargs["error_message"] == "batch failed"
    # Cascade is the whole point — files must not be left EXECUTING.
    assert kwargs["cascade_terminal_files"] is True


def test_success_false_returns_false_and_logs(caplog):
    client = _api(success=False)
    with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.recovery"):
        ok = mark_execution_error(client, "exec-2", "org-1", error_message="x")
    assert ok is False
    assert "success=False" in caplog.text


def test_exception_is_swallowed_and_returns_false(caplog):
    client = _api(raises=RuntimeError("backend down"))
    with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.recovery"):
        ok = mark_execution_error(client, "exec-3", "org-1", error_message="x")
    # Never raises — the caller keeps its recovery handle instead of crashing.
    assert ok is False
    assert "internal API raised" in caplog.text


def test_absent_success_attr_assumed_true():
    # A legacy raise-on-failure response with no ``success`` attribute is treated
    # as success (it would have raised otherwise).
    client = MagicMock()
    client.update_workflow_execution_status.return_value = object()
    assert mark_execution_error(client, "e", "o", error_message="x") is True
