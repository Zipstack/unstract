import logging
from typing import Any, Optional, Union

from account.dto import MemberData
from account.models import Organization, User
from account.user import UserService
from platform_settings.platform_auth_service import PlatformAuthenticationService
from tenant_account.models import OrganizationMember

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

    @staticmethod
    def get_or_create_user_by_email(
        user_id: str, email: str
    ) -> Union[User, OrganizationMember]:
        user_service = UserService()
        user = user_service.get_user_by_email(email)
        if not user:
            user = user_service.create_user(email, user_id)
        return user

    @staticmethod
    def get_or_create_user(
        user: User,
    ) -> Optional[Union[User, OrganizationMember]]:
        user_service = UserService()
        if user.id:
            account_user: Optional[User] = user_service.get_user_by_id(user.id)
            if account_user:
                return account_user
            elif user.email:
                account_user = user_service.get_user_by_email(email=user.email)
                if account_user:
                    return account_user
                if user.user_id:
                    user.save()
                    return user
        elif user.email and user.user_id:
            account_user = user_service.create_user(
                email=user.email, user_id=user.user_id
            )
            return account_user
        return None

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
