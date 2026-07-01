"""PG-only duplicate-destination-write guard + active-file TTL cap.

On the PG (at-least-once) transport a batch can be re-run after a crash /
reaper-recovery, and such a re-run bypasses discovery's FileHistory filter. The
destination path therefore re-checks FileHistory by hash right before the write
and skips it when the file already completed in a prior run — closing the
duplicate-write window. The guard is a no-op on the Celery transport (that path
is unchanged), honours use_file_history (ETL "rewrite every run"), and is
fail-open on any lookup error (never blocks a real write).
"""

from __future__ import annotations

from unittest import mock

import pytest
from unstract.core.data_models import (
    ExecutionStatus,
    FileHashData,
    WorkflowTransport,
)

from shared.models.file_processing import FileProcessingContext
from shared.workflow.execution.active_file_manager import (
    MAX_ACTIVE_FILE_CACHE_TTL,
    get_active_file_cache_ttl,
)
from shared.workflow.execution.service import WorkerWorkflowExecutionService

PG = WorkflowTransport.PG_QUEUE.value
CELERY = WorkflowTransport.CELERY.value


def _svc(api_client=None):
    # Bypass __init__ — we only exercise the guard + destination wiring.
    svc = WorkerWorkflowExecutionService.__new__(WorkerWorkflowExecutionService)
    svc.api_client = api_client or mock.Mock()
    svc.logger = mock.Mock()
    svc._last_execution_error = None
    return svc


def _file_hash(h="hash-1"):
    # spec=FileHashData so a typo'd/renamed attr fails loudly instead of being
    # fabricated (the spec-less mock is what hid the original dead-code bug).
    return mock.Mock(
        spec=FileHashData, file_hash=h, file_path="/root/f.pdf", file_name="f.pdf"
    )


def _history(found=True, status=ExecutionStatus.COMPLETED.value):
    return {"found": found, "file_history": {"status": status} if found else None}


def _call(svc, *, transport, use_file_history=True, is_api=False, file_hash=None):
    return svc._pg_destination_already_written(
        file_hash=file_hash or _file_hash(),
        transport=transport,
        use_file_history=use_file_history,
        workflow_id="wf-1",
        is_api=is_api,
    )


def test_celery_transport_never_looks_up_or_skips():
    svc = _svc()
    assert _call(svc, transport=CELERY) is False
    svc.api_client.get_file_history_by_cache_key.assert_not_called()


def test_use_file_history_false_never_looks_up_or_skips():
    # ETL/TASK "rewrite every run" contract — never skip its write.
    svc = _svc()
    assert _call(svc, transport=PG, use_file_history=False) is False
    svc.api_client.get_file_history_by_cache_key.assert_not_called()


def test_pg_skips_when_completed_history_exists():
    svc = _svc()
    svc.api_client.get_file_history_by_cache_key.return_value = _history()
    assert _call(svc, transport=PG) is True


@pytest.mark.parametrize(
    "history",
    [
        {"found": False, "file_history": None},
        {"found": True, "file_history": {"status": ExecutionStatus.ERROR.value}},
        {"found": True, "file_history": {}},
    ],
)
def test_pg_proceeds_when_not_completed(history):
    svc = _svc()
    svc.api_client.get_file_history_by_cache_key.return_value = history
    assert _call(svc, transport=PG) is False


def test_pg_fails_open_and_logs_on_lookup_error():
    svc = _svc()
    svc.api_client.get_file_history_by_cache_key.side_effect = RuntimeError("api down")
    with mock.patch(
        "shared.workflow.execution.service.logger"
    ) as log:
        assert _call(svc, transport=PG) is False  # fail-open
    log.error.assert_called_once()  # loud (Sentry-visible), not a silent warning


def test_pg_proceeds_when_no_cache_key():
    svc = _svc()
    assert _call(svc, transport=PG, file_hash=_file_hash(h=None)) is False
    svc.api_client.get_file_history_by_cache_key.assert_not_called()


def test_api_execution_matches_on_hash_only():
    svc = _svc()
    svc.api_client.get_file_history_by_cache_key.return_value = _history()
    _call(svc, transport=PG, is_api=True)
    _, kwargs = svc.api_client.get_file_history_by_cache_key.call_args
    assert kwargs["file_path"] is None


def test_file_processing_context_carries_transport():
    ctx = FileProcessingContext(
        file_data=mock.Mock(),
        file_hash=_file_hash(),
        api_client=mock.Mock(),
        workflow_execution={},
        transport=PG,
    )
    assert ctx.transport == PG


def test_handle_destination_processing_forwards_transport_and_skips_on_hit():
    """Real-call-site wiring: `_handle_destination_processing` forwards the
    context's transport (not a non-existent `file_data.transport`) to the guard,
    and on a hit it must NOT call `destination.handle_output`. This is exactly
    the regression the original dead `getattr(file_data,'transport')` introduced.
    """
    svc = _svc()
    file_hash = _file_hash()
    file_hash.is_manualreview_required = False
    ctx = FileProcessingContext(
        file_data=mock.Mock(),
        file_hash=file_hash,
        api_client=svc.api_client,
        workflow_execution={},
        transport=PG,
    )
    workflow = mock.Mock()
    workflow.destination_config.to_dict.return_value = {}
    destination = mock.Mock(is_api=False)

    with (
        mock.patch("shared.workflow.execution.service.DestinationConfig"),
        mock.patch(
            "shared.workflow.execution.service.WorkerDestinationConnector"
        ) as WDC,
        mock.patch.object(
            svc, "_pg_destination_already_written", return_value=True
        ) as guard,
    ):
        WDC.from_config.return_value = destination
        result = svc._handle_destination_processing(
            file_processing_context=ctx,
            workflow=workflow,
            workflow_id="wf",
            execution_id="e",
            is_success=True,
            workflow_file_execution_id="fx",
            organization_id="org",
            use_file_history=True,
            is_api=False,
        )

    assert guard.call_args.kwargs["transport"] == PG  # threaded from the context
    assert guard.call_args.kwargs["use_file_history"] is True
    destination.handle_output.assert_not_called()  # skipped, no duplicate write
    assert result.processed is False


def test_active_file_ttl_cap_aligned_to_reaper_window():
    assert MAX_ACTIVE_FILE_CACHE_TTL == 9000
    with mock.patch.dict("os.environ", {"ACTIVE_FILE_CACHE_TTL": "8000"}):
        assert get_active_file_cache_ttl() == 8000  # was capped at 7200 before


def test_active_file_ttl_out_of_range_clamps_and_warns():
    with (
        mock.patch.dict("os.environ", {"ACTIVE_FILE_CACHE_TTL": "999999"}),
        mock.patch(
            "shared.workflow.execution.active_file_manager.logger"
        ) as log,
    ):
        assert get_active_file_cache_ttl() == MAX_ACTIVE_FILE_CACHE_TTL
        log.warning.assert_called_once()
