"""Organisation capability permissions (UN-4399).

The OSS auth service treats the ``admin`` role as admin, so the fixtures'
roles drive ``is_user_organization_admin`` directly.
"""

from types import SimpleNamespace
from unittest.mock import patch

from account_v2.models import Organization
from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet
from api_v2.api_deployment_views import APIDeploymentViewSet
from connector_v2.views import ConnectorInstanceViewSet
from django.test import SimpleTestCase
from permissions.permission import IsOwner
from permissions.roles import ResourceRole
from pipeline_v2.views import PipelineViewSet
from platform_audit.tests.base import AuditTestBase, make_user
from rest_framework.exceptions import PermissionDenied
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from tenant_account_v2.capabilities import (
    SPECS,
    Capability,
    CapabilitySetting,
)
from tenant_account_v2.views import organization_capabilities, organization_settings

ENFORCED = [spec for spec in SPECS if spec.enforced]


class CapabilityRegistryTests(SimpleTestCase):
    def test_every_capability_has_one_spec_in_design_order(self) -> None:
        self.assertEqual([s.key for s in SPECS], list(Capability))

    def test_every_spec_is_stored_on_organization(self) -> None:
        fields = {f.name for f in Organization._meta.get_fields()}
        for spec in SPECS:
            with self.subTest(key=spec.key.value):
                self.assertIn(spec.field, fields)

    def test_new_capabilities_use_the_standard_message(self) -> None:
        spec = next(s for s in SPECS if s.key == Capability.CREATE_OTHER_ADAPTERS)
        self.assertEqual(
            spec.message(), "Create other adapters is restricted to organisation admins."
        )


