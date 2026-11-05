"""API deployment calls report an aborted run as an error (UN-4318)."""

from __future__ import annotations

from unittest.mock import patch

from account_v2.models import Organization
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext
from workflow_manager.workflow_v2.dto import ExecutionResponse
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from api_v2.api_deployment_views import DeploymentExecution
from api_v2.models import APIDeployment, APIKey

ORG_ID = "org-aborted"


class SyncCallForAbortedRunTest(TestCase):
    def setUp(self) -> None:
        Organization.objects.create(
            name=ORG_ID, display_name="Org", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        self.workflow = Workflow.objects.create(workflow_name="wf", is_active=True)
        self.api = APIDeployment.objects.create(api_name="api", workflow=self.workflow)
        self.key = APIKey.objects.create(api=self.api)

    def _post_with_status(self, execution_status: str) -> Response:
        request = APIRequestFactory().post(
            f"/deployment/api/{ORG_ID}/api/",
            {"files": SimpleUploadedFile("doc.txt", b"hello")},
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.key.api_key}",
        )
        with (
            patch(
                "api_v2.api_deployment_views.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch(
                "api_v2.api_deployment_views.DeploymentHelper.execute_workflow",
                return_value={"execution_status": execution_status},
            ),
        ):
            return DeploymentExecution.as_view()(
                request, org_name=ORG_ID, api_name="api"
            )

    def test_status_codes(self) -> None:
        for execution_status, code in (
            ("STOPPED", 422),
            ("ERROR", 422),
            ("COMPLETED", 200),
        ):
            with self.subTest(execution_status=execution_status):
                self.assertEqual(
                    self._post_with_status(execution_status).status_code, code
                )

    def _get_stopped_result(self) -> Response:
        item = {
            "file": "doc.txt",
            "metadata": {"workflow_id": "w", "highlight_data": [1]},
            "result": {
                "output": {"a": 1},
                "metadata": {"inner": 1},
                "metrics": {"llm": 1},
            },
        }
        execution = WorkflowExecution.objects.create(
            workflow=self.workflow,
            pipeline_id=self.api.id,
            execution_mode=WorkflowExecution.Mode.QUEUE,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status="STOPPED",
        )
        stopped = ExecutionResponse(
            workflow_id="w",
            execution_id="e",
            execution_status="STOPPED",
            result=[item],
        )
        request = APIRequestFactory().get(
            f"/deployment/api/{ORG_ID}/api/",
            {"execution_id": str(execution.id)},
            HTTP_AUTHORIZATION=f"Bearer {self.key.api_key}",
        )
        helper = "api_v2.api_deployment_views.DeploymentHelper"
        with (
            patch(f"{helper}.get_execution_status", return_value=stopped),
            patch(f"{helper}._enrich_result_with_workflow_metadata"),
        ):
            return DeploymentExecution.as_view()(
                request, org_name=ORG_ID, api_name="api"
            )

    def test_get_filters_a_stopped_runs_results_like_post(self) -> None:
        response = self._get_stopped_result()

        self.assertEqual(response.status_code, 422)
        item = response.data["message"][0]
        self.assertNotIn("highlight_data", item["metadata"])
        self.assertNotIn("metrics", item["result"])
        self.assertNotIn("metadata", item["result"])
        self.assertEqual(item["result"]["output"], {"a": 1})
