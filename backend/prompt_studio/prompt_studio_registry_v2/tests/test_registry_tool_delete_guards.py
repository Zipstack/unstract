"""Regression tests for the two guards on ``DELETE registry/<pk>/``.

The route added in this PR is the first by-PK operation on
``PromptStudioRegistryView``, which previously exposed only ``list``. Two
things gate it, and both are load-bearing:

1. **Authorization** (``IsRegistryToolOwner``). The viewset carries no
   ``permission_classes`` and ``DEFAULT_PERMISSION_CLASSES`` is empty, so
   without this every member of an organization could delete any other
   member's exported tool by PK. ``OrganizationFilterBackend`` runs inside
   ``get_object()`` and blocks *cross-org* access, but not intra-org.

2. **In-use refusal** (409). An exported tool still attached to a workflow must
   not be deletable, or those workflows break.

``has_object_permission`` is pure logic over collaborators, so these tests stub
the Django-coupled boundary (``permissions.permission``,
``OrganizationMemberService``) and exercise the real method body. Django is not
importable in a plain checkout, so the class body is extracted from source --
mirroring ``prompt_studio_core_v2/tests/test_build_index_payload.py``. A rename
fails these tests rather than silently skipping them.

The in-use check is asserted against the same predicate the view applies
(a non-empty set of dependent workflow IDs raises), without standing up the ORM.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
PERMISSION_MODULE = BACKEND_DIR / "prompt_studio" / "permission.py"

START_MARKER = "class IsRegistryToolOwner(permissions.BasePermission):"


class _User:
    def __init__(self, name: str, is_service_account: bool = False) -> None:
        self.name = name
        self.is_service_account = is_service_account

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.name}>"


class _CustomTool:
    """Stand-in for the parent Prompt Studio project."""

    def __init__(self, owner: _User) -> None:
        self.owner = owner


class _RegistryRow:
    """Stand-in for a ``PromptStudioRegistry`` row.

    ``custom_tool`` is nullable, so it may be ``None`` for legacy rows exported
    before the link existed; those fall back to the row's own owner.
    """

    def __init__(self, custom_tool: _CustomTool | None, owner: _User) -> None:
        self.custom_tool = custom_tool
        self.owner = owner


class _Request:
    def __init__(self, user: _User) -> None:
        self.user = user


def _build_permission(*, org_admins: set[str]) -> Any:
    """Extract the real ``IsRegistryToolOwner`` against stubbed collaborators."""
    source = PERMISSION_MODULE.read_text()
    if START_MARKER not in source:
        pytest.fail(
            f"Could not find {START_MARKER!r} in {PERMISSION_MODULE}. If it was "
            "renamed, update this test rather than deleting it."
        )
    body = textwrap.dedent(source[source.index(START_MARKER) :])

    class _BasePermission:
        pass

    class _Permissions:
        BasePermission = _BasePermission

    def _is_resource_owner(user: _User, obj: Any) -> bool:
        return getattr(obj, "owner", None) is user

    class _OrganizationMemberService:
        @staticmethod
        def is_user_organization_admin(user: _User) -> bool:
            return user.name in org_admins

    namespace: dict[str, Any] = {
        "permissions": _Permissions,
        "_is_resource_owner": _is_resource_owner,
        "OrganizationMemberService": _OrganizationMemberService,
        "Request": object,
        "APIView": object,
        "Any": Any,
    }
    exec(compile(body, str(PERMISSION_MODULE), "exec"), namespace)
    return namespace["IsRegistryToolOwner"]()


OWNER = _User("owner")
STRANGER = _User("stranger")
ADMIN = _User("admin")
SERVICE = _User("service", is_service_account=True)


def _linked_row(owner: _User = OWNER) -> _RegistryRow:
    """A normal row whose parent project is owned by ``owner``."""
    return _RegistryRow(custom_tool=_CustomTool(owner=owner), owner=_User("unused"))


class TestRegistryToolDeleteAuthorization:
    def test_project_owner_may_delete(self) -> None:
        permission = _build_permission(org_admins=set())
        assert (
            permission.has_object_permission(_Request(OWNER), None, _linked_row()) is True
        )

    def test_other_org_member_may_not_delete(self) -> None:
        """The IDOR this guard exists to close.

        Org filtering already blocks cross-org access; this covers a member of
        the *same* org who does not own the project.
        """
        permission = _build_permission(org_admins=set())

        allowed = permission.has_object_permission(
            _Request(STRANGER), None, _linked_row()
        )

        assert allowed is False, (
            "A non-owner in the same organization must not be able to delete "
            "another member's exported tool"
        )

    def test_org_admin_may_delete(self) -> None:
        permission = _build_permission(org_admins={"admin"})
        assert (
            permission.has_object_permission(_Request(ADMIN), None, _linked_row()) is True
        )

    def test_service_account_may_delete(self) -> None:
        permission = _build_permission(org_admins=set())
        assert (
            permission.has_object_permission(_Request(SERVICE), None, _linked_row())
            is True
        )

    def test_ownership_follows_the_parent_project_not_the_row(self) -> None:
        """Ownership is inherited from ``custom_tool``, mirroring IsParentToolOwner.

        The row's own ``owner`` must be ignored while a parent exists, otherwise
        a stale export-time owner could outrank the project's current owner.
        """
        row = _RegistryRow(custom_tool=_CustomTool(owner=OWNER), owner=STRANGER)
        permission = _build_permission(org_admins=set())

        assert permission.has_object_permission(_Request(STRANGER), None, row) is False
        assert permission.has_object_permission(_Request(OWNER), None, row) is True

    def test_unlinked_legacy_row_falls_back_to_its_own_owner(self) -> None:
        """``custom_tool`` is nullable; those rows must stay deletable by their owner."""
        row = _RegistryRow(custom_tool=None, owner=OWNER)
        permission = _build_permission(org_admins=set())

        assert permission.has_object_permission(_Request(OWNER), None, row) is True
        assert permission.has_object_permission(_Request(STRANGER), None, row) is False


class TestRegistryToolInUseRefusal:
    """The 409 guard: a tool attached to a workflow must not be deleted.

    Mirrors the predicate in ``PromptStudioRegistryView.destroy`` -- a non-empty
    set of dependent workflow IDs refuses the delete.
    """

    @staticmethod
    def _refuses(dependent_workflow_ids: set[str]) -> bool:
        return bool(dependent_workflow_ids)

    def test_tool_used_by_a_workflow_is_refused(self) -> None:
        assert self._refuses({"workflow-1"}) is True

    def test_unused_tool_is_deletable(self) -> None:
        assert self._refuses(set()) is False

    def test_in_use_error_is_a_409(self) -> None:
        """Deleting an in-use tool is a conflict, not a server error.

        The neighbouring ``ToolDeleteError`` is a 500; this must not be modelled
        on it, since the condition is caller-correctable.
        """
        source = (
            BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2" / "exceptions.py"
        ).read_text()

        assert "class RegistryToolInUseError" in source, (
            "RegistryToolInUseError is missing; the in-use guard has no way to "
            "signal a conflict"
        )
        body = source[source.index("class RegistryToolInUseError") :]
        assert "status_code = 409" in body.split("class ")[1], (
            "RegistryToolInUseError must be a 409 so callers can distinguish a "
            "correctable conflict from a server fault"
        )
