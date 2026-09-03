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
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

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

    @pytest.mark.parametrize(
        "action", ["retrieve", "create_profile_manager", "make_profile_default"]
    )
    def test_other_actions_are_not_owner_gated(self, action: str) -> None:
        """The over-restriction tripwire, asserting CURRENT behaviour.

        Sharing must still reach ordinary reads, and the two profile routes
        remain share-permissive by decision -- an org-shared member may create
        a profile and change which one is default. Gating them was proposed
        and deliberately reversed, so this pins the reversal: a future edit
        cannot quietly sweep every action to owner-only.
        """
        from permissions.permission import IsOwnerOrSharedUserOrSharedToOrg

        permissions = _permission_for(PromptStudioCoreView, action)

        assert any(isinstance(p, IsOwnerOrSharedUserOrSharedToOrg) for p in permissions)


class TestMakeProfileDefaultIsScopedToItsTool:
    """Promoting a default must not reach across tools.

    ``make_profile_default`` clears ``is_default`` across the target tool's
    profiles and then promotes one. Resolved unscoped, a profile belonging to
    another tool could be promoted -- and since the clear had already run, the
    tool was left with no default of its own and a foreign profile marked
    default for it.
    """

    @staticmethod
    def _call(view: Any, request: Any) -> Any:
        return PromptStudioCoreView.make_profile_default(view, request)

    def test_profile_from_another_tool_is_not_promotable(self) -> None:
        """The cross-tool promotion this fix closes."""
        view = SimpleNamespace(get_object=lambda: "tool-A")
        request = SimpleNamespace(data={"default_profile": "profile-of-tool-B"})
        module = "prompt_studio.prompt_studio_core_v2.views"

        with (
            patch(f"{module}.get_object_or_404", side_effect=Http404) as lookup,
            patch(f"{module}.ProfileManager") as profile_manager,
        ):
            with pytest.raises(Http404):
                self._call(view, request)

        # Scoped to the parent tool -- an unscoped lookup would have found it.
        assert lookup.call_args.kwargs["prompt_studio_tool"] == "tool-A"
        (
            profile_manager.objects.filter.return_value.update.assert_not_called(),
            (
                "nothing may be modified when the promotion is refused -- the "
                "is_default clear must not run ahead of a failed lookup"
            ),
        )

    def test_same_tool_profile_is_promoted(self) -> None:
        """The happy path still works, and still clears the old default."""
        view = SimpleNamespace(get_object=lambda: "tool-A")
        request = SimpleNamespace(data={"default_profile": "profile-of-tool-A"})
        promoted = SimpleNamespace(is_default=False, profile_id="profile-of-tool-A")
        module = "prompt_studio.prompt_studio_core_v2.views"

        with (
            patch(f"{module}.get_object_or_404", return_value=promoted),
            patch(f"{module}.ProfileManager") as profile_manager,
        ):
            promoted.save = lambda: None
            response = self._call(view, request)

        assert promoted.is_default is True
        profile_manager.objects.filter.assert_called_once_with(
            prompt_studio_tool="tool-A"
        )
        profile_manager.objects.filter.return_value.update.assert_called_once_with(
            is_default=False
        )
        assert response.data == {"default_profile": "profile-of-tool-A"}

    def test_missing_default_profile_is_a_400_not_a_500(self) -> None:
        """``request.data["default_profile"]`` was a bare KeyError."""
        view = SimpleNamespace(get_object=lambda: "tool-A")

        with pytest.raises(ValidationError):
            self._call(view, SimpleNamespace(data={}))


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

    def test_format_suffix_route_does_not_crash(self) -> None:
        """``prompt/reorder.json`` passes a ``format`` kwarg.

        ``format_suffix_patterns`` generates the suffixed variant and DRF
        forwards the captured kwarg to the handler; the bare signature raised
        TypeError -- a 500 before the permission check was ever reached.
        """
        view = ToolStudioPromptView()
        view.action = "reorder_prompts"
        prompt = _prompt(_tool(owner=OWNER, shared_to_org=True))
        request = SimpleNamespace(user=SHARED_MEMBER, data={"prompt_id": "p-1"})
        module = "prompt_studio.prompt_studio_v2.views"

        with (
            patch(f"{module}.get_object_or_404", return_value=prompt),
            patch(f"{module}.CustomTool"),
            patch.object(ToolStudioPromptView, "check_object_permissions"),
            patch(f"{module}.PromptStudioController") as controller,
        ):
            controller.return_value.reorder_prompts.return_value = "ok"
            assert view.reorder_prompts(request, format="json") == "ok"


