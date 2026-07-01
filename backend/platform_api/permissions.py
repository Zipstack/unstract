import logging

from account_v2.authentication_controller import AuthenticationController
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class IsOrganizationAdmin(BasePermission):
    message = "Only organization admins can manage platform API keys."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, "is_service_account", False):
            return False
        try:
            auth_controller = AuthenticationController()
            member = auth_controller.get_organization_members_by_user(user=request.user)
            return auth_controller.is_admin_by_role(member.role)
        except Exception:
            logger.exception("Error checking admin role for user %s", request.user.id)
            return False


class CanRotatePlatformApiKey(BasePermission):
    """Permission for the ``rotate`` action (UN-3586).

    - **Session callers** must be organization admins (existing behavior —
      an admin may rotate any key in their org).
    - **Platform API key callers** (bearer/service-account sessions) are also
      allowed to rotate — this is the API/automation path that the admin-only
      ``IsOrganizationAdmin`` gate otherwise blocks (it rejects service
      accounts). Rotation stays confined to the caller's own organization via
      the auth middleware (URL org must match the key's org) and the
      org-scoped queryset, so a key can only rotate keys in its own org.

    Note: the auth middleware blocks ``read`` keys from POST, so only
    ``read_write``/``full_access`` keys can reach rotate.
    """

    message = (
        "Rotating platform API keys requires an organization admin session "
        "or a platform API key."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Platform API key (bearer) callers may rotate — the API/automation
        # path that the admin-only IsOrganizationAdmin gate blocks.
        if getattr(request, "platform_api_key", None) is not None:
            return True
        # Session caller: must be an org admin (may rotate any key in the org).
        return IsOrganizationAdmin().has_permission(request, view)
