"""Critical path ``workflow-author``: create a workflow and configure its
source + destination endpoints.

This is the authoring contract that every execution path builds on. Creating a
workflow implicitly materialises its two endpoints — a workflow whose endpoints
are missing is unconfigurable and unexecutable, and nothing else in the product
recreates them. Fully synchronous: no workers, no execution. Needs a live DB
(integration tier).
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

from workflow_manager.endpoint_v2.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet


class WorkflowAuthorAPITest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-wf", display_name="Org WF", organization_id="org-wf"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="author@example.com",
            email="author@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.factory = APIRequestFactory()

    def _create_workflow(self, name: str):
        view = WorkflowViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/api/v1/workflow/", {"workflow_name": name}, format="json"
        )
        force_authenticate(request, user=self.user)
        return view(request)

    def _patch_endpoint(self, endpoint: WorkflowEndpoint, payload: dict):
        # Deferred: WorkflowEndpointSerializer resolves a queryset at class-body
        # evaluation, so importing its view at module scope queries the DB during
        # pytest collection — before any test has DB access.
        from workflow_manager.endpoint_v2.views import WorkflowEndpointViewSet

        view = WorkflowEndpointViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch(
            f"/api/v1/workflow/endpoint/{endpoint.id}/", payload, format="json"
        )
        force_authenticate(request, user=self.user)
        return view(request, pk=str(endpoint.id))

    @pytest.mark.critical_path("workflow-author")
    def test_create_workflow_materialises_configurable_endpoints(self) -> None:
        response = self._create_workflow("wf-author")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        workflow = Workflow.objects.get(id=response.data["id"])
        assert workflow.organization_id == self.org.id
        assert workflow.is_active

        endpoints = {e.endpoint_type: e for e in workflow.workflowendpoint_set.all()}
        assert set(endpoints) == {
            WorkflowEndpoint.EndpointType.SOURCE,
            WorkflowEndpoint.EndpointType.DESTINATION,
        }
        # Endpoints land unconfigured — authoring, not execution, fills them in.
        assert all(not e.connection_type for e in endpoints.values())

        source = self._patch_endpoint(
            endpoints[WorkflowEndpoint.EndpointType.SOURCE],
            {"connection_type": WorkflowEndpoint.ConnectionType.API},
        )
        assert source.status_code == status.HTTP_200_OK, source.data

        destination = self._patch_endpoint(
            endpoints[WorkflowEndpoint.EndpointType.DESTINATION],
            {"connection_type": WorkflowEndpoint.ConnectionType.API},
        )
        assert destination.status_code == status.HTTP_200_OK, destination.data

        assert WorkflowEndpointUtils.is_api_workflow(workflow)
