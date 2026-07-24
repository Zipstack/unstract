"""Critical path ``api-deployment-provision``: deploying a workflow as an API
mints a usable key and a resolvable endpoint.

Provisioning is the only place an API key is created for a deployment, and the
endpoint string it derives is what callers POST to. Both are returned exactly
once — at create time — so a regression here is unrecoverable for the caller.
Fully synchronous. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets

import pytest
from account_v2.models import Organization, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.workflow import Workflow

from api_v2.api_deployment_views import APIDeploymentViewSet
from api_v2.api_key_views import APIKeyViewSet
from api_v2.models import APIDeployment, APIKey

ORG_ID = "org-provision"


class APIDeploymentProvisionTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG_ID, display_name="Org Provision", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        self.user = User.objects.create_user(
            username="deployer@example.com",
            email="deployer@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.workflow = Workflow.objects.create(workflow_name="wf-deploy", is_active=True)
        for endpoint_type in WorkflowEndpoint.EndpointType:
            WorkflowEndpoint.objects.create(
                workflow=self.workflow,
                endpoint_type=endpoint_type,
                connection_type=WorkflowEndpoint.ConnectionType.API,
            )
        self.factory = APIRequestFactory()

    @pytest.mark.critical_path("api-deployment-provision")
    def test_deploy_mints_key_and_endpoint(self) -> None:
        create = APIDeploymentViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/api/v1/api/deployment/",
            {
                "workflow": str(self.workflow.id),
                "display_name": "my api",
                "api_name": "my-api",
                "description": "provisioned in a test",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = create(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["api_endpoint"] == f"deployment/api/{ORG_ID}/my-api/"

        api = APIDeployment.objects.get(api_name="my-api")
        assert api.is_active
        assert api.organization_id == self.org.id

        # The key is returned once, at create time, and never again.
        key = APIKey.objects.get(api=api)
        assert str(key.api_key) == response.data["api_key"]
        assert key.is_active

        list_keys = APIKeyViewSet.as_view({"get": "api_keys"})
        list_request = self.factory.get(f"/api/v1/api/keys/api/{api.id}/")
        force_authenticate(list_request, user=self.user)
        listed = list_keys(list_request, api_id=str(api.id))

        assert listed.status_code == status.HTTP_200_OK, listed.data
        assert [k["id"] for k in listed.data] == [str(key.id)]
