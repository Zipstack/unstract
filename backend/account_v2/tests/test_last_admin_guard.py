"""Tests for the last-admin demotion guard in AuthenticationController.

Stubs all Django-model-importing modules at sys.modules level before importing
the controller, so these tests run without Django setup or a live database.
Stubs are installed only when the module is not already present in sys.modules
(same pattern as usage_v2/tests/test_helper.py) to avoid poisoning other tests
in a shared pytest session.

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
    _all_members: list = []

    @classmethod
    def get_user_by_email(cls, email: str) -> SimpleNamespace | None:
        return cls._member_by_email

    @classmethod
    def get_members(cls) -> list:
        return cls._all_members

    # Kept for compatibility with other call sites in the controller.
    @classmethod
    def get_user_by_id(cls, id: object) -> None:
        return None

    @classmethod
    def _reset(cls) -> None:
        cls._member_by_email = None
        cls._all_members = []


class _FakeAuthService:
    """Minimal auth-service stub; is_admin_by_role mirrors UserRole semantics."""

    def is_admin_by_role(self, role: str) -> bool:
        from account_v2.enums import UserRole

        return role == UserRole.ADMIN.value


# ---------------------------------------------------------------------------
# Module-level stubs — installed once before the controller is imported.
# Guarded with `if X not in sys.modules` so real modules already loaded by
# other tests in the same pytest session are not overwritten.
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    def _mod(name: str, **attrs: object) -> None:
        if name in sys.modules:
            return
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m

    _s = object  # placeholder for unused imported names

    _mod("tenant_account_v2.models", OrganizationMember=_s)
    _mod("account_v2.models", Organization=_s, User=_s)

    # Always install the service stub so tests can control its return values
    # regardless of import order.
    svc_mod = types.ModuleType("tenant_account_v2.organization_member_service")
    svc_mod.OrganizationMemberService = _OrgMemberServiceStub
    sys.modules["tenant_account_v2.organization_member_service"] = svc_mod

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
    c = AuthenticationController.__new__(AuthenticationController)
    c.auth_service = _FakeAuthService()
    return c


def _member(role: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, user=SimpleNamespace(user_id="uid-1", id="uid-1"))


def _sole_admin_setup() -> None:
    """Configure the stub so that exactly one admin exists."""
    _OrgMemberServiceStub._member_by_email = _member(UserRole.ADMIN.value)
    _OrgMemberServiceStub._all_members = [_member(UserRole.ADMIN.value)]


# ---------------------------------------------------------------------------
# Guard unit tests (_ensure_not_last_admin_demotion)
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
        _OrgMemberServiceStub._all_members = [_member("admin"), _member("admin")]
        _controller()._ensure_not_last_admin_demotion(
            email="admin@example.com", new_role=UserRole.USER.value
        )

    def test_raises_when_sole_admin_demoted(self):
        _sole_admin_setup()
        with pytest.raises(Forbidden):
            _controller()._ensure_not_last_admin_demotion(
                email="admin@example.com", new_role=UserRole.USER.value
            )

    def test_no_op_when_target_not_found(self):
        _controller()._ensure_not_last_admin_demotion(
            email="ghost@example.com", new_role=UserRole.USER.value
        )


# ---------------------------------------------------------------------------
# Entrypoint tests — verify the guard is wired into the public call sites
# ---------------------------------------------------------------------------


class TestEntrypointGuard:
    def test_add_user_role_raises_for_sole_admin(self):
        _sole_admin_setup()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        with pytest.raises(Forbidden):
            _controller().add_user_role(req, "org1", "admin@example.com", UserRole.USER.value)

    def test_remove_user_role_raises_for_sole_admin(self):
        _sole_admin_setup()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        with pytest.raises(Forbidden):
            _controller().remove_user_role(
                req, "org1", "admin@example.com", UserRole.ADMIN.value
            )

    def test_remove_user_role_skips_guard_for_non_admin_role(self):
        # Removing a non-admin role must not trigger the guard even if sole admin.
        _sole_admin_setup()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        # Guard should not raise; downstream auth_service call will be a no-op
        # since _FakeAuthService has no remove_organization_user_role.
        # We only care the Forbidden is NOT raised.
        c = _controller()
        c.auth_service = SimpleNamespace(
            is_admin_by_role=_FakeAuthService().is_admin_by_role,
            remove_organization_user_role=lambda *a, **kw: [UserRole.USER.value],
        )
        result = c.remove_user_role(req, "org1", "user@example.com", UserRole.USER.value)
        assert result == UserRole.USER.value
