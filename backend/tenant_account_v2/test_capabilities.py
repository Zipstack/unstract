"""Organisation capability permissions (UN-4399).

The OSS auth service treats the ``admin`` role as admin, so the fixtures'
roles drive ``is_user_organization_admin`` directly.
"""

import importlib
import re
from types import SimpleNamespace
from unittest.mock import patch

from account_v2.authentication_controller import AuthenticationController
from account_v2.custom_exceptions import Forbidden
from account_v2.models import Organization
from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet
from api_v2.api_deployment_views import APIDeploymentViewSet
from api_v2.exceptions import UnauthorizedKey
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from connector_v2.views import ConnectorInstanceViewSet
from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator
from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.serializers import (
    GlobalApiDeploymentKeyUpdateSerializer,
)
from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet
from notification_v2.views import NotificationSettingsView
from permissions.permission import IsOwner
from permissions.roles import ResourceRole
from pipeline_v2.views import PipelineViewSet
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.views import PlatformApiKeyViewSet
from platform_audit.tests.base import AuditTestBase, make_user
from rest_framework.exceptions import PermissionDenied
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from tenant_account_v2 import urls as tenant_urls
from tenant_account_v2.capabilities import (
    SPECS,
    Capability,
    CapabilitySetting,
)
from tenant_account_v2.models import OrganizationMember
from tenant_account_v2.users_view import OrganizationUserViewSet
from tenant_account_v2.views import organization_capabilities, organization_settings

# Endpoints open to members before UN-4399; service accounts pass them.
MEMBER_OPEN = (
    Capability.CREATE_LLM_ADAPTERS,
    Capability.CREATE_CONNECTORS,
    Capability.CREATE_OTHER_ADAPTERS,
    Capability.DELETE_WORKFLOWS_AND_DEPLOYMENTS,
)
ENFORCED = [spec for spec in SPECS if spec.key in MEMBER_OPEN]


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

    def test_migration_database_defaults_match_the_model(self) -> None:
        # Django drops a column's database default after AddField, so the
        # migration sets them by hand; they must agree with the model.
        migration = importlib.import_module(
            "account_v2.migrations.0008_organization_capability_settings"
        ).Migration
        sql = " ".join(
            statement
            for op in migration.operations
            if op.__class__.__name__ == "RunSQL"
            for statement in op.sql
        )
        found = dict(re.findall(r"ALTER COLUMN (\w+) SET DEFAULT (true|false)", sql))
        new_fields = {
            spec.field
            for spec in SPECS
            if spec.field
            not in ("restrict_llm_adapter_creation", "restrict_connector_creation")
        }
        self.assertEqual(set(found), new_fields)
        for column, default in found.items():
            with self.subTest(column=column):
                self.assertEqual(
                    default == "true",
                    Organization._meta.get_field(column).default,
                )

    def test_schema_names_the_capability_enums_as_the_contract_does(self) -> None:
        schema = SchemaGenerator(patterns=tenant_urls.urlpatterns).get_schema(
            request=None, public=True
        )
        components = schema["components"]["schemas"]
        self.assertEqual(
            components["CapabilityKey"]["enum"], [c.value for c in Capability]
        )
        self.assertEqual(
            components["CapabilitySetting"]["enum"], ["admins_only", "any_member"]
        )
        # No field-named duplicate (KeyEnum, SettingEnum) of either.
        duplicated = [
            name
            for name, component in components.items()
            if name.endswith("Enum")
            and component.get("enum")
            in ([c.value for c in Capability], ["admins_only", "any_member"])
        ]
        self.assertEqual(duplicated, [])


