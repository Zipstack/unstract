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
    """Is the crud to Prompt/Notes allowed to user.

    A user qualifies when they own the parent ``CustomTool``, are a direct
    viewer (VIEWER membership, UN-2202), reach the project via group sharing
    (``ResourceGroupShare`` on the parent tool), or are an org admin
    (org-wide admin override, UN-3479).
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        tool = obj.tool_id
        if _is_resource_owner(request.user, tool):
            return True
        if _is_resource_viewer(request.user, tool):
            return True
        if has_group_access(request.user, tool):
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
