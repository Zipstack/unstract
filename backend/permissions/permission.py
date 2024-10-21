from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:

        return True if obj.created_by == request.user else False


class IsOwnerOrSharedUser(permissions.BasePermission):
    """Custom permission to only allow owners and shared users of an object."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:

        return (
            True
            if (
                obj.created_by == request.user
                or obj.shared_users.filter(pk=request.user.pk).exists()
            )
            else False
        )


class IsOwnerOrSharedUserOrSharedToOrg(permissions.BasePermission):
    """Custom permission to only allow owners and shared users of an object or
    if it is shared to org."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:

        return (
            True
            if (
                obj.created_by == request.user
                or obj.shared_users.filter(pk=request.user.pk).exists()
                or obj.shared_to_org
            )
            else False
        )


class IsFrictionLessAdapter(permissions.BasePermission):
    """Hack for friction-less onboarding not allowing user to view or updating
    friction less adapter."""

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:

        if obj.is_friction_less:
            return False

        return True if obj.created_by == request.user else False


class IsFrictionLessAdapterDelete(permissions.BasePermission):
    """Hack for friction-less onboarding Allows frticon less adapter to rmoved
    by an org member."""

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:

        if obj.is_friction_less:
            return True

        return True if obj.created_by == request.user else False
