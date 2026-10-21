"""Tests for GET organization: the role, member count and region it now carries.

The drf-spectacular annotation on the view, with ReadMe.md, is the published
contract, so it is tested here too.
"""

import secrets
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from drf_spectacular.generators import SchemaGenerator
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2 import urls, views
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
        self.addCleanup(UserContext.set_organization_identifier, None)

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
        self.listed = listed
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
        self.assertEqual(list(org)[:4], ["id", "display_name", "name", "metadata"])

    @override_settings(REGION=None)
    def test_no_region_key_without_regions(self) -> None:
        orgs = self.controller.user_organizations(self.request).data["organizations"]
        self.assertTrue(all("region" not in org for org in orgs))

    def test_details_failure_still_lists_without_logout(self) -> None:
        with (
            self.assertLogs("account_v2.authentication_controller", "ERROR") as logs,
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
        self.assertIn(self.caller.user_id, logs.output[0])
        self.assertIn("2 organizations", logs.output[0])

    def test_failed_details_query_leaves_the_transaction_usable(self) -> None:
        # TestCase wraps each test in a transaction, as ATOMIC_REQUESTS would.
        def bad_query(*args: object) -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM no_such_table")

        with (
            self.assertLogs("account_v2.authentication_controller", "ERROR"),
            patch(
                "account_v2.authentication_controller.with_member_details",
                side_effect=bad_query,
            ),
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(pk=self.caller.pk).count(), 1)

    @override_settings(REGION=None)
    def test_view_returns_the_old_payload_plus_details(self) -> None:
        # Through the view, as v0 calls it: every old key and value unchanged.
        raw = APIRequestFactory().get("/api/v1/organization")
        force_authenticate(raw, user=self.caller)
        # org-x has no data on this deployment, as for another region's org.
        unknown = OrganizationData(id="org-x", display_name="X", name="org-x")
        with patch(
            "account_v2.authentication_controller.AuthenticationService.user_organizations",
            return_value=[*self.listed, unknown],
        ):
            response = views.get_organizations(raw)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "message": "success",
                "organizations": [
                    {
                        "id": "org-a",
                        "display_name": "Org A",
                        "name": "org-a",
                        "metadata": None,
                        "role": "admin",
                        "member_count": 3,
                    },
                    {
                        "id": "org-b",
                        "display_name": "Org B",
                        "name": "org-b",
                        "metadata": None,
                        "role": "user",
                        "member_count": 2,
                    },
                    {
                        "id": "org-x",
                        "display_name": "X",
                        "name": "org-x",
                        "metadata": None,
                    },
                ],
            },
        )
        # assertEqual ignores key order; the wire order is part of the contract.
        self.assertEqual(
            [list(org) for org in response.data["organizations"]],
            [
                ["id", "display_name", "name", "metadata", "role", "member_count"],
                ["id", "display_name", "name", "metadata", "role", "member_count"],
                ["id", "display_name", "name", "metadata"],
            ],
        )


class OrganizationListSchemaTests(TestCase):
    def test_schema_documents_the_fields(self) -> None:
        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        org = schema["components"]["schemas"]["GetOrganizationsResponse"]
        self.assertTrue({"role", "member_count", "region"} <= set(org["properties"]))
        self.assertEqual(set(org["required"]), {"id", "display_name", "name", "metadata"})
        for field in ("role", "member_count", "region"):
            self.assertNotIn("nullable", org["properties"][field])
        failed = schema["paths"]["/organization"]["get"]["responses"]["412"]
        body = failed["content"]["application/json"]["schema"]
        body = schema["components"]["schemas"][body["$ref"].rsplit("/", 1)[1]]
        self.assertEqual(set(body["properties"]), {"domain", "code"})
        operation_ids = {
            op.get("operationId")
            for path in schema["paths"].values()
            for op in path.values()
        }
        self.assertIn("organization_list", operation_ids)


@override_settings(REGION="US")
class OrganizationListEndpointTests(TestCase):
    """Through the URL and the auth middleware, as a browser calls it."""

    url = "/api/v1/organization"

    def setUp(self) -> None:
        self.caller = _user("caller@example.com")
        org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        OrganizationMember.objects.create(
            organization=org, user=self.caller, role="admin"
        )
        self.listed = [OrganizationData(id="org-a", display_name="Org A", name="org-a")]
        patcher = patch(
            "account_v2.authentication_controller.AuthenticationService.user_organizations",
            return_value=self.listed,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(UserContext.set_organization_identifier, None)

    def test_signed_in_caller_gets_the_details(self) -> None:
        self.client.force_login(self.caller)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        (org,) = response.json()["organizations"]
        self.assertEqual(
            (org["role"], org["member_count"], org["region"]), ("admin", 1, "US")
        )

    def test_anonymous_caller_is_refused(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(b"org-a", response.content)
