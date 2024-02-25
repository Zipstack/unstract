from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object to edit it."""

    def has_object_permission(
        self, request: Request, view: APIView, obj: Any
    ) -> bool:
        return True if obj.created_by == request.user else False
