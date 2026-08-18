"""Tests for ``WorkflowOrchestrationUtils.record_pg_orchestration_failure`` (UN-3652).

This is the shared PG orchestration-failure recorder used by both the general and
api workers. The tests pin the actual behaviour the PR adds — error surfacing,
counter reconciliation, and the guarantee that **neither a UI-logging hiccup nor
a status-update failure may disturb the caller's original exception/flow** (it
must never raise, so the handler's own re-raise / error-response always runs).

The Celery path is byte-identical by construction: this recorder is only invoked
on the ``is_pg_transport`` branch, so a Celery failure never reaches it (and so
never sends file aggregates).
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from shared.workflow.execution.orchestration_utils import WorkflowOrchestrationUtils

from unstract.core.data_models import ExecutionStatus


def _record(**overrides):
    api_client = overrides.pop("api_client", MagicMock())
    logger = overrides.pop("logger", MagicMock())
    workflow_logger = overrides.pop("workflow_logger", MagicMock())
    kwargs = {
        "api_client": api_client,
        "execution_id": "exec-1",
        "total_files": 2,
        "error_message": "boom",
        "logger": logger,
        "workflow_logger": workflow_logger,
    }
    kwargs.update(overrides)
    WorkflowOrchestrationUtils.record_pg_orchestration_failure(**kwargs)
    return api_client, logger, workflow_logger


class TestRecordPgOrchestrationFailure:
    def test_reconciles_counters_via_update_status(self):
        # B: marks the attempted files failed (in-progress = total - 0 - total = 0)
        # AND includes total_files (the serializer requires it with aggregates).
        api_client, _, _ = _record(total_files=2)
        api_client.update_workflow_execution_status.assert_called_once_with(
            execution_id="exec-1",
            status=ExecutionStatus.ERROR.value,
            error_message="boom",
            total_files=2,
            successful_files=0,
            failed_files=2,
        )

    def test_surfaces_error_to_ui_logger(self):
        # C: the failure reason is published to the UI/WS logger.
        _, _, wl = _record()
        assert wl.log_error.called
        assert "boom" in wl.log_error.call_args.args[1]

    def test_no_logger_still_reconciles(self):
        api_client, _, _ = _record(workflow_logger=None)
        api_client.update_workflow_execution_status.assert_called_once()

    def test_ui_logger_failure_does_not_block_update(self):
        # A WS hiccup must not abort the counter reconciliation.
        wl = MagicMock()
        wl.log_error.side_effect = RuntimeError("ws down")
        api_client, logger, _ = _record(workflow_logger=wl)
        api_client.update_workflow_execution_status.assert_called_once()
        assert logger.warning.called

    def test_status_update_failure_is_swallowed_not_raised(self):
        # The greptile P1 guarantee: a rejected update (e.g. a 400 serializer
        # error) is logged but NOT re-raised, so it can't mask the caller's
        # original orchestration exception or skip its re-raise.
        api_client = MagicMock()
        api_client.update_workflow_execution_status.side_effect = ValueError("400")
        # Must not raise:
        _, logger, _ = _record(api_client=api_client)
        assert logger.error.called  # logged at error level (a real defect signal)

    def test_count_keys_are_valid_update_status_kwargs(self):
        # Guard the ``**counts`` seam against a kwarg rename on either side — a
        # mismatch would otherwise only surface as a runtime TypeError on the rare
        # PG-failure path.
        from shared.api.internal_client import InternalAPIClient

        sig = inspect.signature(InternalAPIClient.update_workflow_execution_status)
        sig.bind_partial(
            execution_id="x",
            status=ExecutionStatus.ERROR.value,
            error_message="e",
            total_files=2,
            successful_files=0,
            failed_files=2,
        )
