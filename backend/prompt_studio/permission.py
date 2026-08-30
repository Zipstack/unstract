from typing import Any

from permissions.permission import (
    _is_resource_owner,
    _is_resource_viewer,
    has_group_access,
)
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from tenant_account_v2.organization_member_service import OrganizationMemberService


class PromptAcesssToUser(permissions.BasePermission):
    """Read and edit access to a Prompt/Note, inherited from the parent tool.

    A user qualifies when they own the parent ``CustomTool``, are a direct
    viewer (VIEWER membership, UN-2202), reach the project via group sharing
    (``ResourceGroupShare`` on the parent tool), reach it because the parent
    tool is shared with the whole org (``shared_to_org``, UN-3315), or are an
    org admin (org-wide admin override, UN-3479).

    Deliberately broader than the workflow rule stated in
    ``permissions.permission.is_workflow_mutator`` ("shared access grants read
    only, never mutate"): a Prompt Studio share confers *edit* rights on the
    project's prompts, matching ``CustomToolViewSet``, which already routes
    ``update``/``partial_update`` on the tool itself through
    ``IsOwnerOrSharedUserOrSharedToOrg``. ``ProfileManagerView`` looks like a
    counterexample -- it routes ``update``/``partial_update``/``destroy``
    through ``IsParentToolOwner`` -- but it is not: profiles are *created*
    through ``PromptStudioCoreView.create_profile_manager``, which admits
    org-shared users, as does ``make_profile_default``. That surface is
    share-permissive and unaddressed here.

    ``destroy`` on ``ToolStudioPromptView`` is gated by
    :class:`IsPromptParentToolOwner` instead, so this class does not confer
    per-prompt deletion. The bulk ``sync_prompts`` route on
    ``PromptStudioCoreView`` is likewise ``IsOwner``-gated.

    One deletion path remains open to a non-owner, known and accepted
    (UN-3315): a ``read_write`` platform API key reaches ``sync_prompts``.
    Service accounts short-circuit ahead of every check here, and that route
    declares no DELETE-tier requirement -- being a POST, it is not covered by
    the DELETE tier that guards per-prompt ``destroy``.

    Separately, and not a hole: ``sync_prompts`` with an empty ``prompts``
    list clears a project's prompts by design -- supported behaviour, asserted
    by ``test_sync_prompts_clear_bumps_tool_modified_at``. The owner gate, not
    payload validation, is what stands between a share and that wipe.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        tool = obj.tool_id
        if _is_resource_owner(request.user, tool):
            return True
        if _is_resource_viewer(request.user, tool):
            return True
        # UN-3315: "Share with everyone" sets shared_to_org on the parent tool.
        # IsOwnerOrSharedUserOrSharedToOrg already honours it, so a user whose
        # only access came from that flag (no VIEWER row, no group share, not an
        # admin) could not reach the project's prompts at all.
        #
        # Read directly rather than via getattr: on a CustomTool the field is
        # a non-nullable BooleanField, so a default would only mask a renamed
        # field by silently denying access. Matches
        # IsOwnerOrSharedUserOrSharedToOrg, which also reads it directly.
        if tool.shared_to_org:
            return True
        if has_group_access(request.user, tool):
            return True
        return OrganizationMemberService.is_user_organization_admin(request.user)


class IsPromptParentToolOwner(permissions.BasePermission):
    """Deletion gate for Prompt Studio prompts/notes.

    Mirrors ``permissions.permission.IsParentToolOwner``, which does the same
    for ``ProfileManager``, but reads the parent through ``ToolStudioPrompt``'s
    own FK name (``tool_id``) rather than ``prompt_studio_tool``. Kept as a
    separate class rather than teaching the shared one to juggle both attribute
    names: a shared authorization class that accumulates per-caller special
    cases is how these gates drift apart.

    Exists because the parent ``CustomTool``'s own ``destroy`` is owner-only
    (``IsOwner`` in ``CustomToolViewSet.get_permissions``). Without this,
    UN-3315's org-wide share would let any org member delete every prompt
    inside a project they cannot themselves delete.

    ``tool_id`` is nullable (``SET_NULL``), so an orphaned prompt whose parent
    tool was deleted falls back to the org-admin check -- it has no owner to
    inherit from.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        tool = obj.tool_id
        if tool is not None and _is_resource_owner(request.user, tool):
            return True
        return OrganizationMemberService.is_user_organization_admin(request.user)


class IsRegistryToolOwner(permissions.BasePermission):
    """Is unpublishing an exported tool allowed to user.

    A ``PromptStudioRegistry`` row is not itself a membership resource, so
    ownership is inherited from the linked ``CustomTool`` -- mirroring
    ``IsParentToolOwner``, which does the same for ``ProfileManager``. Falls
    back to the row's own owner for unlinked legacy rows (``custom_tool`` is
    nullable).

    Read access is deliberately broader (see
    ``PromptStudioRegistry.objects.list_tools``); deleting is restricted to
    owners and org admins.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        owner_resource = obj.custom_tool or obj
        if _is_resource_owner(request.user, owner_resource):
            return True
        return OrganizationMemberService.is_user_organization_admin(request.user)