class CapabilityTestBase(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.service_account = make_user("svc@example.com", is_service_account=True)
        # As platform_api.services gives every platform key's service account.
        OrganizationMember.objects.create(
            organization=self.org, user=self.service_account, role="user"
        )

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
        self.assertEqual(
            {k for k, r in rows.items() if not r["configurable"]},
            set(),
        )

    def test_admins_are_always_allowed(self) -> None:
        rows = self.capabilities(self.admin)
        self.assertTrue(all(r["allowed_for_me"] for r in rows.values()))

    def test_no_setting_blocks_service_accounts(self) -> None:
        for spec in SPECS:
            self.restrict(spec.key, True)
        rows = self.capabilities(self.service_account)
        self.assertTrue(all(r["allowed_for_me"] for r in rows.values()))

    def test_no_organization_is_a_404_in_the_standard_envelope(self) -> None:
        with patch(
            "tenant_account_v2.views.UserContext.get_organization", return_value=None
        ):
            for method, data in (
                ("get", None),
                ("patch", {"create_connectors": "admins_only"}),
            ):
                with self.subTest(method=method):
                    response = self.call(
                        organization_capabilities, method, user=self.admin, data=data
                    )
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.data["type"], "client_error")

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
            ({}, None),
        ):
            with self.subTest(body=str(body)):
                response = self.call(organization_capabilities, "patch", data=body)
                self.assertEqual(response.status_code, 400, response.data)
                self.org.refresh_from_db()
                self.assertFalse(self.org.restrict_connector_creation)

    def test_every_capability_accepts_both_settings(self) -> None:
        for spec in SPECS:
            for setting in ("any_member", "admins_only"):
                with self.subTest(key=spec.key.value, setting=setting):
                    response = self.call(
                        organization_capabilities, "patch", data={spec.key.value: setting}
                    )
                    self.assertEqual(response.status_code, 200, response.data)

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

    def test_before_is_read_from_the_row_not_the_requests_copy(self) -> None:
        # A concurrent request saved admins_only after this one loaded the
        # org, so this one's copy is stale. Lifting the restriction must still
        # be audited, from both endpoints.
        lifted = {
            "before": {"setting": "admins_only"},
            "after": {"setting": "any_member"},
        }
        for count, (view, data) in enumerate(
            (
                (organization_capabilities, {"create_connectors": "any_member"}),
                (organization_settings, {"restrict_connector_creation": False}),
            ),
            start=1,
        ):
            with self.subTest(view=view.__name__):
                stale = Organization.objects.get(pk=self.org.pk)
                self.restrict(Capability.CREATE_CONNECTORS, True)
                with patch(
                    "tenant_account_v2.views.UserContext.get_organization",
                    return_value=stale,
                ):
                    response = self.call(view, "patch", data=data)
                self.assertEqual(response.status_code, 200)
                events = self.events(action="capability.changed")
                self.assertEqual([e.changes for e in events], [lifted] * count)


class EnforcementMatrixTests(CapabilityTestBase):
    """Each enforced capability x {admins_only, any_member} x {admin, member,
    service account}.
    """

    def _allowed(self, key: Capability, user) -> bool:
        if key == Capability.CREATE_CONNECTORS:
            response = self._create_connector(user)
            if response.status_code == 403:
                return False
            self.assertEqual(response.status_code, 201, response.data)
            return True
        if key in (Capability.CREATE_LLM_ADAPTERS, Capability.CREATE_OTHER_ADAPTERS):
            adapter_type = "LLM" if key == Capability.CREATE_LLM_ADAPTERS else "EMBEDDING"
            response = self._create_adapter(user, adapter_type)
            if response.status_code == 403:
                return False
            self.assertEqual(response.status_code, 201, response.data)
            return True
        return self._may_delete_owned_workflow(user)

    def _create_connector(self, user):
        # The connector and payload shape of connector_v2's register test.
        # Creating stores the metadata without contacting the storage.
        view = ConnectorInstanceViewSet.as_view({"post": "create"})
        payload = {
            "connector_id": "minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
            "connector_name": f"minio-{user.pk}-{ConnectorInstance.objects.count()}",
            "connector_metadata": {
                "connectorName": "minio",
                "key": "access-key",
                "secret": "secret-key",
                "endpoint_url": "http://minio.invalid:9000",
                "region_name": "",
                "bucket": "bucket",
                "path": "/",
            },
        }
        return self.call(view, "post", user=user, data=payload)

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

    def test_editing_an_adapter_without_changing_its_type_stays_allowed(self) -> None:
        # The frontend always sends adapter_type on an edit.
        created = self._create_adapter(self.member, "LLM")
        self.assertEqual(created.status_code, 201, created.data)
        self.restrict(Capability.CREATE_LLM_ADAPTERS, True)
        view = AdapterInstanceViewSet.as_view({"patch": "partial_update"})
        with patch.object(AdapterInstance, "get_context_window_size", return_value=4096):
            response = self.call(
                view,
                "patch",
                user=self.member,
                data={"adapter_type": "LLM", "adapter_name": "renamed"},
                pk=created.data["id"],
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            AdapterInstance.objects.get(pk=created.data["id"]).adapter_name, "renamed"
        )

    # Real registry ids (unstract.sdk1 Adapterkit): the OpenAI LLM and the
    # OpenAI embedding adapter.
    OPENAI_LLM = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"
    OPENAI_EMBEDDING = "openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151"

    def _create_adapter_as(self, user, adapter_id: str, adapter_type: str):
        view = AdapterInstanceViewSet.as_view({"post": "create"})
        payload = {
            "adapter_id": adapter_id,
            "adapter_name": f"mislabelled-{AdapterInstance.objects.count()}",
            "adapter_type": adapter_type,
            "adapter_metadata": {"api_key": "sk-test", "model": "gpt-4o-mini"},
        }
        with patch.object(AdapterInstance, "get_context_window_size", return_value=4096):
            return self.call(view, "post", user=user, data=payload)

    def test_a_mislabelled_adapter_type_is_refused_both_ways(self) -> None:
        # Each label would pass the open capability while the id belongs to
        # the restricted one.
        for restricted, adapter_id, label in (
            (Capability.CREATE_LLM_ADAPTERS, self.OPENAI_LLM, "EMBEDDING"),
            (Capability.CREATE_OTHER_ADAPTERS, self.OPENAI_EMBEDDING, "LLM"),
        ):
            with self.subTest(restricted=restricted.value):
                self.restrict(Capability.CREATE_LLM_ADAPTERS, False)
                self.restrict(Capability.CREATE_OTHER_ADAPTERS, False)
                self.restrict(restricted, True)
                before = AdapterInstance.objects.count()
                response = self._create_adapter_as(self.member, adapter_id, label)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["errors"][0]["attr"], "adapter_type")
                self.assertEqual(AdapterInstance.objects.count(), before)

    def test_a_correctly_labelled_registry_adapter_is_created(self) -> None:
        response = self._create_adapter_as(self.member, self.OPENAI_LLM, "LLM")
        self.assertEqual(response.status_code, 201, response.data)

    def test_switching_adapter_id_to_another_types_provider_is_refused(self) -> None:
        created = self._create_adapter_as(self.member, self.OPENAI_EMBEDDING, "EMBEDDING")
        self.assertEqual(created.status_code, 201, created.data)
        self.restrict(Capability.CREATE_LLM_ADAPTERS, True)
        view = AdapterInstanceViewSet.as_view({"patch": "partial_update"})
        with patch.object(AdapterInstance, "get_context_window_size", return_value=4096):
            response = self.call(
                view,
                "patch",
                user=self.member,
                data={"adapter_id": self.OPENAI_LLM},
                pk=created.data["id"],
            )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            AdapterInstance.objects.get(pk=created.data["id"]).adapter_id,
            self.OPENAI_EMBEDDING,
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


