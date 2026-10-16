"""Create, delete, share and co-owner events for shareable resources.

Every flow goes through the real viewset, so each emit site is exercised.
"""

import json
from unittest.mock import MagicMock, patch

from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet
from api_v2.api_deployment_views import APIDeploymentViewSet
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from connector_v2.views import ConnectorInstanceViewSet
from django.core.files.uploadedfile import SimpleUploadedFile
from permissions.membership_serializers import AddOwnerSerializer, RemoveOwnerSerializer
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from pipeline_v2.views import PipelineViewSet
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from rest_framework.test import force_authenticate
from tenant_account_v2.models import OrganizationGroup, OrganizationMember
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from platform_audit.actions import Action
from platform_audit.tests.base import AuditTestBase, make_user
from platform_audit.views import PlatformAuditEventListView


class ResourceEventTestBase(AuditTestBase):
    def assert_resource_event(
        self, action: str, kind: str, resource_id, name: str, summary: str = ""
    ):
        event = self.only_event(action=action, target_type=kind)
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name, event.summary),
            (kind, str(resource_id), name, summary),
        )
        return event

    def create_workflow(self, name: str = "wf") -> Workflow:
        response = self.call(
            WorkflowViewSet.as_view({"post": "create"}), "post", data={"workflow_name": name}
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Workflow.objects.get(workflow_name=name)

    def create_adapter(self, name: str = "my-llm") -> AdapterInstance:
        with patch.object(AdapterInstance, "get_context_window_size", return_value=4096):
            response = self.call(
                AdapterInstanceViewSet.as_view({"post": "create"}),
                "post",
                data={
                    "adapter_id": "openai|test",
                    "adapter_name": name,
                    "adapter_type": "LLM",
                    "adapter_metadata": {"api_key": "sk-test", "model": "gpt-4o-mini"},
                },
            )
        self.assertEqual(response.status_code, 201, response.data)
        return AdapterInstance.objects.get(adapter_name=name)

    def create_connector(self) -> ConnectorInstance:
        # The connector and payload of connector_v2's register test; creating
        # stores the metadata without contacting the storage.
        response = self.call(
            ConnectorInstanceViewSet.as_view({"post": "create"}),
            "post",
            data={
                "connector_id": "minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
                "connector_name": "minio-in",
                "connector_metadata": {
                    "connectorName": "minio",
                    "key": "access-key",
                    "secret": "secret-key",
                    "endpoint_url": "http://minio.invalid:9000",
                    "region_name": "",
                    "bucket": "bucket",
                    "path": "/",
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        return ConnectorInstance.objects.get(connector_name="minio-in")


class CreateAndDeleteTests(ResourceEventTestBase):
    def _delete(self, viewset, resource, pk) -> None:
        response = self.call(
            viewset.as_view({"delete": "destroy"}), "delete", pk=str(pk)
        )
        self.assertIn(response.status_code, (200, 204), getattr(response, "data", None))

    def test_adapter(self) -> None:
        adapter = self.create_adapter()
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "adapter_instance", adapter.id, "my-llm", "LLM"
        )
        adapter_id = adapter.id
        # The creator's first LLM becomes their default, which cannot be
        # deleted; delete a second one.
        second = self.create_adapter("second-llm")
        self._delete(AdapterInstanceViewSet, second, second.id)
        self.assert_resource_event(
            Action.RESOURCE_DELETED, "adapter_instance", second.id, "second-llm", "LLM"
        )
        self.assertTrue(AdapterInstance.objects.filter(id=adapter_id).exists())

    def test_connector(self) -> None:
        connector = self.create_connector()
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "connector_instance", connector.id, "minio-in"
        )
        self._delete(ConnectorInstanceViewSet, connector, connector.id)
        self.assert_resource_event(
            Action.RESOURCE_DELETED, "connector_instance", connector.id, "minio-in"
        )

    def test_workflow(self) -> None:
        workflow = self.create_workflow()
        self.assert_resource_event(Action.RESOURCE_CREATED, "workflow", workflow.id, "wf")
        self._delete(WorkflowViewSet, workflow, workflow.id)
        self.assert_resource_event(Action.RESOURCE_DELETED, "workflow", workflow.id, "wf")

    def test_api_deployment(self) -> None:
        workflow = self.create_workflow()
        for endpoint in WorkflowEndpoint.objects.filter(workflow=workflow):
            endpoint.connection_type = WorkflowEndpoint.ConnectionType.API
            endpoint.save()
        response = self.call(
            APIDeploymentViewSet.as_view({"post": "create"}),
            "post",
            data={
                "workflow": str(workflow.id),
                "display_name": "my api",
                "api_name": "my-api",
                "description": "audited",
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        api = APIDeployment.objects.get(api_name="my-api")
        self.assert_resource_event(Action.RESOURCE_CREATED, "api_deployment", api.id, "my api")
        self._delete(APIDeploymentViewSet, api, api.id)
        self.assert_resource_event(Action.RESOURCE_DELETED, "api_deployment", api.id, "my api")

    def test_pipeline(self) -> None:
        workflow = self.create_workflow()
        response = self.call(
            PipelineViewSet.as_view({"post": "create"}),
            "post",
            data={
                "workflow": str(workflow.id),
                "pipeline_name": "nightly",
                "pipeline_type": Pipeline.PipelineType.ETL,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        pipeline = Pipeline.objects.get(pipeline_name="nightly")
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "pipeline", pipeline.id, "nightly", "ETL"
        )
        with patch("pipeline_v2.views.SchedulerHelper.remove_job"):
            self._delete(PipelineViewSet, pipeline, pipeline.id)
        self.assert_resource_event(
            Action.RESOURCE_DELETED, "pipeline", pipeline.id, "nightly", "ETL"
        )

    def test_prompt_studio_project(self) -> None:
        response = self.call(
            PromptStudioCoreView.as_view({"post": "create"}),
            "post",
            data={"tool_name": "invoice-parser", "description": "d", "author": "test"},
        )
        self.assertEqual(response.status_code, 201, response.data)
        tool = CustomTool.objects.get(tool_name="invoice-parser")
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "custom_tool", tool.tool_id, "invoice-parser"
        )
        # Deleting also removes the project's files from remote storage.
        models = "prompt_studio.prompt_studio_core_v2.models"
        with (
            patch(f"{models}.EnvHelper.get_storage", return_value=MagicMock()),
            patch(
                f"{models}.PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory",
                return_value="unused",
            ),
        ):
            self._delete(PromptStudioCoreView, tool, tool.tool_id)
        self.assert_resource_event(
            Action.RESOURCE_DELETED, "custom_tool", tool.tool_id, "invoice-parser"
        )

    def _import_project(self):
        # The export's top-level shape (prompt_studio_helper.validate_import_file).
        export = {
            "tool_metadata": {"tool_name": "imported", "author": "a", "description": "d"},
            "tool_settings": {},
            "prompts": [],
        }
        upload = SimpleUploadedFile(
            "project.json", json.dumps(export).encode(), content_type="application/json"
        )
        request = self.factory.post("/", {"file": upload}, format="multipart")
        request.id = "req-123"  # as self.call sets it
        force_authenticate(request, user=self.admin)
        helper = "prompt_studio.prompt_studio_core_v2.views.PromptStudioHelper"
        # The steps after the project row exists are not under test.
        with (
            patch(f"{helper}.import_prompts"),
            patch(f"{helper}.validate_adapter_configuration", return_value=(False, "")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return PromptStudioCoreView.as_view({"post": "import_project"})(request)

    def test_prompt_studio_import(self) -> None:
        with patch(
            "prompt_studio.prompt_studio_core_v2.views.PromptStudioHelper"
            ".create_profile_manager"
        ):
            response = self._import_project()
        self.assertEqual(response.status_code, 201, response.data)
        tool = CustomTool.objects.get(tool_id=response.data["tool_id"])
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "custom_tool", tool.tool_id, tool.tool_name
        )

    def test_a_failed_import_still_records_the_project_it_left(self) -> None:
        # The view has no transaction: a later failure leaves the project row.
        with patch(
            "prompt_studio.prompt_studio_core_v2.views.PromptStudioHelper"
            ".create_profile_manager",
            side_effect=ValueError("adapter not found"),
        ):
            response = self._import_project()
        self.assertEqual(response.status_code, 400, response.data)
        tool = CustomTool.objects.get()
        self.assert_resource_event(
            Action.RESOURCE_CREATED, "custom_tool", tool.tool_id, tool.tool_name
        )

    def test_a_sync_prompts_backup_copy_is_recorded(self) -> None:
        self.call(
            PromptStudioCoreView.as_view({"post": "create"}),
            "post",
            data={"tool_name": "source", "description": "d", "author": "test"},
        )
        source = CustomTool.objects.get(tool_name="source")
        export = PromptStudioHelper.export_project_settings(source)
        # Syncing into the source needs its default profile; the backup is
        # made before that and is what is under test.
        with patch(
            "prompt_studio.prompt_studio_core_v2.views.PromptStudioHelper.sync_prompts",
            return_value={"prompts_created": 0},
        ):
            response = self.call(
                PromptStudioCoreView.as_view({"post": "sync_prompts"}),
                "post",
                data={"data": export, "create_copy": True},
                pk=str(source.tool_id),
            )
        self.assertEqual(response.status_code, 200, response.data)
        backup = CustomTool.objects.get(tool_id=response.data["backup_tool_id"])
        event = self.only_event(
            action=Action.RESOURCE_CREATED, target_id=str(backup.tool_id)
        )
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_name, event.summary),
            ("custom_tool", backup.tool_name, "backup of source"),
        )

    def test_an_in_use_connector_is_not_recorded_deleted(self) -> None:
        connector = self.create_connector()
        workflow = self.create_workflow()
        WorkflowEndpoint.objects.filter(workflow=workflow).update(
            connector_instance=connector
        )
        response = self.call(
            ConnectorInstanceViewSet.as_view({"delete": "destroy"}),
            "delete",
            pk=str(connector.id),
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertTrue(ConnectorInstance.objects.filter(id=connector.id).exists())
        self.assertEqual(self.events(action=Action.RESOURCE_DELETED), [])

    def test_a_refused_delete_records_nothing(self) -> None:
        adapter = self.create_adapter()  # the creator's default LLM
        response = self.call(
            AdapterInstanceViewSet.as_view({"delete": "destroy"}),
            "delete",
            pk=str(adapter.id),
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.events(action=Action.RESOURCE_DELETED), [])


class SharingTests(ResourceEventTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.workflow = self.create_workflow()
        self.group = OrganizationGroup.objects.create(organization=self.org, name="Ops")

    def _share(self, viewset, pk, data):
        response = self.call(viewset.as_view({"post": "share"}), "post", data=data, pk=str(pk))
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))

    def test_records_each_changed_axis(self) -> None:
        self._share(
            WorkflowViewSet,
            self.workflow.id,
            {
                "shared_users": [self.member.id],
                "shared_groups": [self.group.id],
                "shared_to_org": True,
            },
        )
        event = self.assert_resource_event(
            Action.RESOURCE_SHARING_CHANGED, "workflow", self.workflow.id, "wf"
        )
        self.assertEqual(
            event.changes,
            {
                "before": {"shared_users": [], "shared_groups": [], "shared_to_org": False},
                "after": {
                    "shared_users": ["member@example.com"],
                    "shared_groups": ["Ops"],
                    "shared_to_org": True,
                },
            },
        )

    def test_unchanged_axes_and_no_op_shares_are_left_out(self) -> None:
        self._share(WorkflowViewSet, self.workflow.id, {"shared_users": [self.member.id]})
        self._share(
            WorkflowViewSet,
            self.workflow.id,
            {"shared_users": [self.member.id], "shared_to_org": True},
        )
        self._share(WorkflowViewSet, self.workflow.id, {"shared_to_org": True})
        events = self.events(action=Action.RESOURCE_SHARING_CHANGED)
        self.assertEqual(
            [e.changes for e in events],
            [
                {"before": {"shared_users": []}, "after": {"shared_users": ["member@example.com"]}},
                {"before": {"shared_to_org": False}, "after": {"shared_to_org": True}},
            ],
        )

    def test_adapter_share_override_records_too(self) -> None:
        adapter = self.create_adapter()
        self._share(AdapterInstanceViewSet, adapter.id, {"shared_to_org": True})
        self.assert_resource_event(
            Action.RESOURCE_SHARING_CHANGED, "adapter_instance", adapter.id, "my-llm", "LLM"
        )

    def test_co_owner_added_and_removed(self) -> None:
        coowner = make_user("co@example.com")
        from tenant_account_v2.models import OrganizationMember

        OrganizationMember.objects.create(organization=self.org, user=coowner, role="user")
        response = self.call(
            WorkflowViewSet.as_view({"post": "add_co_owner"}),
            "post",
            data={"user_id": coowner.id},
            pk=str(self.workflow.id),
        )
        self.assertEqual(response.status_code, 200, response.data)
        added = self.assert_resource_event(
            Action.RESOURCE_CO_OWNER_ADDED, "workflow", self.workflow.id, "wf", "co@example.com"
        )
        self.assertEqual(added.metadata, {"user_id": coowner.id, "email": "co@example.com"})
        response = self.call(
            WorkflowViewSet.as_view({"delete": "remove_co_owner"}),
            "delete",
            pk=str(self.workflow.id),
            user_id=str(coowner.id),
        )
        self.assertEqual(response.status_code, 204)
        self.assert_resource_event(
            Action.RESOURCE_CO_OWNER_REMOVED, "workflow", self.workflow.id, "wf", "co@example.com"
        )


class CoOwnerRaceTests(ResourceEventTestBase):
    """Two requests can pass validation for the same change; only one makes it."""

    def setUp(self) -> None:
        super().setUp()
        self.workflow = self.create_workflow()
        self.coowner = make_user("co@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=self.coowner, role="user"
        )

    def _context(self) -> dict:
        request = self.factory.post("/")
        request.user = self.admin
        return {"request": request, "resource": self.workflow}

    def test_an_add_racing_a_share_still_makes_the_user_an_owner(self) -> None:
        serializer = AddOwnerSerializer(
            data={"user_id": self.coowner.id}, context=self._context()
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        manager_cls = type(self.workflow.memberships)
        real_get_or_create = manager_cls.get_or_create

        def share_lands_first(manager, *args, **kwargs):
            # A concurrent share/ makes them a viewer just before this write.
            real_get_or_create(
                manager, user_id=kwargs["user_id"], defaults={"role": ResourceRole.VIEWER}
            )
            return real_get_or_create(manager, *args, **kwargs)

        with patch.object(manager_cls, "get_or_create", share_lands_first):
            self.assertTrue(serializer.save())
        self.assertEqual(
            self.workflow.memberships.get(user=self.coowner).role, ResourceRole.OWNER
        )

    def test_an_add_another_request_already_made_changes_nothing(self) -> None:
        serializer = AddOwnerSerializer(
            data={"user_id": self.coowner.id}, context=self._context()
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        self.assertFalse(serializer.save())
        self.assertEqual(
            self.workflow.memberships.filter(user=self.coowner).count(), 1
        )

    def test_a_remove_another_request_already_made_changes_nothing(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        serializer = RemoveOwnerSerializer(
            data={}, context={**self._context(), "user_to_remove": self.coowner}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.workflow.memberships.filter(user=self.coowner).delete()
        self.assertFalse(serializer.save())

    def test_a_save_that_changed_nothing_records_nothing(self) -> None:
        with patch(
            "permissions.membership_views.AddOwnerSerializer.save", return_value=False
        ):
            response = self.call(
                WorkflowViewSet.as_view({"post": "add_co_owner"}),
                "post",
                data={"user_id": self.coowner.id},
                pk=str(self.workflow.id),
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.events(action=Action.RESOURCE_CO_OWNER_ADDED), [])


class OrgScopingTests(ResourceEventTestBase):
    def test_events_belong_to_the_resources_org_and_only_it_reads_them(self) -> None:
        workflow = self.create_workflow()
        event = self.only_event(action=Action.RESOURCE_CREATED)
        self.assertEqual(event.organization, self.org)
        self.assertEqual(workflow.organization, self.org)

        other_admin = make_user("admin@other.com")
        from tenant_account_v2.models import OrganizationMember

        OrganizationMember.objects.create(
            organization=self.other_org, user=other_admin, role="admin"
        )
        self.use_org(self.other_org)
        response = self.call(PlatformAuditEventListView.as_view(), "get", user=other_admin)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"], [])
