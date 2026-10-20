"""A user never receives a result they cannot open, per resource type.

Each type is checked against the same roles its list honours: owner,
co-owner, direct viewer, group share, org share, admin and service account
see it; an org member without access and another org's resources do not.
"""

from account_v2.models import Organization
from adapter_processor_v2.models import AdapterInstance
from django.test import TestCase
from permissions.permission import IsFrictionLessAdapter
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin, make_user
from pipeline_v2.models import Pipeline
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from tenant_account_v2.models import GroupMembership, OrganizationGroup, OrganizationMember
from tenant_account_v2.sharing_helpers import set_resource_share_groups
from utils.user_context import UserContext

from global_search.constants import OSSSearchType
from global_search.tests.base import (
    OSS_BUILDERS,
    _pipeline,
    build_adapter,
    result_ids,
    search,
)

QUERY = "zeta"


class SearchVisibilityTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.group_member = make_user("grouped@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=self.group_member, role="user"
        )
        self.group = OrganizationGroup.objects.create(
            organization=self.org, name="Team", created_by=self.owner
        )
        GroupMembership.objects.create(group=self.group, user=self.group_member)
        self.service_account = make_user("svc@example.com", is_service_account=True)

    def _private(self, type_key: str):
        item = OSS_BUILDERS[type_key](self.org, self.owner, f"{QUERY}-{type_key}")
        item.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        item.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        item.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        return item

    def _found(self, user, type_key: str, item) -> bool:
        response = search(user, q=QUERY, types=type_key, limit=20)
        self.assertEqual(response.status_code, 200)
        return str(item.pk) in result_ids(response, type_key)

    def test_each_type_follows_its_list_visibility(self) -> None:
        for type_key in OSS_BUILDERS:
            with self.subTest(type=type_key):
                item = self._private(type_key)

                for user in (self.owner, self.coowner, self.viewer, self.admin):
                    self.assertTrue(self._found(user, type_key, item), user.email)
                self.assertTrue(self._found(self.service_account, type_key, item))
                for user in (self.outsider, self.group_member):
                    self.assertFalse(self._found(user, type_key, item), user.email)

                set_resource_share_groups(item, [self.group.id])
                self.assertTrue(self._found(self.group_member, type_key, item))
                self.assertFalse(self._found(self.outsider, type_key, item))

                item.shared_to_org = True
                item.save()
                self.assertTrue(self._found(self.outsider, type_key, item))

    def test_other_orgs_resources_never_appear(self) -> None:
        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        UserContext.set_organization_identifier(other.organization_id)
        foreign = {}
        for type_key, build in OSS_BUILDERS.items():
            item = build(other, self.stranger, f"{QUERY}-{type_key}")
            item.shared_to_org = True
            item.save()
            foreign[type_key] = str(item.pk)
        UserContext.set_organization_identifier(self.org.organization_id)

        for user in (self.admin, self.service_account, self.outsider):
            response = search(user, q=QUERY, limit=20)
            leaked = set(result_ids(response)) & set(foreign.values())
            self.assertEqual(leaked, set(), user.email)

    def test_frictionless_adapters_are_never_returned(self) -> None:
        # Listed so any member can delete one, but adapter retrieve refuses
        # them for everyone, admins included; search would only lead to a 403.
        adapter = build_adapter(
            self.org, self.owner, f"{QUERY}-frictionless", is_friction_less=True
        )
        adapter.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        for user in (self.owner, self.admin, self.service_account, self.outsider):
            self.assertFalse(
                self._found(user, OSSSearchType.ADAPTER, adapter), user.email
            )

    def test_adapter_route_follows_who_may_edit_it(self) -> None:
        # adapter.detail is gated like adapter retrieve: owners, co-owners,
        # admins and service accounts. Anyone else who can list the adapter
        # opens the read-only adapter.info.
        adapter = self._private(OSSSearchType.ADAPTER)
        set_resource_share_groups(adapter, [self.group.id])
        adapter.shared_to_org = True
        adapter.save()
        expected = {
            self.owner: "adapter.detail",
            self.coowner: "adapter.detail",
            self.admin: "adapter.detail",
            self.service_account: "adapter.detail",
            self.viewer: "adapter.info",
            self.group_member: "adapter.info",
            self.outsider: "adapter.info",
        }
        for user, route_key in expected.items():
            with self.subTest(user=user.email):
                response = search(
                    user, q=QUERY, types=OSSSearchType.ADAPTER, limit=20
                )
                (result,) = response.data["groups"][0]["results"]
                self.assertEqual(
                    result["route"],
                    {
                        "key": route_key,
                        "params": {
                            "id": str(adapter.pk),
                            "adapter_type": adapter.adapter_type,
                        },
                    },
                )
                # Tied to the real gate, so the two rules cannot drift apart.
                self.assertEqual(
                    route_key == "adapter.detail", self._may_retrieve(user, adapter)
                )

    @staticmethod
    def _may_retrieve(user, adapter) -> bool:
        request = Request(APIRequestFactory().get("/"))
        request.user = user
        return IsFrictionLessAdapter().has_object_permission(
            request, None, AdapterInstance.objects.get(pk=adapter.pk)
        )

    def test_no_op_adapters_are_never_returned(self) -> None:
        adapter = build_adapter(
            self.org,
            self.owner,
            f"{QUERY}-noop",
            adapter_id="noOpLlm|f673a5a2-90f9-40f5-94c0-9fbc663b7553",
            shared_to_org=True,
        )
        self.assertFalse(self._found(self.admin, OSSSearchType.ADAPTER, adapter))

    def test_default_and_app_pipelines_are_never_returned(self) -> None:
        for pipeline_type in (Pipeline.PipelineType.DEFAULT, Pipeline.PipelineType.APP):
            with self.subTest(pipeline_type=pipeline_type.value):
                pipeline = _pipeline(pipeline_type)(
                    self.org, self.owner, f"{QUERY}-{pipeline_type}"
                )
                response = search(self.admin, q=QUERY, limit=20)
                self.assertNotIn(str(pipeline.pk), result_ids(response))
