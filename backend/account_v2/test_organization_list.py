"""Tests for GET organization: the role, member count and region it now carries.

The drf-spectacular annotation on the view, with ReadMe.md, is the published
contract, so it is tested here too.
"""

import secrets
from unittest.mock import patch

from django.test import TestCase, override_settings
from drf_spectacular.generators import SchemaGenerator
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2 import urls
from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import OrganizationData
from account_v2.models import Organization, User


def _user(email: str) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class OrganizationListTests(TestCase):
    def setUp(self) -> None:
        self.caller = _user("caller@example.com")
        org_a = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        org_b = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        for org, user, role in [
            (org_a, self.caller, "admin"),
            (org_a, _user("a1@example.com"), "user"),
            (org_a, _user("a2@example.com"), "user"),
            (org_b, self.caller, "user"),
            (org_b, _user("b1@example.com"), "admin"),
        ]:
            OrganizationMember.objects.create(organization=org, user=user, role=role)
        UserContext.set_organization_identifier(org_a.organization_id)

        for target, kwargs in [
            (
                "account_v2.authentication_controller."
                "AuthenticationPluginRegistry.is_plugin_available",
                {"return_value": False},
            ),
            (
                "account_v2.authentication_controller."
                "CacheService.set_user_organizations",
                {},
            ),
        ]:
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.controller = AuthenticationController()
        listed = [
            OrganizationData(
                id=o.organization_id, display_name=o.display_name, name=o.name
            )
            for o in (org_a, org_b)
        ]
        patcher = patch.object(
            self.controller.auth_service, "user_organizations", return_value=listed
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        raw = APIRequestFactory().get("/api/v1/organization")
        force_authenticate(raw, user=self.caller)
        self.request = Request(raw)

    @override_settings(REGION="US")
    def test_list_carries_the_new_fields(self) -> None:
        response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 200)
        a, b = response.data["organizations"]
        self.assertEqual((a["role"], a["member_count"], a["region"]), ("admin", 3, "US"))
        self.assertEqual((b["role"], b["member_count"], b["region"]), ("user", 2, "US"))

    def test_existing_fields_keep_their_order(self) -> None:
        org = self.controller.user_organizations(self.request).data["organizations"][0]
        self.assertEqual(list(org)[:3], ["id", "display_name", "name"])

    @override_settings(REGION=None)
    def test_no_region_key_without_regions(self) -> None:
        orgs = self.controller.user_organizations(self.request).data["organizations"]
        self.assertTrue(all("region" not in org for org in orgs))

    def test_details_failure_still_lists_without_logout(self) -> None:
        with (
            patch(
                "account_v2.authentication_controller.with_member_details",
                side_effect=RuntimeError("boom"),
            ),
            patch.object(self.controller, "user_logout") as logout,
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 200)
        orgs = response.data["organizations"]
        self.assertEqual([org["id"] for org in orgs], ["org-a", "org-b"])
        self.assertNotIn("role", orgs[0])
        logout.assert_not_called()


class OrganizationListSchemaTests(TestCase):
    def test_schema_documents_the_fields(self) -> None:
        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        org = schema["components"]["schemas"]["GetOrganizationsResponse"]
        self.assertTrue({"role", "member_count", "region"} <= set(org["properties"]))
        self.assertEqual(set(org["required"]), {"id", "display_name", "name"})
        operation_ids = {
            op.get("operationId")
            for path in schema["paths"].values()
            for op in path.values()
        }
        self.assertIn("organization_list", operation_ids)
