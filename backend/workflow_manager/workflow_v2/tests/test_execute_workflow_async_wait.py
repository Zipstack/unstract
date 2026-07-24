"""Regression test for UN-3602 — the defense-in-depth guarantee.

The bug: post-dispatch bookkeeping (recording the dispatch handle) raised, and
because it lived inside the broad post-dispatch ``try/except``, the handler
returned ``EXECUTING`` immediately and SKIPPED the synchronous ``timeout`` poll
loop. The fix moves that bookkeeping into its own ``try/except`` so a failure
there can never abort the wait.

This test pins that: when ``_record_dispatch_handle`` raises,
``execute_workflow_async`` must still enter the poll loop (i.e. call
``_get_execution_status``) instead of short-circuiting to an immediate
``EXECUTING``. Without the inner ``try/except``, this test fails.

DB-free: the model, transport resolution, context, and ``time.sleep`` are mocked.
"""

from unittest.mock import MagicMock, patch

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"


class TestTimeoutWaitSurvivesBookkeepingFailure:
    def test_record_handle_raise_does_not_skip_timeout_poll(self):
        exec_row = MagicMock(status=ExecutionStatus.EXECUTING.value)

        with (
            patch(f"{_MOD}.resolve_transport", return_value="pg_queue"),
            patch(f"{_MOD}.UserContext") as user_ctx,
            patch(f"{_MOD}.StateStore") as state_store,
            patch(f"{_MOD}.time"),  # no-op sleep
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
            patch.object(
                WorkflowHelper, "_dispatch_orchestrator_task", return_value="1"
            ),
            patch.object(
                WorkflowHelper,
                "_record_dispatch_handle",
                side_effect=RuntimeError("bookkeeping boom"),
            ) as record_handle,
            patch.object(
                WorkflowHelper,
                "_get_execution_status",
                return_value=ExecutionStatus.EXECUTING,
            ) as get_status,
        ):
            user_ctx.get_organization_identifier.return_value = "org1"
            state_store.get.return_value = None
            wf_exec.objects.get.return_value = exec_row

            response = WorkflowHelper.execute_workflow_async(
                workflow_id="wf-1",
                execution_id="exec-1",
                hash_values_of_files={},
                timeout=2,  # > -1 so the poll loop is supposed to run
            )

        # The bookkeeping was attempted and raised — and was swallowed.
        record_handle.assert_called_once()
        # The load-bearing assertion: the poll loop STILL ran despite the raise.
        # If the recording were back outside the inner try/except, the broad
        # handler would have returned EXECUTING immediately and this would be 0.
        assert get_status.called
        # And the call returned normally (no propagated exception).
        assert response is not None
