import logging
from typing import Any

from account.dto import MemberData
from account.models import Organization, User
from platform_settings.platform_auth_service import PlatformAuthenticationService

logger = logging.getLogger(__name__)


class AuthenticationHelper:
    def __init__(self) -> None:
        pass

    def list_of_members_from_user_model(
        self, model_data: list[Any]
    ) -> list[MemberData]:
        members: list[MemberData] = []
        for data in model_data:
            user_id = data.user_id
            email = data.email
            name = data.username

            members.append(MemberData(user_id=user_id, email=email, name=name))

        return members

    def create_initial_platform_key(
        self, user: User, organization: Organization
    ) -> None:
        """Create an initial platform key for the given user and organization.

        This method generates a new platform key with the specified parameters
        and saves it to the database. The generated key is set as active and
        assigned the name "Key #1". The key is associated with the provided
        user and organization.

        Parameters:
            user (User): The user for whom the platform key is being created.
            organization (Organization):
                The organization to which the platform key belongs.

        Raises:
            Exception: If an error occurs while generating the platform key.

        Returns:
            None
        """
        try:
            PlatformAuthenticationService.generate_platform_key(
                is_active=True,
                key_name="Key #1",
                user=user,
                organization=organization,
            )
        except Exception:
            logger.error(
                "Failed to create default platform key for "
                f"organization {organization.organization_id}"
            )
