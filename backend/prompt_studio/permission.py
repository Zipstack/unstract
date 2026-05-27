from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from tenant_account_v2.organization_member_service import OrganizationMemberService


class PromptAcesssToUser(permissions.BasePermission):
    """Is the crud to Prompt/Notes allowed to user."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(request.user, "is_service_account", False):
            return True
        if obj.tool_id.created_by == request.user:
            return True
        if obj.tool_id.shared_users.filter(pk=request.user.pk).exists():
            return True
        return OrganizationMemberService.is_user_organization_admin(request.user)
