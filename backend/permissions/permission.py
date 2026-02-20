from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from utils.user_context import UserContext


class IsOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object.

    Owners include both the original creator (created_by)
    and any co-owners.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if obj.created_by == request.user:
            return True
        if (
            hasattr(obj, "co_owners")
            and obj.co_owners.filter(pk=request.user.pk).exists()
        ):
            return True
        return False


class IsOrganizationMember(permissions.BasePermission):
    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user_organization = UserContext.get_organization()
        if user_organization is None:
            return False
        return True if obj.organization == user_organization else False


class IsOwnerOrSharedUser(permissions.BasePermission):
    """Custom permission to only allow owners and shared users of an object."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if obj.created_by == request.user:
            return True
        if (
            hasattr(obj, "co_owners")
            and obj.co_owners.filter(pk=request.user.pk).exists()
        ):
            return True
        if obj.shared_users.filter(pk=request.user.pk).exists():
            return True
        return False


class IsOwnerOrSharedUserOrSharedToOrg(permissions.BasePermission):
    """Custom permission to only allow owners and shared users of an object or
    if it is shared to org.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if obj.created_by == request.user:
            return True
        if (
            hasattr(obj, "co_owners")
            and obj.co_owners.filter(pk=request.user.pk).exists()
        ):
            return True
        if obj.shared_users.filter(pk=request.user.pk).exists():
            return True
        if obj.shared_to_org:
            return True
        return False


def _is_adapter_owner(request: Request, obj: AdapterInstance) -> bool:
    """Check if the user is an owner (created_by or co_owner) of the adapter."""
    if obj.created_by == request.user:
        return True
    return bool(obj.co_owners.filter(pk=request.user.pk).exists())


class IsFrictionLessAdapter(permissions.BasePermission):
    """Hack for friction-less onboarding not allowing user to view or updating
    friction less adapter.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return False

        return _is_adapter_owner(request, obj)


class IsFrictionLessAdapterDelete(permissions.BasePermission):
    """Hack for friction-less onboarding Allows frticon less adapter to rmoved
    by an org member.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return True

        return _is_adapter_owner(request, obj)
