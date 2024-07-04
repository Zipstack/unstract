import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.models import Organization, PlatformKey, User
from platform_settings_v2.exceptions import KeyCountExceeded, UserForbidden
from tenant_account_v2.models import OrganizationMember

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
        try:
            member: OrganizationMember = (
                auth_controller.get_organization_members_by_user(user=user)
            )
        except Exception as error:
            logger.error(
                f"Error occurred while fetching organization for user : {error}"
            )
            raise error
        if not auth_controller.is_admin_by_role(member.role):
            logger.error("User is not having right access to perform this operation.")
            raise UserForbidden()
        else:
            pass

    @staticmethod
    def validate_token_count(organization: Organization) -> None:
        if (
            PlatformKey.objects.filter(organization=organization).count()
            >= PLATFORM_KEY_COUNT
        ):
            logger.error(
                f"Only {PLATFORM_KEY_COUNT} keys are support at a time. Count exceeded."
            )
            raise KeyCountExceeded()
        else:
            pass
