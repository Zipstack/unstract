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
    - **Platform API key callers** (bearer/service-account sessions) may rotate
      ONLY their own key, enabling self-service credential rotation via the API
      without exposing other keys in the org. The org boundary is already
      enforced upstream (auth middleware + org-scoped queryset); this adds the
      intra-org "self only" restriction for key callers.

    The "self only" constraint for key callers is enforced object-level in
    ``has_object_permission`` (the idiomatic DRF location); ``has_permission``
    is the coarse session-vs-key gate. This permission is only used by the
    detail-route ``rotate`` action, which fetches the row via ``get_object()``
    and therefore always triggers the object-level check.

    Note: the auth middleware already blocks ``read`` keys from POST, so only
    ``read_write``/``full_access`` keys can reach rotate.
    """

    message = (
        "You can only rotate your own API key. Rotating other keys requires an "
        "organization admin."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request, "platform_api_key", None) is not None:
            # Platform API key caller: admitted here; the "own key only"
            # constraint is enforced in has_object_permission below.
            return True
        # Session caller: must be an org admin (may rotate any key in the org).
        return IsOrganizationAdmin().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        platform_key = getattr(request, "platform_api_key", None)
        if platform_key is not None:
            # Platform API key may rotate only its own key.
            return obj.id == platform_key.id
        # Session admins were already gated in has_permission.
        return True
