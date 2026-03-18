from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from utils.user_context import UserContext


def _is_service_account(request: Request) -> bool:
    """Allow service accounts through for all non-DELETE methods.

    Two constraints are enforced upstream in the authentication middleware
    before this check is ever reached:
      1. DELETE is blocked for all API keys.
      2. Write methods (POST/PUT/PATCH) are blocked for READ-only API keys.

    Therefore any service-account request that arrives here is permitted to
    proceed regardless of HTTP method.
    """
    return getattr(request.user, "is_service_account", False)


class IsOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        return True if obj.created_by == request.user else False


class IsOrganizationMember(permissions.BasePermission):
    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user_organization = UserContext.get_organization()
        if user_organization is None:
            return False
        return True if obj.organization == user_organization else False


class IsOwnerOrSharedUser(permissions.BasePermission):
    """Custom permission to only allow owners and shared users of an object."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
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
    if it is shared to org.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
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
    friction less adapter.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return False

        return True if obj.created_by == request.user else False


class IsFrictionLessAdapterDelete(permissions.BasePermission):
    """Hack for friction-less onboarding Allows frticon less adapter to rmoved
    by an org member.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return True

        return True if obj.created_by == request.user else False
