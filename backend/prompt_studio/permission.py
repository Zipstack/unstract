from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class PromptAcesssToUser(permissions.BasePermission):
    """Is the crud to Prompt/Notes allowed to user."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        return (
            True
            if (
                obj.tool_id.created_by == request.user
                or obj.tool_id.shared_users.filter(pk=request.user.pk).exists()
            )
            else False
        )
