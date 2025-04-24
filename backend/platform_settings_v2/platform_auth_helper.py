import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.models import Organization, PlatformKey, User
from tenant_account_v2.models import OrganizationMember

from platform_settings_v2.exceptions import KeyCountExceeded, UserForbidden

PLATFORM_KEY_COUNT = 2

logger = logging.getLogger(__name__)


class PlatformAuthHelper:
    """Class to hold helper functions for Platform settings authentication."""

    @staticmethod
    def validate_user_role(user: User) -> None:
        """This method validates if the logged in user has admin role for
        performing appropriate actions.

        Args:
            user (User): Logged in user from context
        """
        auth_controller = AuthenticationController()
        member: OrganizationMember = auth_controller.get_organization_members_by_user(
            user=user
        )
        if not auth_controller.is_admin_by_role(member.role):
            logger.error("User is not having right access to perform this operation.")
            raise UserForbidden()
        else:
            pass

    @staticmethod
    def validate_token_count(organization: Organization) -> None:
        """This method validates if the organization has reached the maximum
        platform key count.

        Args:
            organization (Organization):
                Organization for which the key is being created.
        """
        key_count = PlatformKey.objects.filter(organization=organization).count()
        if key_count >= PLATFORM_KEY_COUNT:
            logger.error(
                f"Key count exceeded: {key_count}/{PLATFORM_KEY_COUNT} keys for "
                f"organization ID {organization.id}."
            )
            raise KeyCountExceeded()
        else:
            pass
