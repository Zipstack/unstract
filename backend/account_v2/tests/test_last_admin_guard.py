"""Tests for the last-admin demotion guard in AuthenticationController.

Stubs all Django-model-importing modules at sys.modules level before importing
the controller, so these tests run without Django setup or a live database.

Test rig: covered by the `unit-backend` group in tests/groups.yaml
(paths: account_v2/tests). That group is currently optional=true pending
test_cases settings; these tests themselves need no DB/redis.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import django.conf
import pytest

# Configure minimal Django settings before any controller import;
# class-level default args (e.g. settings.DEFAULT_MODEL_BACKEND) are
# evaluated at class definition time.
if not django.conf.settings.configured:
    django.conf.settings.configure(
        DEFAULT_AUTH_USERNAME="",
        DEFAULT_MODEL_BACKEND="",
        CSRF_COOKIE_SECURE=False,
        INSTALLED_APPS=[],
    )


# ---------------------------------------------------------------------------
# Hand-rolled service stub — avoids any mock framework dependency.
# ---------------------------------------------------------------------------


class _OrgMemberServiceStub:
    _member_by_email: SimpleNamespace | None = None
    _members_by_role: list = []

    @classmethod
    def get_user_by_email(cls, email: str) -> SimpleNamespace | None:
        return cls._member_by_email

    @classmethod
    def get_members_by_role(cls, role: str) -> list:
        return cls._members_by_role

    @classmethod
    def _reset(cls) -> None:
        cls._member_by_email = None
        cls._members_by_role = []


# ---------------------------------------------------------------------------
# Module-level stubs — installed once before the controller is imported.
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    def _mod(name: str, **attrs: object) -> types.ModuleType:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    _s = object  # placeholder for unused imported names

    _mod("tenant_account_v2.models", OrganizationMember=_s)
    _mod("account_v2.models", Organization=_s, User=_s)
    _mod(
        "tenant_account_v2.organization_member_service",
        OrganizationMemberService=_OrgMemberServiceStub,
    )
    _mod(
        "account_v2.constants",
        AuthorizationErrorCode=_s,
        Common=_s,
        Cookie=_s,
        ErrorMessage=_s,
        OrganizationMemberModel=_s,
    )
    _mod("account_v2.authentication_plugin_registry", AuthenticationPluginRegistry=_s)
    _mod("account_v2.authentication_service", AuthenticationService=_s)
    _mod("account_v2.authentication_helper", AuthenticationHelper=_s)
    _mod("account_v2.organization", OrganizationService=_s)
    _mod(
        "account_v2.serializer",
        GetOrganizationsResponseSerializer=_s,
        OrganizationSerializer=_s,
        SetOrganizationsResponseSerializer=_s,
    )
    _mod("account_v2.user", UserService=_s)
    _mod("utils.cache_service", CacheService=_s)
    _mod("utils.local_context", StateStore=_s)
    _mod("utils.user_context", UserContext=_s)
    _mod("utils.user_session", UserSessionUtils=_s)
    _mod("logs_helper.log_service", LogService=_s)


_install_stubs()

from account_v2.authentication_controller import AuthenticationController  # noqa: E402
from account_v2.custom_exceptions import Forbidden  # noqa: E402
from account_v2.enums import UserRole  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_stub() -> None:
    _OrgMemberServiceStub._reset()


def _controller() -> AuthenticationController:
    return AuthenticationController.__new__(AuthenticationController)


def _member(role: str) -> SimpleNamespace:
    return SimpleNamespace(role=role)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLastAdminGuard:
    def test_no_op_when_assigning_admin_role(self):
        _controller()._ensure_not_last_admin_demotion(
            email="admin@example.com", new_role=UserRole.ADMIN.value
        )

    def test_no_op_when_target_is_not_admin(self):
        _OrgMemberServiceStub._member_by_email = _member(UserRole.USER.value)
        _controller()._ensure_not_last_admin_demotion(
            email="user@example.com", new_role=UserRole.USER.value
        )

    def test_no_op_when_multiple_admins_remain(self):
        _OrgMemberServiceStub._member_by_email = _member(UserRole.ADMIN.value)
        _OrgMemberServiceStub._members_by_role = [_member("admin"), _member("admin")]
        _controller()._ensure_not_last_admin_demotion(
            email="admin@example.com", new_role=UserRole.USER.value
        )

    def test_raises_when_sole_admin_demoted(self):
        _OrgMemberServiceStub._member_by_email = _member(UserRole.ADMIN.value)
        _OrgMemberServiceStub._members_by_role = [_member("admin")]
        with pytest.raises(Forbidden):
            _controller()._ensure_not_last_admin_demotion(
                email="admin@example.com", new_role=UserRole.USER.value
            )

    def test_no_op_when_target_not_found(self):
        _controller()._ensure_not_last_admin_demotion(
            email="ghost@example.com", new_role=UserRole.USER.value
        )
