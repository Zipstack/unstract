"""Where adapters and connectors are used (PB-T11, UN-4328).

The core rule: a profile the delete guard refuses is reported as used, and one
it allows as unused. The parity tests check that against the real ``destroy``.
"""

from typing import Any
from unittest.mock import patch

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet
from api_v2.models import APIDeployment
from connection_check.tests.base import ConnectionCheckTestBase, make_user
from connector_v2.models import ConnectorInstance
from connector_v2.views import ConnectorInstanceViewSet
from django.db import connection
from django.test.utils import CaptureQueriesContext
from permissions.models import ResourceRole
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from rest_framework import status
from tenant_account_v2.models import OrganizationMember
from tool_instance_v2.models import ToolInstance
from utils.tests.auth_seam import member_role
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.workflow import Workflow

from resource_usage.adapters import prompt_studio_refs, string_leaves
from resource_usage.constants import OTHER_GROUP, ProfileKind
from resource_usage.serializers import usage_payload
from resource_usage.references import (
    Reference,
    blocking_relations,
    collect,
    register_provider,
    relation_label,
    unregister_provider,
)

SOURCE = WorkflowEndpoint.EndpointType.SOURCE
DESTINATION = WorkflowEndpoint.EndpointType.DESTINATION


class UsageTestBase(ConnectionCheckTestBase):
    def make_workflow(self, name: str, owner: User | None = None) -> Workflow:
        workflow: Workflow = Workflow.objects.create(
            workflow_name=name, organization=self.org, created_by=self.owner
        )
        workflow.memberships.create(user=owner or self.owner, role=ResourceRole.OWNER)
        return workflow

    def make_tool_instance(self, workflow: Workflow, metadata: Any) -> ToolInstance:
        tool: ToolInstance = ToolInstance.objects.create(
            workflow=workflow,
            tool_id="tool-uid",
            step=1,
            version="",
            metadata=metadata,
            created_by=self.owner,
        )
        return tool

    def make_project(self, name: str, **adapters: Any) -> CustomTool:
        project: CustomTool = CustomTool.objects.create(
            tool_name=name,
            description="usage test",
            organization=self.org,
            created_by=self.owner,
            **adapters,
        )
        project.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        return project

    def make_profile(self, project: CustomTool | None, adapter: Any) -> ProfileManager:
        profile: ProfileManager = ProfileManager.objects.create(
            profile_name=f"profile-{adapter.adapter_name}",
            prompt_studio_tool=project,
            vector_store=adapter,
            embedding_model=adapter,
            llm=adapter,
            x2text=adapter,
            created_by=self.owner,
        )
        return profile

    def make_endpoint(
        self, workflow: Workflow, connector: ConnectorInstance, endpoint_type: str
    ) -> WorkflowEndpoint:
        endpoint: WorkflowEndpoint = WorkflowEndpoint.objects.create(
            workflow=workflow,
            endpoint_type=endpoint_type,
            connection_type=WorkflowEndpoint.ConnectionType.FILESYSTEM,
            connector_instance=connector,
        )
        return endpoint

    def usage(self, viewset: Any, profile: Any, user: User | None = None) -> Any:
        return self.call(viewset, "get", "usage", user, pk=profile.pk)


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class AdapterGuardParityTests(UsageTestBase):
    """Every case is checked against what ``destroy`` actually does."""

    def _cases(self) -> dict[str, AdapterInstance]:
        cases = {name: self.make_adapter(name) for name in (
            "unused",
            "by-id",
            "by-name",
            "nested",
            "project-fk",
            "profile",
            "orphan-profile",
            "workflow-and-project",
            "other-org-id",
            "other-org-name",
            'quoted "name" \\ here',
            "naïve-llm",
        )}
        workflow = self.make_workflow("wf")
        self.make_tool_instance(workflow, {"llm": str(cases["by-id"].pk)})
        # Before the lazy migration, metadata holds the adapter name.
        self.make_tool_instance(workflow, {"llm": "by-name"})
        self.make_tool_instance(
            workflow, {"tool_settings": [{"x": str(cases["nested"].pk)}]}
        )
        self.make_project("p1", monitor_llm=cases["project-fk"])
        self.make_profile(self.make_project("p2"), cases["profile"])
        self.make_profile(None, cases["orphan-profile"])
        both = cases["workflow-and-project"]
        self.make_tool_instance(self.make_workflow("wf2"), {"llm": str(both.pk)})
        self.make_project("p3", challenge_llm=both)
        # The same id and name in another organisation's tool instance: the
        # guard matches within the adapter's organisation only.
        foreign: Workflow = Workflow.objects.create(
            workflow_name="foreign", organization=self.other_org, created_by=self.owner
        )
        self.make_tool_instance(
            foreign, {"llm": str(cases["other-org-id"].pk), "x": "other-org-name"}
        )
        # Names that JSON escapes, or that are not ASCII, still match.
        self.make_tool_instance(workflow, {"llm": 'quoted "name" \\ here'})
        self.make_tool_instance(workflow, {"llm": "naïve-llm"})
        return cases

    def test_used_exactly_when_delete_is_refused(self, _ctx: Any) -> None:
        cases = self._cases()
        index = collect(ProfileKind.ADAPTER, list(cases.values()))
        for name, adapter in cases.items():
            reported_used = index[adapter.pk].used_in_count > 0
            response = self.call(
                AdapterInstanceViewSet, "delete", "destroy", pk=adapter.pk
            )
            refused = response.status_code != status.HTTP_204_NO_CONTENT
            self.assertEqual(reported_used, refused, name)
            self.assertEqual(index[adapter.pk].blocks_delete, refused, name)
        self.assertEqual(
            [name for name, a in cases.items() if not index[a.pk].used_in_count],
            ["unused", "other-org-id", "other-org-name"],
        )

    def test_counts_by_group(self, _ctx: Any) -> None:
        cases = self._cases()
        index = collect(ProfileKind.ADAPTER, list(cases.values()))
        self.assertEqual(index[cases["workflow-and-project"].pk].used_in_count, 2)
        # Two tool instances in one workflow count it once.
        self.assertEqual(index[cases["by-id"].pk].used_in_count, 1)

    def test_only_tool_instances_naming_an_adapter_are_walked(self, _ctx: Any) -> None:
        adapter = self.make_adapter("named")
        workflow = self.make_workflow("wf")
        self.make_tool_instance(workflow, {"llm": str(adapter.pk)})
        self.make_tool_instance(workflow, {"llm": "something-else"})
        # Another organisation's tool instance naming the same id.
        foreign: Workflow = Workflow.objects.create(
            workflow_name="foreign", organization=self.other_org, created_by=self.owner
        )
        self.make_tool_instance(foreign, {"llm": str(adapter.pk), "org": "other"})
        with patch(
            "resource_usage.adapters.string_leaves", wraps=string_leaves
        ) as walk:
            usage = collect(ProfileKind.ADAPTER, [adapter])
        self.assertEqual(usage[adapter.pk].used_in_count, 1)
        walked = [call.args[0] for call in walk.call_args_list]
        self.assertNotIn({"llm": "something-else"}, walked)
        self.assertNotIn({"llm": str(adapter.pk), "org": "other"}, walked)

    def test_profile_without_project_is_in_other(self, _ctx: Any) -> None:
        cases = self._cases()
        usage = collect(ProfileKind.ADAPTER, [cases["orphan-profile"]])
        self.assertEqual(
            [(r.group, r.item_type) for r in usage[cases["orphan-profile"].pk].counted],
            [(OTHER_GROUP, "prompt_studio_profile")],
        )

    def test_unclaimed_protect_relation_still_counts(self, _ctx: Any) -> None:
        """A PROTECT FK no provider knows is reported in ``other``."""
        cases = self._cases()
        unregister_provider(ProfileKind.ADAPTER, prompt_studio_refs)
        try:
            index = collect(ProfileKind.ADAPTER, [cases["project-fk"]])
        finally:
            from resource_usage.adapters import _claims

            register_provider(ProfileKind.ADAPTER, prompt_studio_refs, _claims())
        groups = {ref.group for ref in index[cases["project-fk"].pk].references.values()}
        self.assertEqual(groups, {OTHER_GROUP})
        self.assertEqual(index[cases["project-fk"].pk].used_in_count, 1)

    def test_every_oss_protect_relation_is_claimed(self, _ctx: Any) -> None:
        from resource_usage.references import _providers

        claimed = set().union(*(reg.claims for reg in _providers[ProfileKind.ADAPTER]))
        for rel in blocking_relations(AdapterInstance):
            self.assertIn(relation_label(rel.related_model, rel.field.name), claimed)


