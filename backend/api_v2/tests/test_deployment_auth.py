"""Critical path ``api-deployment-auth``: the public deployment endpoint
rejects unauthenticated callers before any work is dispatched.

``POST /deployment/api/<org>/<api_name>/`` is the only unauthenticated surface
in the product — it is guarded by the ``@DeploymentHelper.validate_api_key``
decorator rather than DRF permission classes, so a regression here silently
opens the endpoint. Every rejection must land before ``execute_workflow``, i.e.
before a ``WorkflowExecution`` row is written or a Celery task is queued;
the mock below asserts exactly that. Needs a live DB (integration tier).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from account_v2.models import Organization
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from api_v2.api_deployment_views import DeploymentExecution
from api_v2.models import APIDeployment, APIKey

ORG_ID = "org-auth"


class APIDeploymentAuthTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG_ID, display_name="Org Auth", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        workflow = Workflow.objects.create(workflow_name="wf-auth", is_active=True)

        self.api = APIDeployment.objects.create(api_name="live-api", workflow=workflow)
        self.key = APIKey.objects.create(api=self.api)
        self.inactive_key = APIKey.objects.create(api=self.api, is_active=False)

        self.inactive_api = APIDeployment.objects.create(
            api_name="dead-api", workflow=workflow, is_active=False
        )
        self.other_api = APIDeployment.objects.create(
            api_name="other-api", workflow=workflow
        )
        self.other_key = APIKey.objects.create(api=self.other_api)

        self.view = DeploymentExecution.as_view()
        self.factory = APIRequestFactory()

    def _post(self, api_name: str, auth: str | None, org: str = ORG_ID):
        headers = {"HTTP_AUTHORIZATION": auth} if auth is not None else {}
        payload = {"files": SimpleUploadedFile("doc.txt", b"hello")}
        request = self.factory.post(
            f"/deployment/api/{org}/{api_name}/", payload, format="multipart", **headers
        )
        return self.view(request, org_name=org, api_name=api_name)

    @pytest.mark.critical_path("api-deployment-auth")
    @patch("api_v2.api_deployment_views.DeploymentHelper.execute_workflow")
    def test_bad_credentials_rejected_before_dispatch(self, execute_workflow) -> None:
        cases = [
            ("missing header", "live-api", None, ORG_ID, 403),
            ("no bearer prefix", "live-api", f"Token {self.key.api_key}", ORG_ID, 403),
            ("empty bearer", "live-api", "Bearer ", ORG_ID, 403),
            ("unknown key", "live-api", f"Bearer {uuid.uuid4()}", ORG_ID, 401),
            ("not a uuid", "live-api", "Bearer not-a-uuid", ORG_ID, 401),
            (
                "inactive key",
                "live-api",
                f"Bearer {self.inactive_key.api_key}",
                ORG_ID,
                401,
            ),
            (
                "key of another api",
                "live-api",
                f"Bearer {self.other_key.api_key}",
                ORG_ID,
                401,
            ),
            ("unknown api", "ghost-api", f"Bearer {self.key.api_key}", ORG_ID, 404),
            ("inactive api", "dead-api", f"Bearer {self.key.api_key}", ORG_ID, 404),
            ("wrong org", "live-api", f"Bearer {self.key.api_key}", "no-such-org", 404),
        ]
        for label, api_name, auth, org, expected in cases:
            with self.subTest(label):
                response = self._post(api_name, auth, org)
                assert response.status_code == expected, response.data

        execute_workflow.assert_not_called()

    @pytest.mark.critical_path("api-deployment-auth")
    @patch("api_v2.api_deployment_views.APIDeploymentRateLimiter.check_and_acquire")
    @patch("api_v2.api_deployment_views.DeploymentHelper.execute_workflow")
    def test_valid_key_reaches_execution(self, execute_workflow, rate_limit) -> None:
        """Guard the inverse of the rejection cases: a guard that rejected
        everything would pass them all.
        """
        rate_limit.return_value = (True, {})
        execute_workflow.return_value = {"execution_status": "COMPLETED"}

        response = self._post("live-api", f"Bearer {self.key.api_key}")

        assert response.status_code == 200, response.data
        execute_workflow.assert_called_once()
