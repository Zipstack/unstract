"""What a shared user may and may not do on someone else's resource (UN-2868).

Sharing is not one rule. A Prompt Studio project is shared *for
collaboration* -- prompts, settings and LLM profiles stay editable. Every
other resource is shared *for use*. On all of them, renaming, deleting and
changing who else has access stay with the owner.

These exercise the real viewsets through DRF's request factory, so a gate
that exists only in a permission class -- and never reaches the route -- is
still caught.
"""

from typing import Any

from account_v2.models import User
from django.test import TestCase
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from tool_instance_v2.views import ToolInstanceViewSet
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.views import WorkflowEndpointViewSet
from workflow_manager.workflow_v2.models.workflow import Workflow


class SharedWorkflowEndpointTests(CoOwnerOrgTestMixin, TestCase):
    """A workflow is shared for use: its connector config is owner-only."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-endpoint", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.endpoint = WorkflowEndpoint.objects.create(
            workflow=self.workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
            connection_type=WorkflowEndpoint.ConnectionType.FILESYSTEM,
        )
        self.factory = APIRequestFactory()

    def _patch(self, actor: User) -> Response:
        view = WorkflowEndpointViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch(
            "/x/", {"configuration": {"path": "/changed"}}, format="json"
        )
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.endpoint.pk))

    def _delete(self, actor: User) -> Response:
        view = WorkflowEndpointViewSet.as_view({"delete": "destroy"})
        request = self.factory.delete("/x/")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.endpoint.pk))

    def _read(self, actor: User) -> Response:
        view = WorkflowEndpointViewSet.as_view({"get": "retrieve"})
        request = self.factory.get("/x/")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.endpoint.pk))

    def test_shared_viewer_cannot_change_connector_config(self) -> None:
        self.assertEqual(self._patch(self.viewer).status_code, status.HTTP_403_FORBIDDEN)

    def test_shared_viewer_cannot_delete_the_endpoint(self) -> None:
        self.assertEqual(
            self._delete(self.viewer).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertTrue(WorkflowEndpoint.objects.filter(pk=self.endpoint.pk).exists())

    def test_shared_viewer_can_still_read_it(self) -> None:
        # Refusing the write must not also hide the resource.
        self.assertEqual(self._read(self.viewer).status_code, status.HTTP_200_OK)

    def test_owner_and_co_owner_can_change_it(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        for actor in (self.owner, self.coowner):
            self.assertEqual(self._patch(actor).status_code, status.HTTP_200_OK)

    def test_a_user_with_no_access_gets_404_not_403(self) -> None:
        # 403 would confirm the endpoint exists to someone who cannot see it.
        self.assertEqual(
            self._patch(self.outsider).status_code, status.HTTP_404_NOT_FOUND
        )


class SharedWorkflowToolInstanceTests(CoOwnerOrgTestMixin, TestCase):
    """Attaching a tool mutates the workflow -- and activates it."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-tools",
            organization=self.org,
            created_by=self.owner,
            is_active=False,
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _create(self, actor: User) -> Response:
        view = ToolInstanceViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/x/",
            {"workflow_id": str(self.workflow.pk), "tool_id": "tool-uid"},
            format="json",
        )
        force_authenticate(request, user=actor)
        return view(request)

    def test_shared_viewer_cannot_add_a_tool(self) -> None:
        response = self._create(self.viewer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_user_with_no_access_gets_404(self) -> None:
        self.assertEqual(
            self._create(self.outsider).status_code, status.HTTP_404_NOT_FOUND
        )


class SharedPromptStudioProjectTests(CoOwnerOrgTestMixin, TestCase):
    """Prompt Studio is shared for collaboration; only the name is owner-only."""

    def setUp(self) -> None:
        self._seed_org()
        from prompt_studio.prompt_studio_core_v2.models import CustomTool

        self.tool = CustomTool.objects.create(
            tool_name="ps-project",
            description="collaboration test",
            organization=self.org,
            created_by=self.owner,
        )
        self.tool.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.tool.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _patch(self, actor: User, payload: dict[str, Any]) -> Response:
        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        view = PromptStudioCoreView.as_view({"patch": "partial_update"})
        request = self.factory.patch("/x/", payload, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.tool.pk))

    def test_shared_user_cannot_rename_the_project(self) -> None:
        response = self._patch(self.viewer, {"tool_name": "renamed-by-viewer"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.tool_name, "ps-project")

    def test_shared_user_can_change_a_settings_field(self) -> None:
        # Same endpoint as the rename, so the gate has to be per-field.
        response = self._patch(self.viewer, {"preamble": "set by a collaborator"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.preamble, "set by a collaborator")

    def test_owner_can_rename(self) -> None:
        response = self._patch(self.owner, {"tool_name": "renamed-by-owner"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.tool_name, "renamed-by-owner")

    def test_resending_the_same_name_is_not_a_rename(self) -> None:
        # A settings PATCH that echoes the current name must not be refused.
        response = self._patch(
            self.viewer, {"tool_name": "ps-project", "postamble": "echoed"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