class AdminOnlyEndpointsMatrixTests(CapabilityTestBase):
    """API keys, members and platform defaults: endpoints that were admin-only.
    'Any member' opens them to members; service accounts stay refused.
    """

    def setUp(self) -> None:
        super().setUp()
        self.colleague = make_user("colleague@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=self.colleague, role="user"
        )
        workflow = Workflow.objects.create(
            workflow_name="wf", organization=self.org, created_by=self.member
        )
        self.deployment = APIDeployment.objects.create(
            api_name="api",
            workflow=workflow,
            organization=self.org,
            created_by=self.member,
        )
        self.deployment.grant_owner(self.member)

    def _allowed(self, key: Capability, user) -> bool:
        if key == Capability.MANAGE_API_KEYS:
            view = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
            data = {
                "name": f"k-{user.pk}-{GlobalApiDeploymentKey.objects.count()}",
                "description": "ci",
                "allow_all_deployments": False,
                "api_deployments": [str(self.deployment.pk)],
            }
            response = self.call(view, "post", user=user, data=data)
            ok_status = 201
        elif key == Capability.MANAGE_MEMBERS:
            view = OrganizationUserViewSet.as_view(
                {"post": "assign_organization_role_to_user"}
            )
            response = self.call(
                view,
                "post",
                user=user,
                data={"email": "colleague@example.com", "role": "user"},
            )
            ok_status = 200
        else:
            view = NotificationSettingsView.as_view()
            response = self.call(
                view, "patch", user=user, data={"club_interval_seconds": 600}
            )
            ok_status = 200
        if response.status_code == 403:
            return False
        self.assertEqual(response.status_code, ok_status, getattr(response, "data", None))
        return True

    def test_matrix(self) -> None:
        for key in (
            Capability.MANAGE_API_KEYS,
            Capability.MANAGE_MEMBERS,
            Capability.CHANGE_PLATFORM_DEFAULTS,
        ):
            for restricted in (True, False):
                self.restrict(key, restricted)
                for name, user, expected in (
                    ("admin", self.admin, True),
                    ("member", self.member, not restricted),
                    ("service account", self.service_account, False),
                ):
                    with self.subTest(key=key.value, restricted=restricted, user=name):
                        self.assertEqual(self._allowed(key, user), expected)


