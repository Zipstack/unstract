"""Regression tests for the UN-3315 prompt authorization split.

``shared_to_org`` grants org members **view and edit** on a project's prompts,
not delete. Three separate mechanisms enforce that, and each has a distinct
failure mode:

1. ``ToolStudioPromptView.get_permissions`` routes ``destroy`` to
   :class:`IsPromptParentToolOwner` while every other action keeps
   :class:`PromptAcesssToUser`. Collapsing it back to a flat
   ``permission_classes`` reopens org-wide DELETE; widening it to gate all
   mutations silently removes the edit rights the ruling granted. Both
   directions are covered -- an over-restriction is as much a defect here as
   an under-restriction.

2. ``PromptStudioCoreView.get_permissions`` routes ``sync_prompts`` to
   ``IsOwner``. That route rip-and-replaces every prompt in the project, so a
   share must not reach it.

3. ``reorder_prompts`` is routed at a *collection* path with the target taken
   from the request body, so DRF never calls ``get_object()`` and the
   class-based hook never fires on its own. Its guard is an explicit
   ``check_object_permissions`` call inside the action.

Mechanism 3 is why these tests import the real modules rather than extracting
method bodies with ``tests_common.source_extraction``, as the sibling
``test_registry_tool_delete_guards.py`` does. That technique's own docstring
records the blind spot: bodies are ``exec``-ed out of context, so *unreachable*
code is indistinguishable from wired code -- and "the hook is never reached" is
precisely the bug mechanism 3 fixes.

No database is touched. ``get_permissions()`` is pure, and the collaborators
that would hit the ORM are patched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from prompt_studio.permission import IsPromptParentToolOwner, PromptAcesssToUser
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from prompt_studio.prompt_studio_v2.views import ToolStudioPromptView

PERMISSION_MODULE = "prompt_studio.permission"


class _User:
    def __init__(self, name: str, is_service_account: bool = False) -> None:
        self.name = name
        self.is_service_account = is_service_account

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.name}>"


OWNER = _User("owner")
SHARED_MEMBER = _User("shared-member")


def _tool(*, owner: _User, shared_to_org: bool) -> SimpleNamespace:
    return SimpleNamespace(owner=owner, shared_to_org=shared_to_org)


def _prompt(tool: SimpleNamespace | None) -> SimpleNamespace:
    """A ``ToolStudioPrompt`` stand-in. The FK really is named ``tool_id``."""
    return SimpleNamespace(tool_id=tool)


def _request(user: _User) -> SimpleNamespace:
    return SimpleNamespace(user=user, data={})


def _owns(user: _User, obj: Any) -> bool:
    return getattr(obj, "owner", None) is user


def _permission_for(view_cls: type, action: str) -> list[Any]:
    view = view_cls()
    view.action = action
    return view.get_permissions()


class TestPromptDeletionIsOwnerOnly:
    """``destroy`` must not be reachable through an org-wide share."""

    def test_destroy_resolves_the_parent_owner_permission(self) -> None:
        """Collapsing the split back to a flat list reopens org-wide DELETE."""
        permissions = _permission_for(ToolStudioPromptView, "destroy")

        assert any(isinstance(p, IsPromptParentToolOwner) for p in permissions), (
            "destroy must resolve IsPromptParentToolOwner; a flat "
            "permission_classes would let any org member delete prompts in a "
            "shared project"
        )

    @pytest.mark.parametrize("action", ["update", "partial_update", "retrieve"])
    def test_edits_and_reads_keep_the_share_aware_permission(self, action: str) -> None:
        """The over-restriction guard.

        UN-3315 grants org-shared members *edit*. Routing every mutation to the
        owner-only class would satisfy the deletion test above while quietly
        removing the capability the change exists to provide.
        """
        permissions = _permission_for(ToolStudioPromptView, action)

        assert any(isinstance(p, PromptAcesssToUser) for p in permissions), (
            f"{action} must keep PromptAcesssToUser so shared members retain "
            "the edit rights UN-3315 granted"
        )
        assert not any(isinstance(p, IsPromptParentToolOwner) for p in permissions)

    def test_shared_member_is_denied_deletion(self) -> None:
        """The behaviour behind the wiring: a share is not an owner."""
        tool = _tool(owner=OWNER, shared_to_org=True)

        with (
            patch(f"{PERMISSION_MODULE}._is_resource_owner", side_effect=_owns),
            patch(f"{PERMISSION_MODULE}.OrganizationMemberService") as service,
        ):
            service.is_user_organization_admin.return_value = False
            allowed = IsPromptParentToolOwner().has_object_permission(
                _request(SHARED_MEMBER), None, _prompt(tool)
            )

        assert allowed is False, (
            "shared_to_org must not confer deletion -- this is the widening "
            "UN-3315 deliberately excluded"
        )

    def test_owner_may_delete(self) -> None:
        tool = _tool(owner=OWNER, shared_to_org=True)

        with (
            patch(f"{PERMISSION_MODULE}._is_resource_owner", side_effect=_owns),
            patch(f"{PERMISSION_MODULE}.OrganizationMemberService") as service,
        ):
            service.is_user_organization_admin.return_value = False
            allowed = IsPromptParentToolOwner().has_object_permission(
                _request(OWNER), None, _prompt(tool)
            )

        assert allowed is True

    def test_orphaned_prompt_denies_rather_than_raising(self) -> None:
        """``tool_id`` is nullable (``SET_NULL``).

        An orphaned prompt has no owner to inherit from, so it must fall
        through to the org-admin check rather than raising AttributeError on
        ``None`` -- a 403, not a 500.
        """
        with (
            patch(f"{PERMISSION_MODULE}._is_resource_owner", side_effect=_owns),
            patch(f"{PERMISSION_MODULE}.OrganizationMemberService") as service,
        ):
            service.is_user_organization_admin.return_value = False
            allowed = IsPromptParentToolOwner().has_object_permission(
                _request(SHARED_MEMBER), None, _prompt(None)
            )

        assert allowed is False

    def test_shared_member_may_still_edit(self) -> None:
        """The paired behaviour: the same member denied delete keeps edit."""
        tool = _tool(owner=OWNER, shared_to_org=True)

        with (
            patch(f"{PERMISSION_MODULE}._is_resource_owner", return_value=False),
            patch(f"{PERMISSION_MODULE}._is_resource_viewer", return_value=False),
            patch(f"{PERMISSION_MODULE}.has_group_access", return_value=False),
            patch(f"{PERMISSION_MODULE}.OrganizationMemberService") as service,
        ):
            service.is_user_organization_admin.return_value = False
            allowed = PromptAcesssToUser().has_object_permission(
                _request(SHARED_MEMBER), None, _prompt(tool)
            )

        assert allowed is True, (
            "shared_to_org is the only grant path left standing here; if this "
            "fails the UN-3315 branch itself has been removed"
        )


class TestSyncPromptsIsOwnerOnly:
    """``sync_prompts`` deletes every prompt in the project before importing."""

    def test_sync_prompts_resolves_the_owner_permission(self) -> None:
        from permissions.permission import IsOwner

        permissions = _permission_for(PromptStudioCoreView, "sync_prompts")

        assert any(isinstance(p, IsOwner) for p in permissions), (
            "sync_prompts rip-and-replaces every prompt; dropping it from the "
            "IsOwner list lets an org-shared member wipe the project"
        )

    def test_reads_are_not_owner_gated(self) -> None:
        """The paired direction -- sharing must still reach ordinary reads."""
        from permissions.permission import IsOwnerOrSharedUserOrSharedToOrg

        permissions = _permission_for(PromptStudioCoreView, "retrieve")

        assert any(isinstance(p, IsOwnerOrSharedUserOrSharedToOrg) for p in permissions)


class TestReorderPromptsIsGated:
    """``reorder_prompts`` is a collection POST -- ``get_object()`` never runs.

    The defect was never that the permission class was wrong; it was that
    nothing invoked it. So these tests pin the *call*, not the verdict.
    """

    def test_reorder_resolves_the_share_aware_permission(self) -> None:
        """Reordering is an edit, so a share must reach it."""
        permissions = _permission_for(ToolStudioPromptView, "reorder_prompts")

        assert any(isinstance(p, PromptAcesssToUser) for p in permissions)
        assert not any(isinstance(p, IsPromptParentToolOwner) for p in permissions), (
            "reordering is an edit, not a deletion -- owner-only would "
            "over-restrict against the UN-3315 ruling"
        )

    def test_action_calls_check_object_permissions(self) -> None:
        """The regression that matters.

        Deleting the explicit ``check_object_permissions`` call leaves the
        action fully functional and completely ungated, which is exactly the
        state this fix found it in.
        """
        view = ToolStudioPromptView()
        view.action = "reorder_prompts"
        prompt = _prompt(_tool(owner=OWNER, shared_to_org=True))
        request = SimpleNamespace(user=SHARED_MEMBER, data={"prompt_id": "p-1"})

        module = "prompt_studio.prompt_studio_v2.views"
        with (
            patch(f"{module}.get_object_or_404", return_value=prompt),
            patch(f"{module}.CustomTool"),
            patch.object(ToolStudioPromptView, "check_object_permissions") as checked,
            patch(f"{module}.PromptStudioController") as controller,
        ):
            controller.return_value.reorder_prompts.return_value = "ok"
            view.reorder_prompts(request)

        checked.assert_called_once()
        assert checked.call_args.args[1] is prompt, (
            "the permission check must run against the prompt the action is "
            "about to reorder"
        )

    def test_permission_check_precedes_the_mutation(self) -> None:
        """Order matters: a denial must stop the reorder, not follow it."""
        view = ToolStudioPromptView()
        view.action = "reorder_prompts"
        prompt = _prompt(_tool(owner=OWNER, shared_to_org=False))
        request = SimpleNamespace(user=SHARED_MEMBER, data={"prompt_id": "p-1"})

        from rest_framework.exceptions import PermissionDenied

        module = "prompt_studio.prompt_studio_v2.views"
        with (
            patch(f"{module}.get_object_or_404", return_value=prompt),
            patch(f"{module}.CustomTool"),
            patch.object(
                ToolStudioPromptView,
                "check_object_permissions",
                side_effect=PermissionDenied,
            ),
            patch(f"{module}.PromptStudioController") as controller,
        ):
            with pytest.raises(PermissionDenied):
                view.reorder_prompts(request)

        controller.return_value.reorder_prompts.assert_not_called()

    def test_missing_prompt_id_is_a_400_not_a_crash(self) -> None:
        view = ToolStudioPromptView()
        view.action = "reorder_prompts"

        with pytest.raises(ValidationError):
            view.reorder_prompts(SimpleNamespace(user=SHARED_MEMBER, data={}))
