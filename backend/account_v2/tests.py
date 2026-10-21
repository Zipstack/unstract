"""Tests for the last-admin demotion guard in AuthenticationController.

An organization must never lose its only admin via a role change. The guard
(``_ensure_not_last_admin_demotion``) is exercised directly and through the
``add_user_role`` / ``remove_user_role`` entrypoints it protects.
"""

import secrets
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from account_v2.authentication_controller import AuthenticationController
from account_v2.custom_exceptions import Forbidden
from account_v2.enums import UserRole
from account_v2.models import Organization, User
from account_v2.views import logout


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
        # Pin the built-in auth service: role vocabulary is plugin-defined, so
        # UserRole below is only meaningful while no auth plugin is installed.
        registry = patch(
            "account_v2.authentication_controller."
            "AuthenticationPluginRegistry.is_plugin_available",
            return_value=False,
        )
        registry.start()
        self.addCleanup(registry.stop)
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


class LogoutMethodTests(TestCase):
    def setUp(self) -> None:
        controller = patch("account_v2.views.AuthenticationController")
        self.controller = controller.start()
        self.addCleanup(controller.stop)
        self.controller.return_value.user_logout.return_value = HttpResponse(status=302)

    def test_get_logs_out(self) -> None:
        response = logout(APIRequestFactory().get("/logout"))
        self.assertEqual(response.status_code, 302)

    def test_post_logs_out(self) -> None:
        response = logout(APIRequestFactory().post("/logout"))
        self.assertEqual(response.status_code, 302)
        self.controller.return_value.user_logout.assert_called_once()
