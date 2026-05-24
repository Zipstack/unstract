from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from utils.user_context import UserContext

_REQUEST_ADMIN_CACHE_ATTR = "_cached_is_organization_admin"


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


def _is_organization_admin(request: Request) -> bool:
    """Return True if the requesting user has the org-admin role.

    Result is cached per-request to keep cost at one membership lookup per
    incoming HTTP call regardless of how many permission classes ask.
    """
    cached = getattr(request, _REQUEST_ADMIN_CACHE_ATTR, None)
    if cached is not None:
        return cached
    try:
        from account_v2.authentication_controller import AuthenticationController

        auth_controller = AuthenticationController()
        member = auth_controller.get_organization_members_by_user(user=request.user)
        is_admin = bool(member) and auth_controller.is_admin_by_role(member.role)
    except Exception:
        is_admin = False
    setattr(request, _REQUEST_ADMIN_CACHE_ATTR, is_admin)
    return is_admin


def _is_service_account_owned(obj: Any) -> bool:
    """True if ``obj.created_by`` is a service-account user.

    Migration-created rows have a service-account ``created_by``; this lets
    the admin-override below stay scoped to those rows and avoid widening
    edit rights over resources created by other humans in the org.
    """
    created_by = getattr(obj, "created_by", None)
    return bool(created_by) and getattr(created_by, "is_service_account", False)


class IsOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object.

    Org admins are also allowed when the object was created by a service
    account (e.g. via the Platform API). This unblocks editing/deleting
    resources that org-to-org migration left owned by the service-account
    user, without widening admin rights over resources created by human
    org members.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        if obj.created_by == request.user:
            return True
        if _is_service_account_owned(obj) and _is_organization_admin(request):
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
        if _is_service_account(request):
            return True

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
