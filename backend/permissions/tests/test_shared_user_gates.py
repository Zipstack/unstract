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
from connector_v2.models import ConnectorInstance
from django.test import TestCase
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.contenttypes.models import ContentType
from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    ResourceGroupShare,
)
from tool_instance_v2.views import ToolInstanceViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.file_history_views import FileHistoryViewSet
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.views import WorkflowViewSet
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
        self.connector = ConnectorInstance.objects.create(
            connector_name="dest-conn",
            connector_id="minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
            connector_metadata={"key": "AKIA-SECRET", "secret": "s3cr3t"},
            organization=self.org,
            created_by=self.owner,
        )
        self.endpoint = WorkflowEndpoint.objects.create(
            workflow=self.workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
            connection_type=WorkflowEndpoint.ConnectionType.FILESYSTEM,
            connector_instance=self.connector,
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

    def test_shared_viewer_does_not_receive_the_connector_credentials(self) -> None:
        # Sharing grants read; the connector's secrets are not part of it.
        rep = self._read(self.viewer).data
        self.assertEqual(rep["connector_instance"]["connector_metadata"], {})

    def test_redacting_credentials_does_not_query_per_endpoint(self) -> None:
        """The redaction must ride the queryset's prefetch, not re-ask per row.

        Measured: 44 queries for 7 endpoints both with and without
        ``to_representation``, so the redaction itself costs nothing. Losing
        the ``workflow__memberships`` prefetch, or making the owner check
        query again, shows up as roughly one more query per endpoint.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for n in range(6):
            wf = Workflow.objects.create(
                workflow_name=f"wf-bulk-{n}",
                organization=self.org,
                created_by=self.owner,
            )
            wf.memberships.create(user=self.owner, role=ResourceRole.OWNER)
            WorkflowEndpoint.objects.create(
                workflow=wf,
                endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
                connection_type=WorkflowEndpoint.ConnectionType.FILESYSTEM,
                connector_instance=self.connector,
            )

        view = WorkflowEndpointViewSet.as_view({"get": "list"})
        request = self.factory.get("/x/")
        force_authenticate(request, user=self.owner)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 7)
        for row in response.data:
            self.assertEqual(
                row["connector_instance"]["connector_metadata"],
                {"key": "AKIA-SECRET", "secret": "s3cr3t"},
            )
        self.assertLess(len(ctx.captured_queries), 48)

    def test_owner_still_receives_the_connector_credentials(self) -> None:
        rep = self._read(self.owner).data
        self.assertEqual(
            rep["connector_instance"]["connector_metadata"],
            {"key": "AKIA-SECRET", "secret": "s3cr3t"},
        )

    def test_owner_and_co_owner_can_change_it(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        for actor in (self.owner, self.coowner):
            self.assertEqual(self._patch(actor).status_code, status.HTTP_200_OK)

    def _endpoint_list(self, actor: User) -> Response:
        view = WorkflowEndpointViewSet.as_view({"get": "workflow_endpoint_list"})
        request = self.factory.get("/x/")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk))

    def test_endpoint_list_refuses_a_user_with_no_access(self) -> None:
        # Pins the list scoping: unscoped, this returned another user's
        # endpoints with their connector configuration.
        self.assertEqual(
            self._endpoint_list(self.outsider).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_endpoint_list_redacts_credentials_for_a_shared_viewer(self) -> None:
        response = self._endpoint_list(self.viewer)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data:
            self.assertEqual(row["connector_instance"]["connector_metadata"], {})

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

    def test_a_tool_cannot_be_moved_to_another_workflow(self) -> None:
        """Pins both reparent guards, including the ``workflow_id`` alias.

        The gate authorises against the stored parent, so a writable parent
        FK would let an owner of workflow B pull a tool off workflow A.
        """
        from tool_instance_v2.models import ToolInstance

        other = Workflow.objects.create(
            workflow_name="wf-other", organization=self.org, created_by=self.owner
        )
        other.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        tool = ToolInstance.objects.create(
            workflow=self.workflow,
            tool_id="tool-uid",
            step=1,
            version="",
            metadata={},
            created_by=self.owner,
        )
        view = ToolInstanceViewSet.as_view({"patch": "partial_update"})
        for payload in ({"workflow": str(other.pk)}, {"workflow_id": str(other.pk)}):
            request = self.factory.patch("/x/", payload, format="json")
            force_authenticate(request, user=self.owner)
            response = view(request, pk=str(tool.pk))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            tool.refresh_from_db()
            self.assertEqual(tool.workflow_id, self.workflow.pk)


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


class PromptStudioChildCreateTests(CoOwnerOrgTestMixin, TestCase):
    """Adding a prompt or an LLM profile is gated by access to the project."""

    def setUp(self) -> None:
        self._seed_org()
        from prompt_studio.prompt_studio_core_v2.models import CustomTool

        self.tool = CustomTool.objects.create(
            tool_name="ps-child-create",
            description="create gate test",
            organization=self.org,
            created_by=self.owner,
        )
        self.tool.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.tool.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _create_prompt(self, actor: User, **extra: Any) -> Response:
        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        view = PromptStudioCoreView.as_view({"post": "create_prompt"})
        payload: dict[str, Any] = {
            "prompt_key": "p1",
            "prompt": "extract something",
            "tool_id": str(self.tool.pk),
        }
        payload.update(extra)
        request = self.factory.post("/x/", payload, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.tool.pk))

    def test_an_outsider_cannot_add_a_prompt(self) -> None:
        from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

        self.assertEqual(
            self._create_prompt(self.outsider).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertFalse(ToolStudioPrompt.objects.filter(tool_id=self.tool).exists())

    def test_the_payload_cannot_redirect_the_prompt_to_another_project(self) -> None:
        # The URL is authoritative: a body naming someone else's project must
        # not decide where the row lands.
        from prompt_studio.prompt_studio_core_v2.models import CustomTool
        from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

        other = CustomTool.objects.create(
            tool_name="not-mine",
            description="owned by the outsider",
            organization=self.org,
            created_by=self.outsider,
        )
        other.memberships.create(user=self.outsider, role=ResourceRole.OWNER)

        response = self._create_prompt(self.owner, tool_id=str(other.pk))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(ToolStudioPrompt.objects.filter(tool_id=other).exists())
        self.assertTrue(ToolStudioPrompt.objects.filter(tool_id=self.tool).exists())

    def test_a_collaborator_can_add_a_prompt(self) -> None:
        # Prompt Studio is shared for collaboration: prompts stay editable.
        self.assertEqual(
            self._create_prompt(self.viewer).status_code, status.HTTP_201_CREATED
        )

    def test_a_malformed_parent_id_is_refused_not_a_server_error(self) -> None:
        # The gate filters a UUID column on raw request data, ahead of any
        # serializer: an unparseable id must miss the lookup, not raise.
        from prompt_studio.prompt_profile_manager_v2.views import ProfileManagerView

        view = ProfileManagerView.as_view({"post": "create"})
        request = self.factory.post(
            "/x/", {"profile_name": "p", "prompt_studio_tool": "not-a-uuid"}, format="json"
        )
        force_authenticate(request, user=self.owner)
        self.assertEqual(view(request).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_malformed_prompt_id_on_reorder_is_not_a_server_error(self) -> None:
        from prompt_studio.prompt_studio_v2.views import ToolStudioPromptView

        view = ToolStudioPromptView.as_view({"post": "reorder_prompts"})
        # Complete payload on purpose: omitting a required field 400s before
        # the id is ever parsed, which is not what this pins.
        request = self.factory.post(
            "/x/",
            {
                "prompt_id": "not-a-uuid",
                "start_sequence_number": 1,
                "end_sequence_number": 2,
            },
            format="json",
        )
        force_authenticate(request, user=self.owner)
        self.assertEqual(view(request).status_code, status.HTTP_400_BAD_REQUEST)


class GroupSharedWorkflowFileHistoryTests(CoOwnerOrgTestMixin, TestCase):
    """Reaching a workflow through a group grants its sub-pages too.

    ``Workflow.objects.for_user`` has always included group shares, so a
    group-shared workflow is visible in the list. Its file history was gated
    on a check that stopped at direct viewers, so opening the workflow worked
    and the File History tab returned 403.
    """

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-group", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)

        group = OrganizationGroup.objects.create(
            name="team-fh", organization=self.org, created_by=self.owner
        )
        GroupMembership.objects.create(group=group, user=self.viewer)
        ResourceGroupShare.objects.create(
            group=group,
            content_type=ContentType.objects.get_for_model(Workflow),
            object_id=str(self.workflow.pk),
            organization=self.org,
        )
        self.factory = APIRequestFactory()

    def _list(self, actor: User) -> Response:
        view = FileHistoryViewSet.as_view({"get": "list"})
        request = self.factory.get("/x/")
        force_authenticate(request, user=actor)
        return view(request, workflow_id=str(self.workflow.pk))

    def test_group_member_can_view_file_history(self) -> None:
        self.assertEqual(self._list(self.viewer).status_code, status.HTTP_200_OK)

    def test_owner_can_view_file_history(self) -> None:
        self.assertEqual(self._list(self.owner).status_code, status.HTTP_200_OK)

    def test_a_user_with_no_access_still_cannot(self) -> None:
        # Widening to groups must not widen to everyone in the org.
        self.assertEqual(
            self._list(self.outsider).status_code, status.HTTP_403_FORBIDDEN
        )


class FileHistoryWriteGateTests(CoOwnerOrgTestMixin, TestCase):
    """Deleting a workflow's execution history is the owner's."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-fh-write", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.history = FileHistory.objects.create(
            workflow=self.workflow,
            cache_key=f"ck-{self.workflow.pk}",
            provider_file_uuid="pf-1",
            status=ExecutionStatus.COMPLETED.value,
        )
        self.factory = APIRequestFactory()

    def test_shared_viewer_cannot_delete_one_row(self) -> None:
        view = FileHistoryViewSet.as_view({"delete": "destroy"})
        request = self.factory.delete("/x/")
        force_authenticate(request, user=self.viewer)
        response = view(
            request, workflow_id=str(self.workflow.pk), id=str(self.history.pk)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(FileHistory.objects.filter(pk=self.history.pk).exists())

    def test_shared_viewer_cannot_clear_the_history(self) -> None:
        view = FileHistoryViewSet.as_view({"post": "clear"})
        request = self.factory.post("/x/", {"ids": [str(self.history.pk)]}, format="json")
        force_authenticate(request, user=self.viewer)
        response = view(request, workflow_id=str(self.workflow.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(FileHistory.objects.filter(pk=self.history.pk).exists())

    def test_owner_can_clear_the_history(self) -> None:
        view = FileHistoryViewSet.as_view({"post": "clear"})
        request = self.factory.post("/x/", {"ids": [str(self.history.pk)]}, format="json")
        force_authenticate(request, user=self.owner)
        response = view(request, workflow_id=str(self.workflow.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ClearFileMarkerMethodTests(CoOwnerOrgTestMixin, TestCase):
    """Clearing execution markers is a POST, and an owner action."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-marker", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def test_the_action_accepts_post_only(self) -> None:
        """Pins the GET->POST move: a GET is reachable by prefetch or a
        pasted URL, with no CSRF in the way.

        Asserts the action's own mapping. Driving ``as_view({"post": ...})``
        and sending a GET proves nothing -- the 405 comes from that map, so
        it passes with the decorator back on ``methods=["get"]``.
        """
        mapping = WorkflowViewSet.clear_file_marker.mapping
        self.assertEqual(set(mapping), {"post"})
        self.assertEqual(mapping["post"], "clear_file_marker")

    def test_the_route_binds_post_only(self) -> None:
        """The URLconf and the decorator have to agree, or one silently wins."""
        from workflow_manager.workflow_v2.urls.workflow import urlpatterns

        matched = [
            p for p in urlpatterns if "clear-file-marker" in str(p.pattern)
        ]
        # More than one: DRF adds a format-suffix twin. Every one must agree.
        self.assertTrue(matched)
        for pattern in matched:
            self.assertEqual(set(pattern.callback.actions), {"post"})

    def test_shared_viewer_cannot_post_it(self) -> None:
        view = WorkflowViewSet.as_view({"post": "clear_file_marker"})
        request = self.factory.post("/x/")
        force_authenticate(request, user=self.viewer)
        response = view(request, pk=str(self.workflow.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeployAnothersWorkflowTests(CoOwnerOrgTestMixin, TestCase):
    """Deploying a workflow is an owner act, not a use of a shared one.

    ``workflow`` is writable on both the deployment and pipeline serializers
    and was bound through a merely org-scoped manager, so any member could
    point a new deployment at a colleague's private workflow -- then execute
    it, with its connectors and adapters, at the owner's cost, and mint API
    keys against it.
    """

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-private", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _deploy(self, actor: User) -> Response:
        from api_v2.api_deployment_views import DeploymentExecution  # noqa: F401
        from api_v2.api_deployment_views import APIDeploymentViewSet

        view = APIDeploymentViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/x/",
            {
                "workflow": str(self.workflow.pk),
                "display_name": "stolen",
                "api_name": "stolen",
            },
            format="json",
        )
        force_authenticate(request, user=actor)
        return view(request)

    def _schedule(self, actor: User) -> Response:
        from pipeline_v2.views import PipelineViewSet

        view = PipelineViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/x/",
            {
                "workflow": str(self.workflow.pk),
                "pipeline_name": "stolen",
                "pipeline_type": "ETL",
                "cron_string": "0 0 * * *",
            },
            format="json",
        )
        force_authenticate(request, user=actor)
        return view(request)

    def _assert_workflow_refused(self, response: Response) -> None:
        """Refused because the workflow is not in the field's queryset.

        The code matters: this serializer also rejects a workflow whose
        endpoints are unconfigured, on the same ``workflow`` attr. Only the
        scoping produces ``does_not_exist``, so asserting the attr alone
        passes with the gate removed.
        """
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        codes = {
            e.get("code")
            for e in response.data.get("errors", [])
            if e.get("attr") == "workflow"
        }
        self.assertIn("does_not_exist", codes)

    def test_an_outsider_cannot_deploy_it(self) -> None:
        self._assert_workflow_refused(self._deploy(self.outsider))

    def test_a_shared_viewer_cannot_deploy_it(self) -> None:
        # Shared for use: running it is fine, standing up a permanent
        # execution surface on it is the owner's.
        self._assert_workflow_refused(self._deploy(self.viewer))

    def test_an_outsider_cannot_schedule_it(self) -> None:
        self._assert_workflow_refused(self._schedule(self.outsider))

    def test_a_shared_viewer_cannot_schedule_it(self) -> None:
        self._assert_workflow_refused(self._schedule(self.viewer))

    def test_the_owner_is_not_blocked(self) -> None:
        # The scoping must not lock the owner out of their own workflow.
        response = self._schedule(self.owner)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_pipeline_co_owner_can_still_save_it(self) -> None:
        """Co-owning the pipeline is not co-owning its workflow.

        The edit modal PUTs the whole form back, ``workflow`` included, so a
        queryset holding only workflows the requester owns refuses a write
        that changes nothing about the parent.
        """
        from pipeline_v2.models import Pipeline
        from pipeline_v2.views import PipelineViewSet

        pipeline = Pipeline.objects.create(
            pipeline_name="shared-etl",
            pipeline_type="ETL",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            cron_string="0 0 * * *",
        )
        pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        pipeline.memberships.create(user=self.coowner, role=ResourceRole.OWNER)

        view = PipelineViewSet.as_view({"put": "update"})
        request = self.factory.put(
            "/x/",
            {
                "workflow": str(self.workflow.pk),
                "pipeline_name": "shared-etl-renamed",
                "pipeline_type": "ETL",
                "cron_string": "0 0 * * *",
            },
            format="json",
        )
        force_authenticate(request, user=self.coowner)
        response = view(request, pk=str(pipeline.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pipeline.refresh_from_db()
        self.assertEqual(pipeline.pipeline_name, "shared-etl-renamed")
        self.assertEqual(pipeline.workflow_id, self.workflow.pk)

    def test_a_co_owner_still_cannot_repoint_it(self) -> None:
        """Keeping the bound workflow selectable must not reopen reparenting."""
        from pipeline_v2.models import Pipeline
        from pipeline_v2.views import PipelineViewSet

        other = Workflow.objects.create(
            workflow_name="wf-elsewhere", organization=self.org, created_by=self.owner
        )
        other.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        pipeline = Pipeline.objects.create(
            pipeline_name="shared-etl-2",
            pipeline_type="ETL",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            cron_string="0 0 * * *",
        )
        pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        pipeline.memberships.create(user=self.coowner, role=ResourceRole.OWNER)

        view = PipelineViewSet.as_view({"put": "update"})
        request = self.factory.put(
            "/x/",
            {
                "workflow": str(other.pk),
                "pipeline_name": "shared-etl-2",
                "pipeline_type": "ETL",
                "cron_string": "0 0 * * *",
            },
            format="json",
        )
        force_authenticate(request, user=self.coowner)
        self.assertEqual(
            view(request, pk=str(pipeline.pk)).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        pipeline.refresh_from_db()
        self.assertEqual(pipeline.workflow_id, self.workflow.pk)


class SharedPipelineActivationTests(CoOwnerOrgTestMixin, TestCase):
    """Starting and stopping a shared pipeline is use, not configuration."""

    def setUp(self) -> None:
        self._seed_org()
        from pipeline_v2.models import Pipeline

        self.workflow = Workflow.objects.create(
            workflow_name="wf-toggle", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.pipeline = Pipeline.objects.create(
            pipeline_name="etl-toggle",
            pipeline_type="ETL",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            cron_string="0 0 * * *",
            active=False,
        )
        self.pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.pipeline.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _patch(self, actor: User, payload: dict[str, Any]) -> Response:
        from pipeline_v2.views import PipelineViewSet

        view = PipelineViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch("/x/", payload, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.pipeline.pk))

    def test_a_shared_viewer_can_enable_it(self) -> None:
        response = self._patch(
            self.viewer, {"active": True, "pipeline_id": str(self.pipeline.pk)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pipeline.refresh_from_db()
        self.assertTrue(self.pipeline.active)

    def test_a_shared_viewer_cannot_smuggle_another_field_alongside(self) -> None:
        """The relaxation is activation-only; one extra key and it is gone."""
        response = self._patch(
            self.viewer, {"active": True, "pipeline_name": "renamed-by-viewer"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.pipeline.refresh_from_db()
        self.assertFalse(self.pipeline.active)
        self.assertEqual(self.pipeline.pipeline_name, "etl-toggle")

    def test_a_shared_viewer_still_cannot_rename_it(self) -> None:
        response = self._patch(self.viewer, {"pipeline_name": "renamed"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_outsider_cannot_enable_it(self) -> None:
        response = self._patch(
            self.outsider, {"active": True, "pipeline_id": str(self.pipeline.pk)}
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )
        self.pipeline.refresh_from_db()
        self.assertFalse(self.pipeline.active)
