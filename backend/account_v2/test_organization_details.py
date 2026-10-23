"""Tests for the role, member count and region added to the organization list."""

import secrets
from dataclasses import dataclass
from types import SimpleNamespace

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


def _bot(email: str) -> User:
    """A platform API key account."""
    bot = _user(email)
    bot.is_service_account = True
    bot.save()
    return bot


def _org(slug: str, display_name: str) -> Organization:
    return Organization.objects.create(
        name=slug, display_name=display_name, organization_id=slug
    )


def _data(org: Organization) -> OrganizationData:
    return OrganizationData(
        id=org.organization_id, display_name=org.display_name, name=org.name
    )


# REGION comes from the deployment's settings; start every test without one.
@override_settings(REGION=None)
class WithMemberDetailsTests(TestCase):
    def setUp(self) -> None:
        self.caller = _user("caller@example.com")
        self.org_a = _org("org-a", "Org A")
        self.org_b = _org("org-b", "Org B")
        self.org_c = _org("org-c", "Org C")
        members = [
            (self.org_a, self.caller, "admin"),
            # Other members hold a role the caller never has, so a leak shows.
            (self.org_a, _user("a1@example.com"), "reviewer"),
            (self.org_a, _user("a2@example.com"), "reviewer"),
            (self.org_b, self.caller, "user"),
            (self.org_b, _user("b1@example.com"), "reviewer"),
            (self.org_c, _user("c1@example.com"), "admin"),
        ]
        for org, user, role in members:
            OrganizationMember.objects.create(organization=org, user=user, role=role)
        # The list is requested from inside one organization's context.
        UserContext.set_organization_identifier(self.org_a.organization_id)
        self.addCleanup(UserContext.set_organization_identifier, None)

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
                    "metadata": None,
                    "role": "admin",
                    "member_count": 3,
                    "region": "US",
                },
                {
                    "id": "org-b",
                    "display_name": "Org B",
                    "name": "org-b",
                    "metadata": None,
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
        self.assertEqual(
            rows,
            [{"id": "org-x", "display_name": "X", "name": "org-x", "metadata": None}],
        )

    @override_settings(REGION="US")
    def test_member_count_without_caller_membership(self) -> None:
        row = with_member_details([_data(self.org_c)], self.caller)[0]
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["region"], "US")
        self.assertNotIn("role", row)

    def test_member_count_leaves_out_service_accounts(self) -> None:
        # Platform API keys get a member row; the members page doesn't list them.
        bot = _bot("key-bot@example.com")
        OrganizationMember.objects.create(organization=self.org_a, user=bot, role="user")
        row = with_member_details([_data(self.org_a)], self.caller)[0]
        self.assertEqual(row["member_count"], 3)

    @override_settings(REGION="US")
    def test_organisation_with_no_people_counts_zero(self) -> None:
        bot = _bot("only-bot@example.com")
        empty = _org("org-empty", "Empty")
        OrganizationMember.objects.create(organization=empty, user=bot, role="user")
        row = with_member_details([_data(empty)], self.caller)[0]
        self.assertEqual((row["member_count"], row["region"]), (0, "US"))

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

    def test_any_object_with_the_fields_works(self) -> None:
        # A plugin may hand back plain objects rather than dataclasses.
        org = SimpleNamespace(id="org-a", display_name="Org A", name="org-a")
        row = with_member_details([org], self.caller)[0]
        self.assertEqual(
            list(row), ["id", "display_name", "name", "metadata", "role", "member_count"]
        )
        self.assertIsNone(row["metadata"])

    def test_no_organizations(self) -> None:
        self.assertEqual(with_member_details([], self.caller), [])
