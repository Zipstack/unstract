"""Tests for the role, member count and region added to the organization list."""

import secrets
from dataclasses import dataclass

from django.test import TestCase, override_settings
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2.dto import OrganizationData
from account_v2.models import Organization, User
from account_v2.organization_details import with_member_details


@dataclass
class CloudOrg:
    """Same fields as the cloud plugin's Auth0Organization."""

    id: str
    display_name: str
    name: str
    metadata: dict | None = None


def _user(email: str) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


def _org(slug: str, display_name: str) -> Organization:
    return Organization.objects.create(
        name=slug, display_name=display_name, organization_id=slug
    )


def _data(org: Organization) -> OrganizationData:
    return OrganizationData(
        id=org.organization_id, display_name=org.display_name, name=org.name
    )


class WithMemberDetailsTests(TestCase):
    def setUp(self) -> None:
        self.caller = _user("caller@example.com")
        self.org_a = _org("org-a", "Org A")
        self.org_b = _org("org-b", "Org B")
        self.org_c = _org("org-c", "Org C")
        members = [
            (self.org_a, self.caller, "admin"),
            (self.org_a, _user("a1@example.com"), "user"),
            (self.org_a, _user("a2@example.com"), "user"),
            (self.org_b, self.caller, "user"),
            (self.org_b, _user("b1@example.com"), "admin"),
            (self.org_c, _user("c1@example.com"), "admin"),
        ]
        for org, user, role in members:
            OrganizationMember.objects.create(organization=org, user=user, role=role)
        # The list is requested from inside one organization's context.
        UserContext.set_organization_identifier(self.org_a.organization_id)

    @override_settings(REGION="US")
    def test_role_count_and_region_per_organisation(self) -> None:
        rows = with_member_details([_data(self.org_a), _data(self.org_b)], self.caller)
        self.assertEqual(
            rows,
            [
                {
                    "id": "org-a",
                    "display_name": "Org A",
                    "name": "org-a",
                    "role": "admin",
                    "member_count": 3,
                    "region": "US",
                },
                {
                    "id": "org-b",
                    "display_name": "Org B",
                    "name": "org-b",
                    "role": "user",
                    "member_count": 2,
                    "region": "US",
                },
            ],
        )

    @override_settings(REGION=None)
    def test_region_absent_without_regions(self) -> None:
        rows = with_member_details([_data(self.org_a)], self.caller)
        self.assertNotIn("region", rows[0])

    @override_settings(REGION="US")
    def test_unknown_organisation_gets_no_details(self) -> None:
        unknown = OrganizationData(id="org-x", display_name="X", name="org-x")
        rows = with_member_details([unknown], self.caller)
        self.assertEqual(rows, [{"id": "org-x", "display_name": "X", "name": "org-x"}])

    @override_settings(REGION="US")
    def test_member_count_without_caller_membership(self) -> None:
        row = with_member_details([_data(self.org_c)], self.caller)[0]
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["region"], "US")
        self.assertNotIn("role", row)

    def test_two_queries_for_any_number_of_organisations(self) -> None:
        orgs = [_data(self.org_a), _data(self.org_b), _data(self.org_c)]
        with self.assertNumQueries(2):
            with_member_details(orgs, self.caller)

    def test_metadata_passes_through(self) -> None:
        cloud = CloudOrg(
            id="org-a", display_name="Org A", name="org-a", metadata={"k": "v"}
        )
        row = with_member_details([cloud], self.caller)[0]
        self.assertEqual(list(row)[:4], ["id", "display_name", "name", "metadata"])
        self.assertEqual(row["metadata"], {"k": "v"})

    def test_input_is_not_mutated(self) -> None:
        org = _data(self.org_a)
        with_member_details([org], self.caller)
        self.assertFalse(hasattr(org, "role"))
