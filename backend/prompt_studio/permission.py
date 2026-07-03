from typing import Any

from permissions.permission import _is_resource_owner, has_group_access
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from tenant_account_v2.organization_member_service import OrganizationMemberService


class PromptAcesssToUser(permissions.BasePermission):
    """Is the crud to Prompt/Notes allowed to user.

    A user qualifies when they own the parent ``CustomTool``, are a direct
    ``shared_users`` member, reach the project via group sharing
    (``ResourceGroupShare`` on the parent tool), or are an org admin
    (org-wide admin override, UN-3479).
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        tool = obj.tool_id
        if _is_resource_owner(request.user, tool):
            return True
        if tool.shared_users.filter(pk=request.user.pk).exists():
            return True
        if has_group_access(request.user, tool):
            return True
        return OrganizationMemberService.is_user_organization_admin(request.user)