class TestPromptListIsScopedToReachableTools:
    """``list`` never calls ``get_object()``, so only the queryset gates it."""

    @staticmethod
    def _queryset_for(request: Any, filter_args: dict[str, Any]) -> Any:
        view = ToolStudioPromptView()
        view.action = "list"
        view.request = request
        module = "prompt_studio.prompt_studio_v2.views"

        with (
            patch(f"{module}.ToolStudioPrompt") as prompt_model,
            patch(f"{module}.CustomTool") as custom_tool,
            patch(f"{module}.FilterHelper") as filter_helper,
        ):
            filter_helper.build_filter_args.return_value = filter_args
            view.get_queryset()

        return prompt_model, custom_tool

    def test_unfiltered_list_is_scoped_to_the_users_tools(self) -> None:
        """The enumeration hole: `.all()` exposed every prompt in the org."""
        request = SimpleNamespace(user=SHARED_MEMBER)

        prompt_model, custom_tool = self._queryset_for(request, {})

        custom_tool.objects.for_user.assert_called_once_with(SHARED_MEMBER)
        prompt_model.objects.filter.assert_called_once_with(
            tool_id__in=custom_tool.objects.for_user.return_value
        )
        (
            prompt_model.objects.all.assert_not_called(),
            (
                "an unscoped .all() fallback lets any org member enumerate every "
                "prompt in the organization"
            ),
        )

    def test_filtered_list_is_scoped_too(self) -> None:
        """``tool_id`` comes off the query string with no ownership check.

        Scoping only the fallback would leave the filtered branch -- the one
        the UI actually uses -- just as open.
        """
        request = SimpleNamespace(user=SHARED_MEMBER)

        prompt_model, custom_tool = self._queryset_for(request, {"tool_id": "other"})

        prompt_model.objects.filter.assert_called_once_with(
            tool_id__in=custom_tool.objects.for_user.return_value
        )
        # The caller-supplied filter narrows the scoped set, never replaces it.
        prompt_model.objects.filter.return_value.filter.assert_called_once_with(
            tool_id="other"
        )


class TestReparentIsGatedOnTheOldParent:
    """Moving a prompt OUT of a project needs what deleting it needs.

    ``PromptAcesssToUser`` admits org-shared members to update, but
    ``IsPromptParentToolOwner`` denies them destroy -- and that gate reads the
    STORED parent, loaded before the update applies. A writable ``tool_id``
    therefore let a denied user reparent into a tool they own and then delete
    legitimately, two requests each passing every check.

    The check is against the EXISTING parent. Checking the new one passes
    trivially: the attacker's destination is a tool they already own, and the
    harm is the prompt leaving the original project regardless of where it
    lands.
    """

    MODULE = "prompt_studio.prompt_studio_v2.views"

    def _update(self, *, stored: str, payload: dict, owner_allows: bool) -> Any:
        view = ToolStudioPromptView()
        view.action = "partial_update"
        instance = SimpleNamespace(tool_id_id=stored)
        request = SimpleNamespace(user=SHARED_MEMBER, data=payload)

        with (
            patch.object(ToolStudioPromptView, "get_object", return_value=instance),
            patch(f"{self.MODULE}.IsPromptParentToolOwner") as gate,
            patch(
                "rest_framework.viewsets.ModelViewSet.update", return_value="updated"
            ) as parent_update,
        ):
            gate.return_value.has_object_permission.return_value = owner_allows
            try:
                result = view.update(request)
            except PermissionDenied:
                return "denied", parent_update
        return result, parent_update

    def test_shared_member_cannot_reparent_out(self) -> None:
        """The bypass: step one of reparent-then-delete is now refused."""
        result, parent_update = self._update(
            stored="tool-A", payload={"tool_id": "tool-B"}, owner_allows=False
        )

        assert result == "denied", (
            "moving a prompt out of a project is a deletion from that "
            "project's side and must require what destroy requires"
        )
        parent_update.assert_not_called(), "the move must not be applied"

    def test_owner_may_reparent(self) -> None:
        """The over-restriction guard: a legitimate move still works."""
        result, parent_update = self._update(
            stored="tool-A", payload={"tool_id": "tool-B"}, owner_allows=True
        )

        assert result == "updated"
        parent_update.assert_called_once()

    def test_same_tool_is_a_no_op_not_a_reparent(self) -> None:
        """The UI PATCHes single fields; an unchanged tool_id must pass.

        Denies at the gate to prove the no-op path never consults it.
        """
        result, parent_update = self._update(
            stored="tool-A", payload={"tool_id": "tool-A"}, owner_allows=False
        )

        assert result == "updated", (
            "an unchanged tool_id is not a reparent -- gating it would break "
            "every field-level PATCH that echoes the parent back"
        )
        parent_update.assert_called_once()

    def test_ordinary_field_edit_is_untouched(self) -> None:
        """A payload with no tool_id never reaches the gate at all."""
        result, parent_update = self._update(
            stored="tool-A", payload={"prompt_key": "k"}, owner_allows=False
        )

        assert result == "updated"
        parent_update.assert_called_once()

    def test_null_tool_id_is_a_reparent(self) -> None:
        """Orphaning is not a no-op.

        ``{"tool_id": null}`` hides the row from everyone once the org
        filter's INNER JOIN excludes it -- its owner and org admins included.
        """
        result, parent_update = self._update(
            stored="tool-A", payload={"tool_id": None}, owner_allows=False
        )

        assert result == "denied", "null must be treated as a move, not a no-op"
        parent_update.assert_not_called()