class CapabilityTestBase(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.service_account = make_user("svc@example.com", is_service_account=True)

    def restrict(self, key: Capability, restricted: bool) -> None:
        spec = next(s for s in SPECS if s.key == key)
        Organization.objects.filter(pk=self.org.pk).update(**{spec.field: restricted})
        self.org.refresh_from_db()

    def capabilities(self, user) -> dict[str, dict]:
        response = self.call(organization_capabilities, "get", user=user)
        self.assertEqual(response.status_code, 200)
        return {row["key"]: row for row in response.data["capabilities"]}


class CapabilitiesApiTests(CapabilityTestBase):
    def test_defaults_are_todays_behaviour(self) -> None:
        rows = self.capabilities(self.member)
        expected = {
            "create_llm_adapters": ("any_member", True),
            "create_connectors": ("any_member", True),
            "create_other_adapters": ("any_member", True),
            "manage_api_keys": ("admins_only", False),
            "manage_members": ("admins_only", False),
            "change_platform_defaults": ("admins_only", False),
            "delete_workflows_and_deployments": ("any_member", True),
        }
        self.assertEqual(
            {k: (r["setting"], r["allowed_for_me"]) for k, r in rows.items()},
            expected,
        )
        self.assertEqual(list(rows), [s.key.value for s in SPECS])
        self.assertEqual(rows["create_connectors"]["label"], "Create connectors")

    def test_admins_are_always_allowed(self) -> None:
        rows = self.capabilities(self.admin)
        self.assertTrue(all(r["allowed_for_me"] for r in rows.values()))

    def test_service_accounts_are_allowed_only_what_is_enforced(self) -> None:
        rows = self.capabilities(self.service_account)
        for spec in SPECS:
            with self.subTest(key=spec.key.value):
                self.assertEqual(rows[spec.key.value]["allowed_for_me"], spec.enforced)

    def test_service_account_cannot_patch(self) -> None:
        response = self.call(
            organization_capabilities,
            "patch",
            user=self.service_account,
            data={"create_connectors": "admins_only"},
        )
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_patch(self) -> None:
        response = self.call(
            organization_capabilities,
            "patch",
            user=self.member,
            data={"create_connectors": "admins_only"},
        )
        self.assertEqual(response.status_code, 403)
        self.org.refresh_from_db()
        self.assertFalse(self.org.restrict_connector_creation)

    def test_admin_patch_saves_and_returns_the_full_list(self) -> None:
        response = self.call(
            organization_capabilities,
            "patch",
            data={
                "create_connectors": "admins_only",
                "delete_workflows_and_deployments": "admins_only",
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["capabilities"]), len(SPECS))
        self.org.refresh_from_db()
        self.assertTrue(self.org.restrict_connector_creation)
        self.assertTrue(self.org.restrict_resource_deletion)
        rows = self.capabilities(self.member)
        self.assertFalse(rows["create_connectors"]["allowed_for_me"])

    def test_patch_rejects_bad_input_and_saves_nothing(self) -> None:
        for body, attr in (
            ({"create_connectors": "admins_only", "nope": "admins_only"}, "nope"),
            ({"create_connectors": "admins_only", "create_llm_adapters": "x"}, None),
            ({"manage_members": "any_member", "create_connectors": "admins_only"}, None),
            ({}, None),
        ):
            with self.subTest(body=str(body)):
                response = self.call(organization_capabilities, "patch", data=body)
                self.assertEqual(response.status_code, 400, response.data)
                self.org.refresh_from_db()
                self.assertFalse(self.org.restrict_connector_creation)

    def test_unenforced_capabilities_accept_only_admins_only(self) -> None:
        for spec in SPECS:
            if spec.enforced:
                continue
            with self.subTest(key=spec.key.value):
                ok = self.call(
                    organization_capabilities,
                    "patch",
                    data={spec.key.value: "admins_only"},
                )
                self.assertEqual(ok.status_code, 200)
                refused = self.call(
                    organization_capabilities,
                    "patch",
                    data={spec.key.value: "any_member"},
                )
                self.assertEqual(refused.status_code, 400)

    def test_legacy_settings_and_capabilities_stay_in_step(self) -> None:
        self.call(
            organization_settings, "patch", data={"restrict_llm_adapter_creation": True}
        )
        self.assertEqual(
            self.capabilities(self.admin)["create_llm_adapters"]["setting"],
            CapabilitySetting.ADMINS_ONLY,
        )
        self.call(
            organization_capabilities, "patch", data={"create_connectors": "admins_only"}
        )
        response = self.call(organization_settings, "get")
        self.assertEqual(
            response.data,
            {"restrict_llm_adapter_creation": True, "restrict_connector_creation": True},
        )

    def test_each_change_is_audited_once(self) -> None:
        self.call(
            organization_capabilities,
            "patch",
            data={
                "create_connectors": "admins_only",
                "create_llm_adapters": "any_member",
            },
        )
        event = self.only_event(action="capability.changed")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("capability", "create_connectors", "Create connectors"),
        )
        self.assertEqual(
            event.changes,
            {"before": {"setting": "any_member"}, "after": {"setting": "admins_only"}},
        )


