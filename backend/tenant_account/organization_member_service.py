from typing import Optional

from tenant_account.models import OrganizationMember
from utils.cache_service import CacheService


class OrganizationMemberService:

    @staticmethod
    def get_user_by_email(email: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user__email=email)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_user_id(user_id: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user__user_id=user_id)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_id(id: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user=id)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    @staticmethod
    def delete_user(user: OrganizationMember) -> None:
        """Delete a user from an organization.

        Parameters:
            user (OrganizationMember): The user to delete.
        """
        user.delete()

    @staticmethod
    def remove_users_by_user_pks(user_pks: list[str]) -> None:
        """Remove a users from an organization.

        Parameters:
            user_pks (list[str]): The primary keys of the users to remove.
        """
        OrganizationMember.objects.filter(user__in=user_pks).delete()

    @classmethod
    def remove_user_by_user_id(cls, user_id: str) -> None:
        """Remove a user from an organization.

        Parameters:
            user_id (str): The user_id of the user to remove.
        """
        user = cls.get_user_by_user_id(user_id)
        if user:
            cls.delete_user(user)

    @staticmethod
    def get_organization_user_cache_key(user_id: str, organization_id: str) -> str:
        """Get the cache key for a user in an organization.

        Parameters:
            organization_id (str): The ID of the organization.

        Returns:
            str: The cache key for a user in the organization.
        """
        return f"user_organization:{user_id}:{organization_id}"

    @classmethod
    def check_user_membership_in_organization_cache(
        cls, user_id: str, organization_id: str
    ) -> bool:
        """Check if a user exists in an organization.

        Parameters:
            user_id (str): The ID of the user to check.
            organization_id (str): The ID of the organization to check.

        Returns:
            bool: True if the user exists in the organization, False otherwise.
        """
        user_organization_key = cls.get_organization_user_cache_key(
            user_id, organization_id
        )
        return CacheService.check_a_key_exist(user_organization_key)

    @classmethod
    def set_user_membership_in_organization_cache(
        cls, user_id: str, organization_id: str
    ) -> None:
        """Set a user's membership in an organization in the cache.

        Parameters:
            user_id (str): The ID of the user.
            organization_id (str): The ID of the organization.
        """
        user_organization_key = cls.get_organization_user_cache_key(
            user_id, organization_id
        )
        CacheService.set_key(user_organization_key, {})

    @classmethod
    def remove_user_membership_in_organization_cache(
        cls, user_id: str, organization_id: str
    ) -> None:
        """Remove a user's membership in an organization from the cache.

        Parameters:
            user_id (str): The ID of the user.
            organization_id (str): The ID of the organization.
        """
        user_organization_key = cls.get_organization_user_cache_key(
            user_id, organization_id
        )
        CacheService.delete_a_key(user_organization_key)
