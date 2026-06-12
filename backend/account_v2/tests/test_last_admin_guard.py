"""Tests for the last-admin demotion guard in AuthenticationController.

These run under plain pytest with no live database. A fixture installs
lightweight stub modules into ``sys.modules`` (reverted on teardown via
``monkeypatch``) so ``AuthenticationController`` imports without Django's
app registry or a DB connection. They are collected under the
``unit-backend`` rig group (tests/groups.yaml) when that group is enabled.
"""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from typing import ClassVar

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

from account_v2.custom_exceptions import Forbidden  # noqa: E402
from account_v2.enums import UserRole  # noqa: E402


# ---------------------------------------------------------------------------
# Hand-rolled service stub — avoids any mock framework dependency.
# State is reset by the `controller_cls` fixture before each test.
# ---------------------------------------------------------------------------


class _OrgMemberServiceStub:
    member_by_email: ClassVar[SimpleNamespace | None] = None
    all_members: ClassVar[list[SimpleNamespace]] = []

    @classmethod
    def get_user_by_email(cls, email: str) -> SimpleNamespace | None:
        return cls.member_by_email

    @classmethod
    def get_members(cls) -> list[SimpleNamespace]:
        return cls.all_members

    @classmethod
    def get_user_by_id(cls, id: object) -> None:  # noqa: A002 - mirrors real API (id= kw)
        return None

    @classmethod
    def reset(cls) -> None:
        cls.member_by_email = None
        cls.all_members = []


class _FakeAuthService:
    """Minimal auth-service stub; is_admin_by_role mirrors UserRole semantics."""

    def is_admin_by_role(self, role: str) -> bool:
        return role == UserRole.ADMIN.value


# ---------------------------------------------------------------------------
# sys.modules stubs — installed per-test via monkeypatch and reverted on
# teardown, so nothing leaks into a shared pytest session.
# ---------------------------------------------------------------------------


def _build_stub_modules() -> dict[str, types.ModuleType]:
    _s = object  # placeholder for names referenced only at controller import

    def _mod(**attrs: object) -> types.ModuleType:
        mod = types.ModuleType("stub")
        for key, value in attrs.items():
            setattr(mod, key, value)
        return mod

    return {
        "tenant_account_v2.models": _mod(OrganizationMember=_s),
        "account_v2.models": _mod(Organization=_s, User=_s),
        "tenant_account_v2.organization_member_service": _mod(
            OrganizationMemberService=_OrgMemberServiceStub
        ),
        "account_v2.constants": _mod(
            AuthorizationErrorCode=_s,
            Common=_s,
            Cookie=_s,
            ErrorMessage=_s,
            OrganizationMemberModel=_s,
        ),
        "account_v2.authentication_plugin_registry": _mod(
            AuthenticationPluginRegistry=_s
        ),
        "account_v2.authentication_service": _mod(AuthenticationService=_s),
        "account_v2.authentication_helper": _mod(AuthenticationHelper=_s),
        "account_v2.organization": _mod(OrganizationService=_s),
        "account_v2.serializer": _mod(
            GetOrganizationsResponseSerializer=_s,
            OrganizationSerializer=_s,
            SetOrganizationsResponseSerializer=_s,
        ),
        "account_v2.user": _mod(UserService=_s),
        "utils.cache_service": _mod(CacheService=_s),
        "utils.local_context": _mod(StateStore=_s),
        "utils.user_context": _mod(UserContext=_s),
        "utils.user_session": _mod(UserSessionUtils=_s),
        "logs_helper.log_service": _mod(LogService=_s),
    }


@pytest.fixture
def controller_cls(monkeypatch):
    """Import AuthenticationController against stub modules, scoped to the test.

    monkeypatch reverts the stubbed dependency modules on teardown; the
    controller module is re-imported fresh and dropped afterwards so a shared
    pytest session always sees the real modules outside this fixture.
    """
    _OrgMemberServiceStub.reset()
    for name, module in _build_stub_modules().items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop("account_v2.authentication_controller", None)
    controller_module = importlib.import_module("account_v2.authentication_controller")
    yield controller_module.AuthenticationController
    sys.modules.pop("account_v2.authentication_controller", None)


def _make_controller(cls) -> object:
    controller = cls.__new__(cls)
    controller.auth_service = _FakeAuthService()
    return controller


def _member(role: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, user=SimpleNamespace(user_id="uid-1", id="uid-1"))


def _set_sole_admin() -> None:
    """Configure the stub so that exactly one admin exists."""
    _OrgMemberServiceStub.member_by_email = _member(UserRole.ADMIN.value)
    _OrgMemberServiceStub.all_members = [_member(UserRole.ADMIN.value)]


# ---------------------------------------------------------------------------
# Guard unit tests (_ensure_not_last_admin_demotion)
# ---------------------------------------------------------------------------


class TestLastAdminGuard:
    def test_no_op_when_assigning_admin_role(self, controller_cls):
        _make_controller(controller_cls)._ensure_not_last_admin_demotion(
            email="admin@example.com", new_role=UserRole.ADMIN.value
        )

    def test_no_op_when_target_is_not_admin(self, controller_cls):
        _OrgMemberServiceStub.member_by_email = _member(UserRole.USER.value)
        _make_controller(controller_cls)._ensure_not_last_admin_demotion(
            email="user@example.com", new_role=UserRole.USER.value
        )

    def test_no_op_when_multiple_admins_remain(self, controller_cls):
        _OrgMemberServiceStub.member_by_email = _member(UserRole.ADMIN.value)
        _OrgMemberServiceStub.all_members = [
            _member(UserRole.ADMIN.value),
            _member(UserRole.ADMIN.value),
        ]
        _make_controller(controller_cls)._ensure_not_last_admin_demotion(
            email="admin@example.com", new_role=UserRole.USER.value
        )

    def test_raises_when_sole_admin_demoted(self, controller_cls):
        _set_sole_admin()
        with pytest.raises(Forbidden):
            _make_controller(controller_cls)._ensure_not_last_admin_demotion(
                email="admin@example.com", new_role=UserRole.USER.value
            )

    def test_no_op_when_target_not_found(self, controller_cls):
        _make_controller(controller_cls)._ensure_not_last_admin_demotion(
            email="ghost@example.com", new_role=UserRole.USER.value
        )


# ---------------------------------------------------------------------------
# Entrypoint tests — verify the guard is wired into the public call sites
# ---------------------------------------------------------------------------


class TestEntrypointGuard:
    def test_add_user_role_raises_for_sole_admin(self, controller_cls):
        _set_sole_admin()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        with pytest.raises(Forbidden):
            _make_controller(controller_cls).add_user_role(
                req, "org1", "admin@example.com", UserRole.USER.value
            )

    def test_remove_user_role_raises_for_sole_admin(self, controller_cls):
        _set_sole_admin()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        with pytest.raises(Forbidden):
            _make_controller(controller_cls).remove_user_role(
                req, "org1", "admin@example.com", UserRole.ADMIN.value
            )

    def test_remove_user_role_skips_guard_for_non_admin_role(self, controller_cls):
        # Removing a non-admin role must not trigger the guard, even when only
        # one admin exists.
        _set_sole_admin()
        req = SimpleNamespace(user=SimpleNamespace(id=1))
        controller = _make_controller(controller_cls)
        controller.auth_service = SimpleNamespace(
            is_admin_by_role=_FakeAuthService().is_admin_by_role,
            remove_organization_user_role=lambda *a, **kw: [UserRole.USER.value],
        )
        result = controller.remove_user_role(
            req, "org1", "user@example.com", UserRole.USER.value
        )
        assert result == UserRole.USER.value
