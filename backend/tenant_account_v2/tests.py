"""Tests for org-scoped group sharing (UN-2977 / mfbt UNS-612).

Covers the security-sensitive surface: the ``ShareAuthorizationService``
authorization matrix (incl. atomicity), the membership/orphan cleanup signals,
``set_resource_share_groups`` diff semantics, the ``for_user()`` group-visibility
filter, and the shareable-resource registry.

Admin resolution (``is_org_admin`` / ``is_user_organization_admin``) is patched
to a deterministic predicate so these tests exercise the sharing logic itself,
not the active authentication plugin's role handling.
"""

from unittest.mock import patch

from account_v2.models import Organization, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
    ResourceGroupShare,
)
from tenant_account_v2.shareable_resources import SHAREABLE_RESOURCES
from tenant_account_v2.sharing_helpers import (
    ShareAuthorizationService,
    get_resource_share_groups,
    set_resource_share_groups,
)


def _make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(
        username=email, email=email, password="irrelevant", **kwargs
    )


def _shared_group_ids(resource) -> set[int]:
    return set(get_resource_share_groups(resource).values_list("id", flat=True))


def _shared_user_ids(resource) -> set[int]:
    return set(resource.shared_users.values_list("id", flat=True))


class GroupSharingTestBase(TestCase):
    """Shared fixtures: one org with an owner, a group member, and an outsider."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)

        self.owner = _make_user("owner@example.com")
        self.member = _make_user("member@example.com")  # belongs to self.group
        self.outsider = _make_user("outsider@example.com")  # org member, no group
        self.admin = _make_user("admin@example.com")
        for user, role in (
            (self.owner, "user"),
            (self.member, "user"),
            (self.outsider, "user"),
            (self.admin, "admin"),
        ):
            OrganizationMember.objects.create(organization=self.org, user=user, role=role)

        self.group = OrganizationGroup.objects.create(
            organization=self.org, name="Team", created_by=self.owner
        )
        GroupMembership.objects.create(group=self.group, user=self.member)

        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )


class ShareAuthorizationServiceTests(GroupSharingTestBase):
    """The authorization matrix from the UN-2977 plan."""

    def setUp(self) -> None:
        super().setUp()
        # Deterministic admin predicate — only ``self.admin`` is an admin.
        patcher = patch(
            "tenant_account_v2.sharing_helpers.is_org_admin",
            side_effect=lambda user: getattr(user, "email", None) == self.admin.email,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _authorize(self, actor, desired) -> None:
        ShareAuthorizationService.authorize_and_commit(
            actor=actor, resource=self.workflow, desired=desired
        )

    def test_owner_can_add_and_remove_users(self) -> None:
        self._authorize(self.owner, {"shared_users": [self.outsider.id]})
        self.assertEqual(_shared_user_ids(self.workflow), {self.outsider.id})
        self._authorize(self.owner, {"shared_users": []})
        self.assertEqual(_shared_user_ids(self.workflow), set())

    def test_owner_can_add_group_and_toggle_org(self) -> None:
        self._authorize(
            self.owner, {"shared_groups": [self.group.id], "shared_to_org": True}
        )
        self.assertEqual(_shared_group_ids(self.workflow), {self.group.id})
        self.workflow.refresh_from_db()
        self.assertTrue(self.workflow.shared_to_org)

    def test_admin_can_remove_users(self) -> None:
        self.workflow.shared_users.add(self.member)
        self._authorize(self.admin, {"shared_users": []})
        self.assertEqual(_shared_user_ids(self.workflow), set())

    def test_unprivileged_cannot_remove_users(self) -> None:
        self.workflow.shared_users.add(self.member, self.outsider)
        with self.assertRaises(PermissionDenied):
            # outsider (a shared user, not owner/admin) tries to drop member
            self._authorize(self.outsider, {"shared_users": [self.outsider.id]})
        self.assertEqual(
            _shared_user_ids(self.workflow), {self.member.id, self.outsider.id}
        )

    def test_unprivileged_cannot_toggle_org(self) -> None:
        with self.assertRaises(PermissionDenied):
            self._authorize(self.outsider, {"shared_to_org": True})
        self.workflow.refresh_from_db()
        self.assertFalse(self.workflow.shared_to_org)

    def test_group_member_can_add_only_their_groups(self) -> None:
        other_group = OrganizationGroup.objects.create(
            organization=self.org, name="Other", created_by=self.owner
        )
        # member belongs to self.group → allowed
        self._authorize(self.member, {"shared_groups": [self.group.id]})
        self.assertEqual(_shared_group_ids(self.workflow), {self.group.id})
        # member is not in other_group → denied
        with self.assertRaises(PermissionDenied):
            self._authorize(
                self.member, {"shared_groups": [self.group.id, other_group.id]}
            )

    def test_service_account_bypasses_authorization(self) -> None:
        svc = _make_user("svc@example.com", is_service_account=True)
        self._authorize(svc, {"shared_to_org": True})
        self.workflow.refresh_from_db()
        self.assertTrue(self.workflow.shared_to_org)

    def test_authorize_is_atomic_on_partial_denial(self) -> None:
        """A denial on any axis must leave every axis uncommitted."""
        self.workflow.shared_users.add(self.outsider)
        with self.assertRaises(PermissionDenied):
            # users add is allowed for a shared user, but the org toggle isn't
            self._authorize(
                self.outsider,
                {
                    "shared_users": [self.outsider.id, self.member.id],
                    "shared_to_org": True,
                },
            )
        self.assertNotIn(self.member.id, _shared_user_ids(self.workflow))
        self.workflow.refresh_from_db()
        self.assertFalse(self.workflow.shared_to_org)


class SetResourceShareGroupsTests(GroupSharingTestBase):
    """Polymorphic ``.set()``-style diff semantics + cross-org guard."""

    def _count(self) -> int:
        return ResourceGroupShare.objects.filter(
            content_type=ContentType.objects.get_for_model(Workflow),
            object_id=str(self.workflow.pk),
        ).count()

    def test_add_remove_and_noop(self) -> None:
        set_resource_share_groups(self.workflow, [self.group.id])
        self.assertEqual(self._count(), 1)
        set_resource_share_groups(self.workflow, [self.group.id])  # no-op
        self.assertEqual(self._count(), 1)
        set_resource_share_groups(self.workflow, [])  # remove
        self.assertEqual(self._count(), 0)

    def test_cross_org_group_rejected(self) -> None:
        other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        foreign_group = OrganizationGroup.objects.create(
            organization=other_org, name="Foreign", created_by=self.owner
        )
        with self.assertRaises(ValueError):
            set_resource_share_groups(self.workflow, [foreign_group.id])
        self.assertEqual(self._count(), 0)


class ForUserGroupVisibilityTests(GroupSharingTestBase):
    """Group-shared resources appear for members and track membership live."""

    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            "tenant_account_v2.organization_member_service."
            "OrganizationMemberService.is_user_organization_admin",
            return_value=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_group_share_visible_to_member_only(self) -> None:
        set_resource_share_groups(self.workflow, [self.group.id])
        self.assertIn(self.workflow, Workflow.objects.for_user(self.member))
        self.assertNotIn(self.workflow, Workflow.objects.for_user(self.outsider))

    def test_membership_change_takes_effect_immediately(self) -> None:
        set_resource_share_groups(self.workflow, [self.group.id])
        self.assertNotIn(self.workflow, Workflow.objects.for_user(self.outsider))
        GroupMembership.objects.create(group=self.group, user=self.outsider)
        self.assertIn(self.workflow, Workflow.objects.for_user(self.outsider))


class SignalCleanupTests(GroupSharingTestBase):
    """The two ``post_delete`` cleanups: rejoin-backdoor and orphan prevention."""

    def test_org_member_removal_purges_memberships_and_direct_shares(self) -> None:
        self.workflow.shared_users.add(self.member)
        set_resource_share_groups(self.workflow, [self.group.id])

        OrganizationMember.objects.get(user=self.member).delete()

        self.assertFalse(
            GroupMembership.objects.filter(user=self.member, group=self.group).exists()
        )
        self.assertNotIn(self.member.id, _shared_user_ids(self.workflow))

    def test_resource_delete_purges_group_shares(self) -> None:
        set_resource_share_groups(self.workflow, [self.group.id])
        content_type = ContentType.objects.get_for_model(Workflow)
        workflow_pk = str(self.workflow.pk)

        self.workflow.delete()

        self.assertFalse(
            ResourceGroupShare.objects.filter(
                content_type=content_type, object_id=workflow_pk
            ).exists()
        )


class ShareableResourceRegistryTests(TestCase):
    """Each installed descriptor must resolve and expose its declared fields."""

    def test_descriptors_resolve_and_fields_exist(self) -> None:
        from django.apps import apps

        for resource in SHAREABLE_RESOURCES:
            try:
                model = apps.get_model(resource.app_label, resource.model_name)
            except LookupError:
                continue  # cloud-only app absent in this deployment
            for attr in ("id_field", "name_field"):
                field_name = getattr(resource, attr)
                try:
                    model._meta.get_field(field_name)
                except FieldDoesNotExist:
                    self.fail(
                        f"{resource.kind}.{attr}={field_name!r} is not a field on "
                        f"{resource.app_label}.{resource.model_name}"
                    )
