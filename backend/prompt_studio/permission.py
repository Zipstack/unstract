from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsDocumentMangerAccesible(permissions.BasePermission):
    """Custom permission to only allow owners of an object."""

    def has_object_permission(
        self, request: Request, view: APIView, obj: Any
    ) -> bool:
        print(obj)
        return False