class EnforcementMatrixTests(CapabilityTestBase):
    """Each enforced capability x {admins_only, any_member} x {admin, member,
    service account}.
    """

    def _allowed(self, key: Capability, user) -> bool:
        if key == Capability.CREATE_CONNECTORS:
            view = ConnectorInstanceViewSet.as_view({"post": "create"})
            # Refusal happens before payload validation, so any body will do.
            response = self.call(view, "post", user=user, data={})
            return response.status_code != 403
        if key in (Capability.CREATE_LLM_ADAPTERS, Capability.CREATE_OTHER_ADAPTERS):
            adapter_type = "LLM" if key == Capability.CREATE_LLM_ADAPTERS else "EMBEDDING"
            response = self._create_adapter(user, adapter_type)
            if response.status_code == 403:
                return False
            self.assertEqual(response.status_code, 201, response.data)
            return True
        return self._may_delete_owned_workflow(user)

    def _create_adapter(self, user, adapter_type: str):
        view = AdapterInstanceViewSet.as_view({"post": "create"})
        payload = {
            "adapter_id": "openai|test",
            "adapter_name": f"{adapter_type}-{user.pk}-{AdapterInstance.objects.count()}",
            "adapter_type": adapter_type,
            "adapter_metadata": {"api_key": "sk-test", "model": "gpt-4o-mini"},
        }
        with patch.object(AdapterInstance, "get_context_window_size", return_value=4096):
            return self.call(view, "post", user=user, data=payload)

    def _may_delete_owned_workflow(self, user) -> bool:
        workflow = Workflow.objects.create(
            workflow_name=f"wf-{user.pk}-{Workflow.objects.count()}",
            organization=self.org,
            created_by=user,
        )
        workflow.memberships.create(user=user, role=ResourceRole.OWNER)
        view = WorkflowViewSet.as_view({"delete": "destroy"})
        response = self.call(view, "delete", user=user, pk=workflow.pk)
        if response.status_code == 403:
            return False
        self.assertIn(response.status_code, (200, 204), getattr(response, "data", None))
        return True

    def test_matrix(self) -> None:
        for spec in ENFORCED:
            for restricted in (True, False):
                self.restrict(spec.key, restricted)
                for name, user, expected in (
                    ("admin", self.admin, True),
                    ("member", self.member, not restricted),
                    ("service account", self.service_account, True),
                ):
                    with self.subTest(
                        key=spec.key.value, restricted=restricted, user=name
                    ):
                        self.assertEqual(self._allowed(spec.key, user), expected)

    def test_refusal_messages(self) -> None:
        self.restrict(Capability.CREATE_CONNECTORS, True)
        self.restrict(Capability.CREATE_LLM_ADAPTERS, True)
        self.restrict(Capability.CREATE_OTHER_ADAPTERS, True)
        view = ConnectorInstanceViewSet.as_view({"post": "create"})
        response = self.call(view, "post", user=self.member, data={})
        self.assertIn(
            "Connector creation is restricted to organization admins",
            str(response.data),
        )
        response = self._create_adapter(self.member, "LLM")
        self.assertIn(
            "LLM adapter creation is restricted to organization admins",
            str(response.data),
        )
        response = self._create_adapter(self.member, "EMBEDDING")
        self.assertIn(
            "Create other adapters is restricted to organisation admins",
            str(response.data),
        )

    def test_changing_an_adapters_type_needs_the_new_types_capability(self) -> None:
        created = self._create_adapter(self.member, "EMBEDDING")
        self.assertEqual(created.status_code, 201, created.data)
        self.restrict(Capability.CREATE_LLM_ADAPTERS, True)
        view = AdapterInstanceViewSet.as_view({"patch": "partial_update"})
        response = self.call(
            view,
            "patch",
            user=self.member,
            data={"adapter_type": "LLM"},
            pk=created.data["id"],
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            AdapterInstance.objects.get(pk=created.data["id"]).adapter_type, "EMBEDDING"
        )

    def test_deleting_still_needs_ownership(self) -> None:
        stranger_owned = Workflow.objects.create(
            workflow_name="not-yours", organization=self.org, created_by=self.admin
        )
        stranger_owned.memberships.create(user=self.admin, role=ResourceRole.OWNER)
        # Shared with the member, so they can see it but do not own it.
        stranger_owned.memberships.create(user=self.member, role=ResourceRole.VIEWER)
        view = WorkflowViewSet.as_view({"delete": "destroy"})
        for restricted in (False, True):
            self.restrict(Capability.DELETE_WORKFLOWS_AND_DEPLOYMENTS, restricted)
            with self.subTest(restricted=restricted):
                response = self.call(
                    view, "delete", user=self.member, pk=stranger_owned.pk
                )
                self.assertEqual(response.status_code, 403)
        for viewset in (APIDeploymentViewSet, PipelineViewSet, WorkflowViewSet):
            with self.subTest(viewset=viewset.__name__):
                view = viewset()
                view.action = "destroy"
                self.assertTrue(
                    any(isinstance(p, IsOwner) for p in view.get_permissions())
                )

    def test_deletion_capability_applies_to_deployments_and_pipelines(self) -> None:
        self.restrict(Capability.DELETE_WORKFLOWS_AND_DEPLOYMENTS, True)
        for viewset in (APIDeploymentViewSet, PipelineViewSet, WorkflowViewSet):
            with self.subTest(viewset=viewset.__name__):
                view = viewset()
                view.action = "destroy"
                request = SimpleNamespace(user=self.member, method="DELETE")
                with self.assertRaisesMessage(
                    PermissionDenied,
                    "Delete workflows and deployments is restricted to organisation admins.",
                ):
                    for permission in view.get_permissions():
                        permission.has_permission(request, view)
