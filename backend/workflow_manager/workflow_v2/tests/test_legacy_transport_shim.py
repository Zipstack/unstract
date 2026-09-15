"""Rolling-deploy shim for UN-4078.

Nothing reads the ``transport`` key any more, but a pre-UN-4078 worker treats an
absent key as "celery" and publishes to a RabbitMQ with no consumers. The backend
must keep writing it for one release; delete this test with the writes.

DB-free: the model, context, and ``time.sleep`` are mocked.
"""

from unittest.mock import MagicMock, patch

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"


class TestOrchestratorPayloadCarriesLegacyTransport:
    def test_dispatch_kwargs_include_pg_queue_transport(self):
        exec_row = MagicMock(status=ExecutionStatus.EXECUTING.value)

        with (
            patch(f"{_MOD}.UserContext") as user_ctx,
            patch(f"{_MOD}.StateStore") as state_store,
            patch(f"{_MOD}.time"),
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
            patch.object(
                WorkflowHelper, "_dispatch_orchestrator_task", return_value="1"
            ) as dispatch,
            patch.object(WorkflowHelper, "_record_dispatch_handle"),
        ):
            user_ctx.get_organization_identifier.return_value = "org1"
            state_store.get.return_value = None
            wf_exec.objects.get.return_value = exec_row

            WorkflowHelper.execute_workflow_async(
                workflow_id="wf-1",
                execution_id="exec-1",
                hash_values_of_files={},
            )

        dispatch.assert_called_once()
        assert dispatch.call_args.kwargs["kwargs"]["transport"] == "pg_queue"
