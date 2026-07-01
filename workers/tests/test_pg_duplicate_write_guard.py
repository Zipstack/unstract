"""PG-only duplicate-destination-write guard + active-file TTL cap.

On the PG (at-least-once) transport a batch can be re-run after a crash /
reaper-recovery, and such a re-run bypasses discovery's FileHistory filter. The
destination path therefore re-checks FileHistory by hash right before the write
and skips it when the file already completed in a prior run — closing the
duplicate-write window. The guard is a no-op on the Celery transport (that path
is unchanged) and fail-open on any lookup error (never blocks a real write).
"""

from __future__ import annotations

from unittest import mock

import pytest
from unstract.core.data_models import ExecutionStatus, WorkflowTransport

from shared.workflow.execution.active_file_manager import (
    MAX_ACTIVE_FILE_CACHE_TTL,
    get_active_file_cache_ttl,
)
from shared.workflow.execution.service import WorkerWorkflowExecutionService

PG = WorkflowTransport.PG_QUEUE.value
CELERY = WorkflowTransport.CELERY.value


def _svc(api_client):
    # Bypass __init__ — we only exercise the pure guard method.
    svc = WorkerWorkflowExecutionService.__new__(WorkerWorkflowExecutionService)
    svc.api_client = api_client
    return svc


def _file_hash(h="hash-1"):
    return mock.Mock(file_hash=h, file_path="/root/f.pdf", file_name="f.pdf")


def _history(found=True, status=ExecutionStatus.COMPLETED.value):
    return {"found": found, "file_history": {"status": status} if found else None}


def test_celery_transport_never_looks_up_or_skips():
    api = mock.Mock()
    already = _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(),
        file_data=mock.Mock(transport=CELERY),
        workflow_id="wf-1",
        is_api=False,
    )
    assert already is False
    api.get_file_history_by_cache_key.assert_not_called()  # no-op on Celery


def test_pg_skips_when_completed_history_exists():
    api = mock.Mock()
    api.get_file_history_by_cache_key.return_value = _history(status="COMPLETED")
    already = _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(),
        file_data=mock.Mock(transport=PG),
        workflow_id="wf-1",
        is_api=False,
    )
    assert already is True


@pytest.mark.parametrize(
    "history",
    [
        {"found": False, "file_history": None},  # never processed
        {"found": True, "file_history": {"status": ExecutionStatus.ERROR.value}},
        {"found": True, "file_history": {}},  # found but no status
    ],
)
def test_pg_proceeds_when_not_completed(history):
    api = mock.Mock()
    api.get_file_history_by_cache_key.return_value = history
    already = _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(),
        file_data=mock.Mock(transport=PG),
        workflow_id="wf-1",
        is_api=False,
    )
    assert already is False


def test_pg_fails_open_on_lookup_error():
    api = mock.Mock()
    api.get_file_history_by_cache_key.side_effect = RuntimeError("api down")
    already = _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(),
        file_data=mock.Mock(transport=PG),
        workflow_id="wf-1",
        is_api=False,
    )
    assert already is False  # fail-open: never block a legitimate write


def test_pg_proceeds_when_no_cache_key():
    api = mock.Mock()
    already = _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(h=None),
        file_data=mock.Mock(transport=PG),
        workflow_id="wf-1",
        is_api=False,
    )
    assert already is False
    api.get_file_history_by_cache_key.assert_not_called()


def test_api_execution_matches_on_hash_only():
    api = mock.Mock()
    api.get_file_history_by_cache_key.return_value = _history()
    _svc(api)._pg_destination_already_written(
        file_hash=_file_hash(),
        file_data=mock.Mock(transport=PG),
        workflow_id="wf-1",
        is_api=True,
    )
    # API executions have unique per-execution paths → look up by hash only.
    _, kwargs = api.get_file_history_by_cache_key.call_args
    assert kwargs["file_path"] is None


def test_active_file_ttl_cap_aligned_to_reaper_window():
    # Cap raised to the PG stuck-batch reaper timeout (2.5h) so the marker can be
    # configured to outlive a stalled-but-not-yet-reaped batch.
    assert MAX_ACTIVE_FILE_CACHE_TTL == 9000
    with mock.patch.dict("os.environ", {"ACTIVE_FILE_CACHE_TTL": "8000"}):
        assert get_active_file_cache_ttl() == 8000  # was capped at 7200 before
