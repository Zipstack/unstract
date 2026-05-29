from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from tenant_account_v2.organization_member_service import OrganizationMemberService
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
    is_admin = OrganizationMemberService.is_user_organization_admin(request.user)
    setattr(request, _REQUEST_ADMIN_CACHE_ATTR, is_admin)
    return is_admin


class IsOwner(permissions.BasePermission):
    """Allow owners, org admins and co-owners.

    Org admins can manage every resource in their organization regardless of
    ``created_by``. This matches the "admin role manages everything" model
    expected by org-to-org migration (resources land owned by a service
    account) and by typical admin UX.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if obj.created_by == request.user:
            return True
        if _is_service_account(request):
            return True
        if _is_organization_admin(request):
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
    """Allow owners, shared users, and org admins."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        if obj.created_by == request.user:
            return True
        if obj.shared_users.filter(pk=request.user.pk).exists():
            return True
        if _is_organization_admin(request):
            return True
        if (
            hasattr(obj, "co_owners")
            and obj.co_owners.filter(pk=request.user.pk).exists()
        ):
            return True
        return False


class IsOwnerOrSharedUserOrSharedToOrg(permissions.BasePermission):
    """Allow owners, shared users, org-shared objects, and org admins."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        if obj.created_by == request.user:
            return True
        if obj.shared_users.filter(pk=request.user.pk).exists():
            return True
        if obj.shared_to_org:
            return True
        if _is_organization_admin(request):
            return True
        if (
            hasattr(obj, "co_owners")
            and obj.co_owners.filter(pk=request.user.pk).exists()
        ):
            return True
        return False


class IsFrictionLessAdapter(permissions.BasePermission):
    """Hack for friction-less onboarding not allowing user to view or updating
    friction less adapter.

    Friction-less adapters wrap platform-owned credentials, so they remain
    blocked for everyone including org admins -- exposing them would leak
    the platform's keys.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return False
        if _is_service_account(request):
            return True
        if obj.created_by == request.user:
            return True
        if _is_organization_admin(request):
            return True
        return IsOwner().has_object_permission(request, view, obj)


class IsFrictionLessAdapterDelete(permissions.BasePermission):
    """Hack for friction-less onboarding Allows frticon less adapter to rmoved
    by an org member.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return True
        if obj.created_by == request.user:
            return True
        if _is_organization_admin(request):
            return True
        return IsOwner().has_object_permission(request, view, obj)
