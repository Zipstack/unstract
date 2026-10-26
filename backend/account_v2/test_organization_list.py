"""Tests for GET organization: the role, member count and region it now carries."""

import secrets
from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TestCase, override_settings
from drf_spectacular.generators import SchemaGenerator
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2 import urls, views
from account_v2.authentication_controller import AuthenticationController
from account_v2.constants import AuthorizationErrorCode
from account_v2.dto import OrganizationData
from account_v2.models import Organization, User


class _AuthorizationError(Exception):
    code = AuthorizationErrorCode.USF
    data = {"domain": "example.com"}


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
        self.listed = [
            OrganizationData(
                id=o.organization_id, display_name=o.display_name, name=o.name
            )
            for o in (org_a, org_b)
        ]
        patcher = patch.object(
            self.controller.auth_service, "user_organizations", return_value=self.listed
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
        self.assertEqual(list(orgs[0]), ["id", "display_name", "name", "metadata"])
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

    def test_failure_outside_a_transaction_needs_no_savepoint(self) -> None:
        with (
            self.assertLogs("account_v2.authentication_controller", "ERROR"),
            patch(
                "account_v2.authentication_controller.connection",
                MagicMock(in_atomic_block=False),
            ),
            patch("account_v2.authentication_controller.transaction.atomic") as atomic,
            patch(
                "account_v2.authentication_controller.with_member_details",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 200)
        atomic.assert_not_called()

    def test_known_listing_error_is_412_with_code_and_logs_out(self) -> None:
        with (
            patch.object(
                self.controller.auth_service,
                "user_organizations",
                side_effect=_AuthorizationError(),
            ),
            patch.object(self.controller, "user_logout") as logout,
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 412)
        self.assertEqual(response.data, {"domain": "example.com", "code": "USF"})
        logout.assert_called_once()

    def test_unknown_listing_error_is_412_with_no_body(self) -> None:
        with (
            patch.object(
                self.controller.auth_service,
                "user_organizations",
                side_effect=RuntimeError("idp down"),
            ),
            patch.object(self.controller, "user_logout") as logout,
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 412)
        self.assertIsNone(response.data)
        logout.assert_called_once()

    def test_no_organizations_lists_none(self) -> None:
        with patch.object(
            self.controller.auth_service, "user_organizations", return_value=[]
        ):
            response = self.controller.user_organizations(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organizations"], [])

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
        self.assertEqual(set(body["required"]), {"domain", "code"})
        operation = schema["paths"]["/organization"]["get"]
        self.assertEqual(operation["operationId"], "organization_list")


@override_settings(REGION="US")
class OrganizationListEndpointTests(TestCase):
    """Through the URL and the auth middleware, as a browser calls it."""

    url = "/api/v1/organization"

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
            (org_b, self.caller, "user"),
            (org_b, _user("b1@example.com"), "admin"),
        ]:
            OrganizationMember.objects.create(organization=org, user=user, role=role)
        listed = [
            OrganizationData(
                id=o.organization_id, display_name=o.display_name, name=o.name
            )
            for o in (org_a, org_b)
        ]
        self.list_organizations = MagicMock(return_value=listed)
        for target, value in [
            (
                "account_v2.authentication_controller."
                "AuthenticationService.user_organizations",
                self.list_organizations,
            ),
            # OSS auth throughout, and no write to the shared cache.
            (
                "account_v2.custom_auth_middleware."
                "AuthenticationPluginRegistry.is_plugin_available",
                MagicMock(return_value=False),
            ),
            (
                "account_v2.authentication_controller."
                "AuthenticationPluginRegistry.is_plugin_available",
                MagicMock(return_value=False),
            ),
            (
                "account_v2.authentication_controller."
                "CacheService.set_user_organizations",
                MagicMock(),
            ),
        ]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(UserContext.set_organization_identifier, None)

    def test_signed_in_caller_gets_the_details(self) -> None:
        # Signed in to org-a, as the browser is when it opens the switcher.
        self.client.force_login(self.caller)
        session = self.client.session
        session["organization"] = "org-a"
        session.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        rows = [
            (org["id"], org["role"], org["member_count"], org["region"])
            for org in response.json()["organizations"]
        ]
        self.assertEqual(rows, [("org-a", "admin", 1, "US"), ("org-b", "user", 2, "US")])

    def test_anonymous_caller_is_refused(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "Unauthorized"})
        self.list_organizations.assert_not_called()
