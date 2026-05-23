from typing import Any

from permissions.permission import has_group_access
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class PromptAcesssToUser(permissions.BasePermission):
    """Is the crud to Prompt/Notes allowed to user.

    A user qualifies when they own the parent ``CustomTool``, are a direct
    ``shared_users`` member, or reach the project via group sharing
    (``ResourceGroupShare`` on the parent tool).
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        tool = obj.tool_id
        if tool.created_by == request.user:
            return True
        if tool.shared_users.filter(pk=request.user.pk).exists():
            return True
        return has_group_access(request.user, tool)
