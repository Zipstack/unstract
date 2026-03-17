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
