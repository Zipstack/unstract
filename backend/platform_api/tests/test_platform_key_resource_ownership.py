"""A resource created through a platform key is owned by the key's creator.

One case per resource that grants an OWNER row on create. They live together
rather than in each owning app because the behaviour under test is one
resolver's (`owner_user_for`), and the interesting part is the same everywhere:
the middleware swaps `request.user` for a service account, and service accounts
are filtered out of every owner surface, so granting to one leaves the resource
with no human owner at all.

Each case drives the real URLconf and middleware chain with a key minted here,
so the swap is exercised rather than simulated. Side effects that are not part
of the grant -- cron scheduling, API-key minting, adapter encryption -- are
patched out; what is asserted is only who ends up on the OWNER row.
"""

import secrets
import uuid
from unittest.mock import patch

from account_v2.models import Organization, User
from django.conf import settings
from django.test import override_settings
from permissions.roles import ResourceRole
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.services import create_api_user_for_key
from rest_framework.test import APITestCase
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

ORG = "org-ownership"

# Trimmed from the production chain, preserving its relative order. Pinning it
# keeps the suite behaving the same under the OSS and cloud test settings.
_MIDDLEWARE = [
    "middleware.request_id.CustomRequestIDMiddleware",
    settings.TENANT_MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    settings.CUSTOM_AUTH_MIDDLEWARE,
]


@override_settings(MIDDLEWARE=_MIDDLEWARE)
class PlatformKeyResourceOwnershipTest(APITestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG, display_name="Ownership", organization_id=ORG
        )
        email = f"creator-{uuid.uuid4().hex[:8]}@example.com"
        self.creator = User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )
        self.key = PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=self.org,
            permission=ApiKeyPermission.FULL_ACCESS,
            created_by=self.creator,
        )
        # The minting path, for the `is_service_account` flag it sets.
        create_api_user_for_key(self.key, self.org)

    def tearDown(self) -> None:
        # Left set, this thread-local scopes the managers in whatever runs next.
        UserContext.set_organization_identifier(None)

    # -- helpers ---------------------------------------------------------

    def _post(self, path: str, payload: dict):
        return self.client.post(
            f"/{settings.PATH_PREFIX}/unstract/{ORG}/{path}",
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.key.key}",
        )

    def _assert_owned_by_creator(self, instance) -> None:
        """The OWNER row names the human who made the key, not the machine."""
        membership = instance.memberships.get(role=ResourceRole.OWNER)
        self.assertEqual(membership.user, self.creator)
        self.assertFalse(
            membership.user.is_service_account,
            "the OWNER row went to the key's service account",
        )

    def _make_workflow(self, *, api_endpoints: bool = False) -> Workflow:
        UserContext.set_organization_identifier(ORG)
        workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}",
            organization=self.org,
            created_by=self.creator,
        )
        if api_endpoints:
            # An API deployment is refused unless both endpoints exist and
            # carry a connection type; API ones need no connector instance.
            from workflow_manager.endpoint_v2.models import WorkflowEndpoint

            for endpoint_type in (
                WorkflowEndpoint.EndpointType.SOURCE,
                WorkflowEndpoint.EndpointType.DESTINATION,
            ):
                WorkflowEndpoint.objects.update_or_create(
                    workflow=workflow,
                    endpoint_type=endpoint_type,
                    defaults={
                        "connection_type": WorkflowEndpoint.ConnectionType.API
                    },
                )
        return workflow

    def _fetch(self, model, pk):
        # Managers are org-scoped off a thread-local the request cleared.
        UserContext.set_organization_identifier(ORG)
        return model.objects.get(pk=pk)

    # -- resources -------------------------------------------------------

    def test_workflow(self) -> None:
        response = self._post(
            "workflow/", {"workflow_name": f"wf-{uuid.uuid4().hex[:8]}"}
        )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(self._fetch(Workflow, response.json()["id"]))

    def test_prompt_studio_project(self) -> None:
        from prompt_studio.prompt_studio_core_v2.models import CustomTool

        with patch(
            "prompt_studio.prompt_studio_core_v2.views.PromptStudioHelper."
            "create_default_profile_manager"
        ):
            response = self._post(
                "prompt-studio/",
                {
                    "tool_name": f"ps-{uuid.uuid4().hex[:8]}",
                    "description": "owned by the key's creator",
                    "author": "tester",
                },
            )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(
            self._fetch(CustomTool, response.json()["tool_id"])
        )

    def test_etl_pipeline(self) -> None:
        from pipeline_v2.models import Pipeline

        workflow = self._make_workflow()
        with patch("pipeline_v2.views.KeyHelper.create_api_key"):
            response = self._post(
                "pipeline/",
                {
                    "pipeline_name": f"etl-{uuid.uuid4().hex[:8]}",
                    "workflow": str(workflow.id),
                    "pipeline_type": "ETL",
                },
            )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(self._fetch(Pipeline, response.json()["id"]))

    def test_api_deployment(self) -> None:
        from api_v2.models import APIDeployment

        workflow = self._make_workflow(api_endpoints=True)
        with (
            patch("api_v2.api_deployment_views.DeploymentHelper.create_api_key"),
            patch("api_v2.api_deployment_views.notify_hubspot_event"),
        ):
            response = self._post(
                "api/deployment/",
                {
                    "display_name": f"api-{uuid.uuid4().hex[:8]}",
                    "api_name": f"api-{uuid.uuid4().hex[:8]}",
                    "description": "owned by the key's creator",
                    "workflow": str(workflow.id),
                },
            )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(
            self._fetch(APIDeployment, response.json()["id"])
        )

    def test_connector(self) -> None:
        from connector_v2.models import ConnectorInstance

        workflow = self._make_workflow()
        response = self._post(
            "connector/",
            {
                "connector_name": f"conn-{uuid.uuid4().hex[:8]}",
                # Must resolve in the connector registry, which is keyed by
                # this exact string -- see ConnectorProcessor.
                "connector_id": "minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
                "workflow": str(workflow.id),
                "connector_mode": "FILESYSTEM",
                "connector_metadata": {
                    "key": "test",
                    "secret": "test",
                    "endpoint_url": "http://localhost:9000",
                    "bucket": "test",
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(
            self._fetch(ConnectorInstance, response.json()["id"])
        )

    def test_adapter(self) -> None:
        from adapter_processor_v2.models import AdapterInstance

        response = self._post(
            "adapter/",
            {
                "adapter_name": f"adapter-{uuid.uuid4().hex[:8]}",
                "adapter_id": "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
                "adapter_type": "LLM",
                "adapter_metadata": {"adapter_name": "test", "api_key": "sk-test"},
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self._assert_owned_by_creator(
            self._fetch(AdapterInstance, response.json()["id"])
        )
