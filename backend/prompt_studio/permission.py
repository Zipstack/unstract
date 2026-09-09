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


def _can_access_tool(user: Any, tool: Any) -> bool:
    """Whether ``user`` may work on ``tool``.

    Prompt Studio is shared for collaboration (UN-2868): a shared user edits
    the project's prompts and settings, the same as its owner. Only the
    project's name, its existence and who else it is shared with stay with
    the owner, and those are gated on the project viewset.
    """
    if _is_resource_owner(user, tool):
        return True
    if _is_resource_viewer(user, tool):
        return True
    if has_group_access(user, tool):
        return True
    # Left last: the admin lookup is uncached, so shared users resolve without it.
    return OrganizationMemberService.is_user_organization_admin(user)


class PromptAcesssToUser(permissions.BasePermission):
    """Is the crud to Prompt/Notes allowed to user.

    A user qualifies when they own the parent ``CustomTool``, are a direct
    viewer (VIEWER membership, UN-2202), reach the project via group sharing
    (``ResourceGroupShare`` on the parent tool), or are an org admin
    (org-wide admin override, UN-3479).
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        return _can_access_tool(request.user, obj.tool_id)


class ParentToolAccess(permissions.BasePermission):
    """Gate for Prompt Studio sub-resources keyed to a project.

    A ``ProfileManager`` carries no membership of its own, so access follows
    the parent ``CustomTool`` -- anyone the project is shared with manages its
    profiles as they do its prompts. ``create`` is collection-level, so DRF
    never calls the object check for it and the parent is resolved from the
    payload instead.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if getattr(view, "action", None) != "create":
            return True
        if getattr(request.user, "is_service_account", False):
            return True
        # Imported here: the models pull in this module at import time.
        from prompt_studio.prompt_profile_manager_v2.constants import ProfileManagerKeys
        from prompt_studio.prompt_studio_core_v2.models import CustomTool

        tool = CustomTool.objects.filter(
            tool_id=request.data.get(ProfileManagerKeys.PROMPT_STUDIO_TOOL)
        ).first()
        return bool(tool and _can_access_tool(request.user, tool))

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        tool = obj.prompt_studio_tool
        if not tool:
            # Orphan row: the parent FK is nullable, so fall back to its creator.
            return obj.created_by_id == request.user.id
        return _can_access_tool(request.user, tool)


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