class MemberManagementGuardrailTests(CapabilityTestBase):
    """With 'Any member', a member manages non-admin members only."""

    def setUp(self) -> None:
        super().setUp()
        self.restrict(Capability.MANAGE_MEMBERS, False)
        self.colleague = make_user("colleague@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=self.colleague, role="user"
        )
        self.assign = OrganizationUserViewSet.as_view(
            {"post": "assign_organization_role_to_user"}
        )

    def _assign(self, email: str, role: str):
        return self.call(
            self.assign, "post", user=self.member, data={"email": email, "role": role}
        )

    def test_a_member_cannot_grant_admin(self) -> None:
        response = self._assign("colleague@example.com", "admin")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OrganizationMember.objects.get(user=self.colleague).role, "user")

    def test_a_member_cannot_change_their_own_role(self) -> None:
        self.assertEqual(self._assign("member@example.com", "user").status_code, 403)

    def test_a_member_cannot_change_an_admins_role(self) -> None:
        # A second admin, so the last-admin guard is not what refuses it.
        second = make_user("second-admin@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=second, role="admin"
        )
        self.assertEqual(self._assign(second.email, "user").status_code, 403)
        self.assertEqual(OrganizationMember.objects.get(user=second).role, "admin")

    def test_a_member_cannot_revoke_admin(self) -> None:
        # A second admin, so the last-admin guard is not what refuses it.
        second = make_user("second-admin@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=second, role="admin"
        )
        view = OrganizationUserViewSet.as_view(
            {"delete": "remove_organization_role_from_user"}
        )
        response = self.call(
            view,
            "delete",
            user=self.member,
            data={"email": second.email, "role": "admin"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OrganizationMember.objects.get(user=second).role, "admin")

    def test_a_member_cannot_remove_a_role(self) -> None:
        # Removing someone's only role removes them, which stays admin-only.
        view = OrganizationUserViewSet.as_view(
            {"delete": "remove_organization_role_from_user"}
        )
        response = self.call(
            view,
            "delete",
            user=self.member,
            data={"email": "colleague@example.com", "role": "user"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            str(response.data["errors"][0]["detail"]),
            "Only admins can remove a member's role.",
        )

    def test_admins_invite_and_change_any_role_under_both_settings(self) -> None:
        controller = AuthenticationController()
        admin = OrganizationMember.objects.get(user=self.admin)
        target = OrganizationMember.objects.get(user=self.colleague)
        for restricted in (True, False):
            self.restrict(Capability.MANAGE_MEMBERS, restricted)
            with self.subTest(restricted=restricted):
                controller.authorize_invite(admin, ["admin", "user", None])
                controller.authorize_role_change(admin, target, "admin")
                controller.authorize_role_change(admin, target, "user", removing=True)

    def test_admins_only_refuses_members_removing_roles(self) -> None:
        self.restrict(Capability.MANAGE_MEMBERS, True)
        view = OrganizationUserViewSet.as_view(
            {"delete": "remove_organization_role_from_user"}
        )
        response = self.call(
            view,
            "delete",
            user=self.member,
            data={"email": "colleague@example.com", "role": "user"},
        )
        self.assertEqual(response.status_code, 403)

    def test_the_invite_endpoint_checks_before_inviting(self) -> None:
        controller = AuthenticationController()
        with patch.object(controller.auth_service, "invite_user") as invite:
            with self.assertRaises(Forbidden):
                controller.invite_user(
                    admin=self.member,
                    org_id=self.org.organization_id,
                    user_list=[{"email": "new@example.com", "role": "admin"}],
                    request=None,
                )
        invite.assert_not_called()

    def test_a_member_invites_with_the_user_role_only(self) -> None:
        controller = AuthenticationController()
        actor = OrganizationMember.objects.get(user=self.member)
        controller.authorize_invite(actor, ["user", None])
        with self.assertRaises(Forbidden):
            controller.authorize_invite(actor, ["user", "admin"])

    def test_a_plugin_that_names_no_member_roles_refuses_members(self) -> None:
        # A plugin that does not define the member-role hooks refuses
        # members: plugins need not inherit AuthenticationService.
        controller = AuthenticationController()
        controller.auth_service = SimpleNamespace(
            is_organization_admin=lambda member: False,
            is_admin_by_role=lambda role: role == "admin",
        )
        actor = OrganizationMember.objects.get(user=self.member)
        target = OrganizationMember.objects.get(user=self.colleague)
        with self.assertRaises(Forbidden):
            controller.authorize_invite(actor, ["user"])
        with self.assertRaises(Forbidden):
            controller.authorize_role_change(actor, target, "user")

    def test_admins_only_refuses_members_everything(self) -> None:
        self.restrict(Capability.MANAGE_MEMBERS, True)
        actor = OrganizationMember.objects.get(user=self.member)
        with self.assertRaises(Forbidden):
            AuthenticationController().authorize_invite(actor, ["user"])
        self.assertEqual(self._assign("colleague@example.com", "user").status_code, 403)


class PlatformApiKeyGuardrailTests(CapabilityTestBase):
    """Platform API keys stay admin-only even with 'Any member': each acts as
    a service account that bypasses per-resource sharing and ownership.
    """

    def setUp(self) -> None:
        super().setUp()
        self.restrict(Capability.MANAGE_API_KEYS, False)
        self.read = PlatformApiKey.objects.create(
            name="ci-read",
            permission=ApiKeyPermission.READ,
            organization=self.org,
            created_by=self.member,
        )

    def test_members_cannot_use_platform_api_keys(self) -> None:
        pk = {"pk": str(self.read.pk)}
        create = {"data": {"name": "m", "description": "d", "permission": "read"}}
        for action, method, kwargs in (
            ({"get": "list"}, "get", {}),
            ({"post": "create"}, "post", create),
            ({"get": "retrieve"}, "get", pk),
            ({"post": "rotate"}, "post", pk),
            ({"patch": "partial_update"}, "patch", {**pk, "data": {"is_active": False}}),
            ({"delete": "destroy"}, "delete", pk),
        ):
            with self.subTest(action=next(iter(action.values()))):
                view = PlatformApiKeyViewSet.as_view(action)
                response = self.call(view, method, user=self.member, **kwargs)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(PlatformApiKey.objects.count(), 1)


class GlobalDeploymentKeyGuardrailTests(CapabilityTestBase):
    """With 'Any member', a member only keys deployments they own."""

    def setUp(self) -> None:
        super().setUp()
        self.restrict(Capability.MANAGE_API_KEYS, False)
        workflow = Workflow.objects.create(
            workflow_name="wf", organization=self.org, created_by=self.admin
        )
        self.mine = APIDeployment.objects.create(
            api_name="mine",
            workflow=workflow,
            organization=self.org,
            created_by=self.member,
        )
        self.mine.grant_owner(self.member)
        self.theirs = APIDeployment.objects.create(
            api_name="theirs",
            workflow=workflow,
            organization=self.org,
            created_by=self.admin,
        )
        self.theirs.grant_owner(self.admin)
        self.all_key = GlobalApiDeploymentKey.objects.create(
            name="admin-all",
            allow_all_deployments=True,
            organization=self.org,
            created_by=self.admin,
        )

    def _create(self, data: dict):
        view = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
        return self.call(
            view,
            "post",
            user=self.member,
            data={"name": "k", "description": "ci", **data},
        )

    def test_a_member_cannot_create_an_allow_all_key(self) -> None:
        response = self._create({"allow_all_deployments": True, "api_deployments": []})
        self.assertEqual(response.status_code, 403)

    def test_a_member_cannot_key_a_deployment_they_do_not_own(self) -> None:
        response = self._create(
            {"allow_all_deployments": False, "api_deployments": [str(self.theirs.pk)]}
        )
        self.assertEqual(response.status_code, 403)

    def test_a_member_may_grant_their_own_deployment(self) -> None:
        response = self._create(
            {"allow_all_deployments": False, "api_deployments": [str(self.mine.pk)]}
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_a_member_rotates_only_keys_they_created(self) -> None:
        own = GlobalApiDeploymentKey.objects.create(
            name="own",
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        own.api_deployments.add(self.mine)
        admins = GlobalApiDeploymentKey.objects.create(
            name="admins", organization=self.org, created_by=self.admin
        )
        admins.api_deployments.add(self.mine)
        rotate = GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"})
        response = self.call(rotate, "post", user=self.member, pk=str(own.pk))
        self.assertEqual(response.status_code, 200, response.data)
        key_before = admins.key
        response = self.call(rotate, "post", user=self.member, pk=str(admins.pk))
        self.assertEqual(response.status_code, 403)
        admins.refresh_from_db()
        self.assertEqual(admins.key, key_before)

    def test_a_member_cannot_edit_or_delete_their_own_key(self) -> None:
        own = GlobalApiDeploymentKey.objects.create(
            name="own",
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        own.api_deployments.add(self.mine)
        update = GlobalApiDeploymentKeyViewSet.as_view({"patch": "partial_update"})
        response = self.call(
            update,
            "patch",
            user=self.member,
            pk=str(own.pk),
            data={"allow_all_deployments": True},
        )
        self.assertEqual(response.status_code, 403)
        destroy = GlobalApiDeploymentKeyViewSet.as_view({"delete": "destroy"})
        response = self.call(destroy, "delete", user=self.member, pk=str(own.pk))
        self.assertEqual(response.status_code, 403)
        own.refresh_from_db()
        self.assertFalse(own.allow_all_deployments)

    def test_a_member_cannot_view_or_rotate_their_own_key_once_it_reaches_further(
        self,
    ) -> None:
        # Their own key, later widened by an admin: same rule as creating it.
        own = GlobalApiDeploymentKey.objects.create(
            name="own",
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        own.api_deployments.add(self.mine, self.theirs)
        rotate = GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"})
        response = self.call(rotate, "post", user=self.member, pk=str(own.pk))
        self.assertEqual(response.status_code, 403)

    def test_a_member_cannot_view_or_rotate_an_allow_all_key(self) -> None:
        # Their own key, so only the allow-all rule can refuse it.
        own_all = GlobalApiDeploymentKey.objects.create(
            name="own-all",
            allow_all_deployments=True,
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        for action, method in (
            ({"get": "retrieve"}, "get"),
            ({"post": "rotate"}, "post"),
        ):
            with self.subTest(action=method):
                view = GlobalApiDeploymentKeyViewSet.as_view(action)
                response = self.call(view, method, user=self.member, pk=str(own_all.pk))
                self.assertEqual(response.status_code, 403)

    def test_a_member_lists_and_views_only_their_own_keys(self) -> None:
        own = GlobalApiDeploymentKey.objects.create(
            name="own",
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        own.api_deployments.add(self.mine)
        listing = GlobalApiDeploymentKeyViewSet.as_view({"get": "list"})
        response = self.call(listing, "get", user=self.member)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["name"] for row in response.data], ["own"])
        response = self.call(listing, "get", user=self.admin)
        self.assertEqual(
            sorted(row["name"] for row in response.data), ["admin-all", "own"]
        )
        retrieve = GlobalApiDeploymentKeyViewSet.as_view({"get": "retrieve"})
        response = self.call(retrieve, "get", user=self.member, pk=str(own.pk))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["key"], str(own.key))

    def test_a_members_list_hides_deployments_they_no_longer_own(self) -> None:
        own = GlobalApiDeploymentKey.objects.create(
            name="own",
            organization=self.org,
            created_by=self.member,
            created_by_member=True,
        )
        own.api_deployments.add(self.mine)
        listing = GlobalApiDeploymentKeyViewSet.as_view({"get": "list"})

        def listed(user) -> list[str]:
            response = self.call(listing, "get", user=user)
            self.assertEqual(response.status_code, 200, response.data)
            row = next(r for r in response.data if r["name"] == "own")
            return [d["id"] for d in row["api_deployments"]]

        self.assertEqual(listed(self.member), [str(self.mine.pk)])
        # Still a viewer: viewing is not owning.
        self.mine.memberships.filter(user=self.member).update(role=ResourceRole.VIEWER)
        self.assertEqual(listed(self.member), [])
        # The link itself stays, and an admin still sees it.
        self.assertEqual(listed(self.admin), [str(self.mine.pk)])

    def _member_key(self) -> GlobalApiDeploymentKey:
        response = self._create(
            {"allow_all_deployments": False, "api_deployments": [str(self.mine.pk)]}
        )
        self.assertEqual(response.status_code, 201, response.data)
        return GlobalApiDeploymentKey.objects.get(pk=response.data["id"])

    def _authenticates(self, key: GlobalApiDeploymentKey, deployment=None) -> bool:
        try:
            KeyHelper.validate_global_api_deployment_key(
                api_key=str(key.key), api_deployment=deployment or self.mine
            )
        except UnauthorizedKey:
            return False
        return True

    def test_a_members_key_stops_working_when_they_stop_owning_it(self) -> None:
        key = self._member_key()
        self.assertTrue(key.created_by_member)
        self.assertTrue(self._authenticates(key))
        # Still a viewer: viewing is not owning.
        self.mine.memberships.filter(user=self.member).update(role=ResourceRole.VIEWER)
        self.assertFalse(self._authenticates(key))

    def test_a_members_key_stops_working_when_they_leave(self) -> None:
        key = self._member_key()
        OrganizationMember.objects.filter(user=self.member).delete()
        self.assertFalse(self._authenticates(key))

    def test_an_admins_key_does_not_depend_on_its_creator(self) -> None:
        view = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
        response = self.call(
            view,
            "post",
            user=self.admin,
            data={
                "name": "admins",
                "description": "ci",
                "allow_all_deployments": False,
                "api_deployments": [str(self.mine.pk)],
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        key = GlobalApiDeploymentKey.objects.get(pk=response.data["id"])
        self.assertFalse(key.created_by_member)
        OrganizationMember.objects.filter(user=self.admin).delete()
        self.assertTrue(self._authenticates(key))

    def _admin_patch(self, key: GlobalApiDeploymentKey, data: dict):
        view = GlobalApiDeploymentKeyViewSet.as_view({"patch": "partial_update"})
        response = self.call(view, "patch", user=self.admin, pk=str(key.pk), data=data)
        key.refresh_from_db()
        return response

    def test_an_admin_cannot_widen_a_members_key(self) -> None:
        key = self._member_key()
        for data in (
            {"allow_all_deployments": True},
            {"api_deployments": [str(self.mine.pk), str(self.theirs.pk)]},
        ):
            with self.subTest(data=data):
                response = self._admin_patch(key, data)
                self.assertEqual(response.status_code, 400)
                self.assertIn(next(iter(data)), str(response.data))
                self.assertFalse(key.allow_all_deployments)
                self.assertEqual(list(key.api_deployments.all()), [self.mine])
        # What the edit form sends for a description-only edit.
        response = self._admin_patch(
            key,
            {
                "description": "renamed",
                "allow_all_deployments": False,
                "api_deployments": [str(self.mine.pk)],
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(key.description, "renamed")
        self.assertTrue(key.created_by_member)
        self.assertTrue(response.data["created_by_member"])

    def test_an_admin_can_still_edit_a_stranded_members_key(self) -> None:
        form = {
            "description": "renamed",
            "allow_all_deployments": False,
            "api_deployments": [str(self.mine.pk)],
        }
        key = self._member_key()
        self.mine.memberships.filter(user=self.member).delete()
        self.assertEqual(self._admin_patch(key, form).status_code, 200)
        key.created_by = None
        key.save(update_fields=["created_by"])
        self.assertEqual(
            self._admin_patch(key, {**form, "description": "again"}).status_code, 200
        )
        # Still nothing may be added.
        response = self._admin_patch(
            key, {"api_deployments": [str(self.mine.pk), str(self.theirs.pk)]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("api_deployments", str(response.data))
        self.assertEqual(list(key.api_deployments.all()), [self.mine])

    def _second_deployment(self) -> APIDeployment:
        workflow = Workflow.objects.create(
            workflow_name="wf2", organization=self.org, created_by=self.member
        )
        return APIDeployment.objects.create(
            api_name="mine2",
            workflow=workflow,
            organization=self.org,
            created_by=self.member,
        )

    def test_an_admin_may_add_a_deployment_the_creator_owns(self) -> None:
        mine2 = self._second_deployment()
        mine2.grant_owner(self.member)
        key = self._member_key()
        response = self._admin_patch(
            key, {"api_deployments": [str(self.mine.pk), str(mine2.pk)]}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            {d.pk for d in key.api_deployments.all()}, {self.mine.pk, mine2.pk}
        )
        self.assertTrue(self._authenticates(key, mine2))

    def test_a_creator_who_left_cannot_have_deployments_added(self) -> None:
        mine2 = self._second_deployment()
        mine2.grant_owner(self.member)
        key = self._member_key()
        OrganizationMember.objects.filter(user=self.member).delete()
        response = self._admin_patch(
            key, {"api_deployments": [str(self.mine.pk), str(mine2.pk)]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("api_deployments", str(response.data))

    def test_a_member_cannot_open_another_members_key(self) -> None:
        # Both own the deployment, and the other key is a member's key: only
        # the creator check can refuse it.
        colleague = make_user("colleague@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=colleague, role="user"
        )
        self.mine.grant_owner(colleague)
        theirs = GlobalApiDeploymentKey.objects.create(
            name="colleague",
            organization=self.org,
            created_by=colleague,
            created_by_member=True,
        )
        theirs.api_deployments.add(self.mine)
        key_before = theirs.key
        for action, method in (
            ({"get": "retrieve"}, "get"),
            ({"post": "rotate"}, "post"),
        ):
            with self.subTest(action=method):
                response = self.call(
                    GlobalApiDeploymentKeyViewSet.as_view(action),
                    method,
                    user=self.member,
                    pk=str(theirs.pk),
                )
                self.assertEqual(response.status_code, 403)
        theirs.refresh_from_db()
        self.assertEqual(theirs.key, key_before)

    def test_a_demoted_admin_cannot_view_or_rotate_their_admin_era_key(self) -> None:
        view = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
        response = self.call(
            view,
            "post",
            user=self.admin,
            data={
                "name": "admin-era",
                "description": "ci",
                "allow_all_deployments": False,
                "api_deployments": [str(self.theirs.pk)],
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        key = GlobalApiDeploymentKey.objects.get(pk=response.data["id"])
        self.assertFalse(key.created_by_member)
        # Demoted, still owning the key's deployment.
        OrganizationMember.objects.filter(user=self.admin).update(role="user")
        demoted = type(self.admin).objects.get(pk=self.admin.pk)
        for action, method in (
            ({"get": "retrieve"}, "get"),
            ({"post": "rotate"}, "post"),
        ):
            with self.subTest(action=method):
                response = self.call(
                    GlobalApiDeploymentKeyViewSet.as_view(action),
                    method,
                    user=demoted,
                    pk=str(key.pk),
                )
                self.assertEqual(response.status_code, 403)
        listing = self.call(
            GlobalApiDeploymentKeyViewSet.as_view({"get": "list"}), "get", user=demoted
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertNotIn("admin-era", [row["name"] for row in listing.data])

    def test_execution_checks_a_members_key_with_its_creators_rights(self) -> None:
        # The execute view hands the authorising global key to the request
        # serializer, which holds a member's key to its creator's profiles.
        from api_v2.api_deployment_views import DeploymentExecution

        key = self._member_key()
        seen = {}

        class Stop(Exception):
            pass

        def capture(*args, **kwargs):
            seen.update(kwargs["context"])
            raise Stop

        request = self.factory.post(
            "/", {}, format="json", HTTP_AUTHORIZATION=f"Bearer {key.key}"
        )
        with patch("api_v2.api_deployment_views.ExecutionRequestSerializer", capture):
            # The view's error handler turns Stop into a 500; only the
            # captured serializer context matters here.
            DeploymentExecution.as_view()(
                request, org_name=self.org.organization_id, api_name="mine"
            )
        self.assertEqual(seen["global_key"].pk, key.pk)
        self.assertTrue(seen["global_key"].created_by_member)

    def test_a_creator_promoted_to_admin_keeps_their_keys_working(self) -> None:
        key = self._member_key()
        self.mine.memberships.filter(user=self.member).delete()
        OrganizationMember.objects.filter(user=self.member).update(role="admin")
        key = GlobalApiDeploymentKey.objects.get(pk=key.pk)
        self.assertTrue(self._authenticates(key))

    def test_a_member_cannot_key_a_deployment_they_only_view(self) -> None:
        self.theirs.memberships.create(user=self.member, role=ResourceRole.VIEWER)
        response = self._create(
            {"allow_all_deployments": False, "api_deployments": [str(self.theirs.pk)]}
        )
        self.assertEqual(response.status_code, 403)
        picker = GlobalApiDeploymentKeyViewSet.as_view({"get": "deployments"})
        names = [
            row["api_name"] for row in self.call(picker, "get", user=self.member).data
        ]
        self.assertEqual(names, ["mine"])
        # A key that covered it (an admin's grant before) stops working for it.
        key = self._member_key()
        key.api_deployments.add(self.theirs)
        self.assertFalse(self._authenticates(key, self.theirs))

    def test_an_edit_does_not_undo_a_rotate_made_meanwhile(self) -> None:
        key = self._member_key()
        stale = GlobalApiDeploymentKey.objects.get(pk=key.pk)
        rotate = GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"})
        response = self.call(rotate, "post", user=self.member, pk=str(key.pk))
        self.assertEqual(response.status_code, 200, response.data)
        rotated = response.data["key"]
        request = SimpleNamespace(user=self.admin)
        serializer = GlobalApiDeploymentKeyUpdateSerializer(
            stale,
            data={"description": "edited"},
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        key.refresh_from_db()
        self.assertEqual(str(key.key), str(rotated))
        self.assertEqual(key.description, "edited")

    def test_a_member_picks_from_their_own_deployments(self) -> None:
        view = GlobalApiDeploymentKeyViewSet.as_view({"get": "deployments"})
        response = self.call(view, "get", user=self.member)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["api_name"] for row in response.data], ["mine"])
