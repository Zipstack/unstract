import logging

from account_v2.authentication_controller import AuthenticationController
from rest_framework.permissions import BasePermission

from platform_api.models import ApiKeyPermission

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

    - **Session callers** must be organization admins (an admin may rotate any
      key in their org).
    - **Platform API key callers** must present a ``full_access`` key — the
      API/automation path that the admin-only ``IsOrganizationAdmin`` gate
      otherwise blocks (it rejects service accounts). ``full_access`` is the
      admin-equivalent tier (it already permits DELETE), so key management
      belongs there.

    Why ``full_access`` only (not any bearer key): ``rotate`` returns the new
    key value in its response, so allowing a lower-tier ``read_write`` key to
    rotate a ``full_access`` key would let it read that key's new secret and
    escalate its privileges. Requiring ``full_access`` closes that path — a
    ``full_access`` caller rotating any key gains no privilege (it is already
    the top tier), matching what a session admin can do.

    Rotation stays confined to the caller's own organization via the auth
    middleware (URL org must match the key's org) and the org-scoped queryset.
    """

    message = (
        "Rotating platform API keys requires an organization admin session or "
        "a full_access platform API key."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        platform_key = getattr(request, "platform_api_key", None)
        if platform_key is not None:
            # Key-based caller: only a full_access key may rotate. Prevents a
            # read_write key from rotating a full_access key and reading its new
            # secret from the response (privilege escalation) — see docstring.
            return platform_key.permission == ApiKeyPermission.FULL_ACCESS
        # Session caller: must be an org admin (may rotate any key in the org).
        return IsOrganizationAdmin().has_permission(request, view)
