import logging
from typing import Any

from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
from tenant_account_v2.organization_member_service import OrganizationMemberService

from account_v2.dto import MemberData
from account_v2.models import Organization, User
from account_v2.user import UserService

logger = logging.getLogger(__name__)


class AuthenticationHelper:
    def __init__(self) -> None:
        pass

    def list_of_members_from_user_model(self, model_data: list[Any]) -> list[MemberData]:
        members: list[MemberData] = []
        for data in model_data:
            user_id = data.user_id
            email = data.email
            name = data.username

            members.append(MemberData(user_id=user_id, email=email, name=name))

        return members

    @staticmethod
    def create_or_update_user(email: str, user_id: str, provider: str) -> User:
        user_service = UserService()
        user = user_service.create_or_update_user(email, user_id, provider)
        return user

    @staticmethod
    def get_or_create_user_by_email(user_id: str, email: str) -> User:
        """Get or create a user with the given email.

        If a user with the given email already exists, return that user.
        Otherwise, create a new user with the given email and return it.

        Parameters:
            user_id (str): The ID of the user.
            email (str): The email of the user.

        Returns:
            User: The user with the given email.
        """
        user_service = UserService()
        user = user_service.get_user_by_email(email)
        if user and not user.user_id:
            user = user_service.update_user(user, user_id)
        if not user:
            user = user_service.create_user(email, user_id)
        return user

    def create_initial_platform_key(self, user: User, organization: Organization) -> None:
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

    @staticmethod
    def remove_users_from_organization_by_pks(
        user_pks: list[str],
    ) -> None:
        """Remove users from an organization by their primary keys.

        Parameters:
            user_pks (list[str]): The primary keys of the users to remove.
        """
        # removing user from organization
        OrganizationMemberService.remove_users_by_user_pks(user_pks)
        # removing user m2m relations , while removing user
        for user_pk in user_pks:
            User.objects.get(pk=user_pk).prompt_registries.clear()
            User.objects.get(pk=user_pk).shared_custom_tools.clear()
            User.objects.get(pk=user_pk).shared_adapters_instance.clear()

    @staticmethod
    def remove_user_from_organization_by_user_id(
        user_id: str, organization_id: str
    ) -> None:
        """Remove users from an organization by their user_id.

        Parameters:
            user_id (str): The user_id of the users to remove.
        """
        organization_user = OrganizationMemberService.get_user_by_user_id(user_id)
        if not organization_user:
            logger.warning(
                f"User removal skipped: User '{user_id}' not found in "
                f"organization '{organization_id}'."
            )
            return

        # removing user from organization
        OrganizationMemberService.remove_user_by_user_id(user_id)

        # removing user m2m relations , while removing user
        User.objects.get(user_id=user_id).prompt_registries.clear()
        User.objects.get(user_id=user_id).shared_custom_tools.clear()
        User.objects.get(user_id=user_id).shared_adapters_instance.clear()

        # removing user from organization cache
        OrganizationMemberService.remove_user_membership_in_organization_cache(
            user_id=user_id, organization_id=organization_id
        )
        logger.info(f"User '{user_id}' removed from organization '{organization_id}'")
