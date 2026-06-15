"""Tests for the last-admin demotion guard in AuthenticationController.

An organization must never lose its only admin via a role change. The guard
(``_ensure_not_last_admin_demotion``) is exercised directly and through the
``add_user_role`` / ``remove_user_role`` entrypoints it protects.
"""

import secrets
from types import SimpleNamespace

from django.test import TestCase
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2.authentication_controller import AuthenticationController
from account_v2.custom_exceptions import Forbidden
from account_v2.enums import UserRole
from account_v2.models import Organization, User


def _make_member(org: Organization, email: str, role: str) -> OrganizationMember:
    user = User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )
    return OrganizationMember.objects.create(organization=org, user=user, role=role)


class LastAdminGuardTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.controller = AuthenticationController()
        self.admin = _make_member(self.org, "admin@example.com", UserRole.ADMIN.value)

    def test_sole_admin_cannot_be_demoted(self) -> None:
        with self.assertRaises(Forbidden):
            self.controller._ensure_not_last_admin_demotion(
                email=self.admin.user.email, new_role=UserRole.USER.value
            )

    def test_demotion_allowed_when_another_admin_remains(self) -> None:
        _make_member(self.org, "admin2@example.com", UserRole.ADMIN.value)
        self.controller._ensure_not_last_admin_demotion(
            email=self.admin.user.email, new_role=UserRole.USER.value
        )

    def test_non_admin_role_change_is_unaffected(self) -> None:
        member = _make_member(self.org, "user@example.com", UserRole.USER.value)
        self.controller._ensure_not_last_admin_demotion(
            email=member.user.email, new_role=UserRole.USER.value
        )

    def test_add_user_role_blocks_sole_admin_demotion(self) -> None:
        request = SimpleNamespace(user=self.admin.user)
        with self.assertRaises(Forbidden):
            self.controller.add_user_role(
                request,
                self.org.organization_id,
                self.admin.user.email,
                UserRole.USER.value,
            )

    def test_remove_user_role_blocks_sole_admin_demotion(self) -> None:
        request = SimpleNamespace(user=self.admin.user)
        with self.assertRaises(Forbidden):
            self.controller.remove_user_role(
                request,
                self.org.organization_id,
                self.admin.user.email,
                UserRole.ADMIN.value,
            )
