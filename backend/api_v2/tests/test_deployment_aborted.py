"""A synchronous API deployment call reports an aborted run as an error (UN-4318)."""

from __future__ import annotations

from unittest.mock import patch

from account_v2.models import Organization
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext
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
        workflow = Workflow.objects.create(workflow_name="wf", is_active=True)
        self.api = APIDeployment.objects.create(api_name="api", workflow=workflow)
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