class StringLeavesTests(ConnectionCheckTestBase):
    """The scan reads metadata the way the delete guard does."""

    def test_same_answer_as_the_guard(self) -> None:
        needle = "11111111-1111-1111-1111-111111111111"
        samples: list[Any] = [
            {"llm": needle},
            {"a": {"b": [needle]}},
            [needle],
            needle,
            {needle: "key-not-value"},
            None,
            42,
            {"flag": True},
        ]
        adapter = type("A", (), {"id": needle, "adapter_name": "n", "organization": 1})
        for metadata in samples:
            with patch(
                "adapter_processor_v2.views.ToolInstance.objects"
            ) as manager:
                manager.filter.return_value.values_list.return_value = [metadata]
                guard = AdapterInstanceViewSet._adapter_used_in_tool_instance(adapter)
            self.assertEqual(needle in set(string_leaves(metadata)), guard, metadata)


class ConnectorRoleTests(UsageTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.source_only = self.make_connector("source-only")
        self.destination_only = self.make_connector("destination-only")
        self.both_one_workflow = self.make_connector("both-one-workflow")
        self.both_two_workflows = self.make_connector("both-two-workflows")
        self.unused = self.make_connector("unused")
        wf1, wf2, wf3 = (self.make_workflow(f"wf{i}") for i in (1, 2, 3))
        self.make_endpoint(wf1, self.source_only, SOURCE)
        self.make_endpoint(wf1, self.destination_only, DESTINATION)
        self.make_endpoint(wf2, self.both_one_workflow, SOURCE)
        self.make_endpoint(wf2, self.both_one_workflow, DESTINATION)
        self.make_endpoint(wf3, self.both_two_workflows, SOURCE)
        self.make_endpoint(wf1, self.both_two_workflows, DESTINATION)
        self.connectors = [
            self.source_only,
            self.destination_only,
            self.both_one_workflow,
            self.both_two_workflows,
            self.unused,
        ]

    def test_used_as(self) -> None:
        index = collect(ProfileKind.CONNECTOR, self.connectors)
        self.assertEqual(
            {c.connector_name: index[c.pk].used_as for c in self.connectors},
            {
                "source-only": "source",
                "destination-only": "destination",
                "both-one-workflow": "both",
                "both-two-workflows": "both",
                "unused": "none",
            },
        )

    def test_item_roles(self) -> None:
        response = self.usage(ConnectorInstanceViewSet, self.both_one_workflow)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["used_in_count"], 1)
        self.assertEqual(
            [i["role"] for i in response.data["groups"]["workflows"]], ["both"]
        )
        response = self.usage(ConnectorInstanceViewSet, self.both_two_workflows)
        roles = {i["name"]: i["role"] for i in response.data["groups"]["workflows"]}
        self.assertEqual(roles, {"wf3": "source", "wf1": "destination"})

    def test_derived_items_carry_the_workflow_role(self) -> None:
        wf3 = Workflow.objects.get(workflow_name="wf3")
        Pipeline.objects.create(
            pipeline_name="nightly",
            workflow=wf3,
            organization=self.org,
            created_by=self.owner,
        )
        data = self.usage(ConnectorInstanceViewSet, self.both_two_workflows).data
        self.assertEqual([i["role"] for i in data["groups"]["pipelines"]], ["source"])
        self.assertEqual(data["used_in_count"], 2)

    def test_used_exactly_when_delete_is_refused(self) -> None:
        index = collect(ProfileKind.CONNECTOR, self.connectors)
        for connector in self.connectors:
            response = self.call(
                ConnectorInstanceViewSet, "delete", "destroy", pk=connector.pk
            )
            refused = response.status_code != status.HTTP_204_NO_CONTENT
            self.assertEqual(
                index[connector.pk].used_in_count > 0, refused, connector.connector_name
            )


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class UsageEndpointTests(UsageTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.adapter = self.make_adapter("llm")
        self.adapter.shared_to_org = True
        self.adapter.save()
        self.workflow = self.make_workflow("Invoices")
        self.make_tool_instance(self.workflow, {"llm": str(self.adapter.pk)})
        self.project = self.make_project("Contracts", monitor_llm=self.adapter)
        pipeline = Pipeline.objects.create(
            pipeline_name="nightly",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
        )
        pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        deployment = APIDeployment.objects.create(
            api_name="invoices-api",
            display_name="Invoices API",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
        )
        deployment.memberships.create(user=self.owner, role=ResourceRole.OWNER)

    def test_groups_and_items(self, _ctx: Any) -> None:
        response = self.usage(AdapterInstanceViewSet, self.adapter)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["id"], str(self.adapter.pk))
        # Deployments and pipelines come through the workflow: listed, not counted.
        self.assertEqual(data["used_in_count"], 2)
        self.assertEqual(
            list(data["groups"]),
            ["workflows", "prompt_studio_projects", "deployments", "pipelines"],
        )
        self.assertEqual(
            data["groups"]["workflows"],
            [
                {
                    "id": str(self.workflow.pk),
                    "name": "Invoices",
                    "type": "workflow",
                    "accessible": True,
                    "blocks_delete": True,
                }
            ],
        )
        project = data["groups"]["prompt_studio_projects"][0]
        self.assertEqual(
            (project["id"], project["type"]),
            (str(self.project.pk), "prompt_studio_project"),
        )
        deployment = data["groups"]["deployments"][0]
        self.assertEqual(
            (deployment["name"], deployment["type"], deployment["blocks_delete"]),
            ("Invoices API", "api_deployment", False),
        )
        self.assertEqual(data["groups"]["pipelines"][0]["name"], "nightly")
        self.assertNotIn("role", project)

    def test_items_the_caller_cannot_open_have_no_id_or_name(self, _ctx: Any) -> None:
        viewer = make_user("viewer@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=viewer, role=member_role()
        )
        response = self.usage(AdapterInstanceViewSet, self.adapter, viewer)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["used_in_count"], 2)
        for items in response.data["groups"].values():
            for item in items:
                self.assertEqual(
                    (item["id"], item["name"], item["accessible"]), (None, None, False)
                )

    def test_items_are_ordered_accessible_first_then_by_name(
        self, _ctx: Any
    ) -> None:
        self.make_tool_instance(
            self.make_workflow("apples"), {"llm": str(self.adapter.pk)}
        )
        usage = collect(ProfileKind.ADAPTER, [self.adapter])[self.adapter.pk]
        # A model without ``for_user`` is never accessible.
        usage.add(
            Reference(
                group="workflows",
                item_type="workflow",
                model=WorkflowEndpoint,
                pk="00000000-0000-0000-0000-000000000001",
                name="aardvark",
            )
        )
        data = usage_payload(ProfileKind.ADAPTER, self.adapter, usage, self.owner)
        self.assertEqual(
            [i["name"] for i in data["groups"]["workflows"]],
            ["apples", "Invoices", None],
        )

    def test_provider_may_yield_the_pk_as_a_string(self, _ctx: Any) -> None:
        spare = self.make_adapter("spare")

        def stringly(adapters: Any) -> Any:
            for adapter in adapters:
                yield str(adapter.pk), Reference(
                    group="lookups",
                    item_type="lookup",
                    model=CustomTool,
                    pk=self.project.pk,
                    name="Lookup",
                )

        register_provider(ProfileKind.ADAPTER, stringly)
        try:
            usage = collect(ProfileKind.ADAPTER, [spare])
        finally:
            unregister_provider(ProfileKind.ADAPTER, stringly)
        self.assertEqual(usage[spare.pk].used_in_count, 1)

    def test_other_org_gets_404(self, _ctx: Any) -> None:
        self.use_org(self.other_org)
        response = self.usage(AdapterInstanceViewSet, self.adapter)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unused_adapter(self, _ctx: Any) -> None:
        response = self.usage(AdapterInstanceViewSet, self.make_adapter("spare"))
        self.assertEqual(response.data["used_in_count"], 0)
        self.assertTrue(all(not items for items in response.data["groups"].values()))

    def test_non_blocking_provider_counts_but_does_not_block(self, _ctx: Any) -> None:
        """How the cloud backend adds Agentic Studio projects (SET_NULL FKs)."""
        spare = self.make_adapter("spare")

        def agentic(adapters: Any) -> Any:
            for adapter in adapters:
                if adapter.pk == spare.pk:
                    yield adapter.pk, Reference(
                        group="agentic_studio_projects",
                        item_type="agentic_studio_project",
                        model=CustomTool,
                        pk=self.project.pk,
                        name="Agentic",
                        blocks_delete=False,
                    )

        register_provider(ProfileKind.ADAPTER, agentic)
        try:
            data = self.usage(AdapterInstanceViewSet, spare).data
        finally:
            unregister_provider(ProfileKind.ADAPTER, agentic)
        self.assertEqual(data["used_in_count"], 1)
        item = data["groups"]["agentic_studio_projects"][0]
        self.assertFalse(item["blocks_delete"])
        response = self.call(AdapterInstanceViewSet, "delete", "destroy", pk=spare.pk)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


@patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
class UsageListTests(UsageTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.used = self.make_adapter("used")
        self.spare = self.make_adapter("spare")
        self.make_tool_instance(self.make_workflow("wf"), {"llm": str(self.used.pk)})
        self.source = self.make_connector("source")
        self.idle = self.make_connector("idle")
        self.make_endpoint(self.make_workflow("wf2"), self.source, SOURCE)

    def _list(self, viewset: Any, query: str) -> Any:
        response = self.call(viewset, "get", "list", path=f"/{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_with_usage_appends_counts(self, _ctx: Any) -> None:
        rows = self._list(AdapterInstanceViewSet, "?with_usage=true")
        counts = {row["adapter_name"]: row["used_in_count"] for row in rows}
        self.assertEqual(counts, {"used": 1, "spare": 0})
        self.assertEqual(list(rows[0])[-1], "used_in_count")
        rows = self._list(ConnectorInstanceViewSet, "?with_usage=TRUE")
        self.assertEqual(
            {r["connector_name"]: (r["used_in_count"], r["used_as"]) for r in rows},
            {"source": (1, "source"), "idle": (0, "none")},
        )
        self.assertEqual(list(rows[0])[-2:], ["used_in_count", "used_as"])

    def test_paged_envelope_gains_unused_count(self, _ctx: Any) -> None:
        page = self._list(AdapterInstanceViewSet, "?page=1&with_usage=true")
        self.assertEqual(page["unused_count"], 1)
        self.assertEqual(list(page)[-2:], ["failing_count", "unused_count"])

    def test_unused_filter(self, _ctx: Any) -> None:
        page = self._list(AdapterInstanceViewSet, "?page=1&unused=true")
        self.assertEqual([r["adapter_name"] for r in page["results"]], ["spare"])
        # The count ignores the unused filter, like failing_count ignores failing.
        self.assertEqual(page["unused_count"], 1)
        self.assertEqual(page["count"], 1)
        # ... and counts across all pages, not the page shown.
        self.make_adapter("spare-2")
        page = self._list(AdapterInstanceViewSet, "?page=1&page_size=1&with_usage=true")
        self.assertEqual(len(page["results"]), 1)
        self.assertEqual(page["unused_count"], 2)
        rows = self._list(ConnectorInstanceViewSet, "?unused=true")
        self.assertEqual([r["connector_name"] for r in rows], ["idle"])

    def test_profile_gone_between_usage_and_rows_is_left_out(self, _ctx: Any) -> None:
        """Usage is read before the rows, so a concurrent delete drops the row."""
        from resource_usage.views import ProfileUsageMixin

        original = ProfileUsageMixin._list_usage

        def then_delete(view: Any) -> Any:
            index = original(view)
            AdapterInstance.objects.filter(pk=self.spare.pk).delete()
            return index

        with patch.object(ProfileUsageMixin, "_list_usage", then_delete):
            rows = self._list(AdapterInstanceViewSet, "?with_usage=true")
        self.assertEqual([r["adapter_name"] for r in rows], ["used"])

    def test_profile_added_between_usage_and_rows_gets_its_usage(
        self, _ctx: Any
    ) -> None:
        """A profile created after usage was read is listed with its usage."""
        from resource_usage.views import ProfileUsageMixin

        original = ProfileUsageMixin._list_usage

        def then_create(view: Any) -> Any:
            index = original(view)
            late = self.make_adapter("late")
            self.make_tool_instance(self.make_workflow("wf3"), {"llm": str(late.pk)})
            return index

        with patch.object(ProfileUsageMixin, "_list_usage", then_create):
            rows = self._list(AdapterInstanceViewSet, "?with_usage=true")
        counts = {row["adapter_name"]: row["used_in_count"] for row in rows}
        self.assertEqual(counts, {"used": 1, "spare": 0, "late": 1})

    def test_other_values_change_nothing(self, _ctx: Any) -> None:
        for viewset in (AdapterInstanceViewSet, ConnectorInstanceViewSet):
            plain = self._list(viewset, "")
            for query in ("?with_usage=false", "?unused=yes", "?with_usage="):
                self.assertEqual(self._list(viewset, query), plain, query)

    def test_query_count_does_not_grow_with_rows(self, _ctx: Any) -> None:
        def queries(viewset: Any) -> int:
            # Warm per-request caches so both runs below start alike.
            self._list(viewset, "?page=1")
            with CaptureQueriesContext(connection) as captured:
                self._list(viewset, "?page=1&with_usage=true")
            plain = len(captured.captured_queries)
            with CaptureQueriesContext(connection) as captured:
                self._list(viewset, "?page=1")
            return plain - len(captured.captured_queries)

        adapter_extra = queries(AdapterInstanceViewSet)
        connector_extra = queries(ConnectorInstanceViewSet)
        for index in range(5):
            adapter = self.make_adapter(f"more-{index}")
            self.make_tool_instance(self.make_workflow(f"w{index}"), {"x": str(adapter.pk)})
            connector = self.make_connector(f"more-{index}")
            self.make_endpoint(self.make_workflow(f"c{index}"), connector, DESTINATION)
        self.assertEqual(queries(AdapterInstanceViewSet), adapter_extra)
        self.assertEqual(queries(ConnectorInstanceViewSet), connector_extra)
