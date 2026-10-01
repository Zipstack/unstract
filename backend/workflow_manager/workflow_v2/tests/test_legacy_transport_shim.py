"""Rolling-deploy shim for UN-4078.

Nothing reads the ``transport`` key any more, but a pre-UN-4078 worker treats an
absent key as "celery" and publishes to a RabbitMQ with no consumers. The backend
must keep writing it for one release; delete this test with the writes.

DB-free: the model, context, and ``time.sleep`` are mocked.
"""

from unittest.mock import MagicMock, patch

import json

from django.test import RequestFactory

from workflow_manager.internal_api_views import create_workflow_execution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"
_VIEWS = "workflow_manager.internal_api_views"


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


class TestCreateWorkflowExecutionResponseCarriesLegacyTransport:
    """The scheduler reads this response body.

    A pre-UN-4078 scheduler does ``workflow_execution.get("transport",
    DEFAULT_WORKFLOW_TRANSPORT)`` against exactly this dict, so dropping the key
    sends it down the Celery branch.
    """

    def test_response_includes_pg_queue_transport(self):
        execution = MagicMock(
            id="exec-1",
            status=ExecutionStatus.PENDING.value,
            execution_log_id="log-1",
        )

        with (
            patch(f"{_VIEWS}.Organization") as organization,
            patch(f"{_VIEWS}.Workflow") as workflow,
            patch(f"{_VIEWS}.WorkflowExecution") as wf_exec,
        ):
            organization.objects.get.return_value = MagicMock()
            workflow.objects.get.return_value = MagicMock()
            wf_exec.objects.create.return_value = execution

            request = RequestFactory().post(
                "/internal/v1/workflow-execution/",
                data=json.dumps({"workflow_id": "wf-1", "total_files": 1}),
                content_type="application/json",
                HTTP_X_ORGANIZATION_ID="org-1",
            )
            response = create_workflow_execution(request)

        assert response.data["transport"] == "pg_queue"
        assert response.data["execution_id"] == "exec-1"
