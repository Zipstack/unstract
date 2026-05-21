import logging
from typing import Any

from account_v2.custom_exceptions import AmbiguousUserException
from account_v2.user_filter_registry import UserFilterRegistry
from django.db.models import QuerySet
from utils.cache_service import CacheService

from tenant_account_v2.models import OrganizationMember

logger = logging.getLogger(__name__)


class OrganizationMemberService:
    @staticmethod
    def get_user_by_email(email: str) -> OrganizationMember | None:
        qs = UserFilterRegistry.apply(
            OrganizationMember.objects.filter(user__email=email),  # type: ignore
            "org_member",
        )
        return qs.first()

    @staticmethod
    def get_unique_user_by_email(email: str) -> OrganizationMember | None:
        """Resolve a single OrganizationMember by email or raise.

        Raises ``AmbiguousUserException`` when more than one row matches
        after registered filters apply — that signals either duplicate
        rows or a misconfigured identity-scoping filter, and silently
        picking one would propagate the wrong identity downstream.
        """
        qs = UserFilterRegistry.apply(
            OrganizationMember.objects.filter(user__email=email),  # type: ignore
            "org_member",
        )
        rows = list(qs[:2])
        if len(rows) > 1:
            # Log the matched member_ids (internal IDs, not PII) instead
            # of the raw email so ambiguity remains diagnosable from logs
            # without expanding PII retention.
            member_ids = list(qs.values_list("member_id", flat=True))
            logger.error(
                "Ambiguous OrganizationMember lookup by email "
                "(matched %d rows; member_ids=%s)",
                len(member_ids),
                member_ids,
            )
            raise AmbiguousUserException()
        return rows[0] if rows else None

    @staticmethod
    def get_user_by_user_id(user_id: str) -> OrganizationMember | None:
        qs = UserFilterRegistry.apply(
            OrganizationMember.objects.filter(user__user_id=user_id),  # type: ignore
            "org_member",
        )
        return qs.first()

    @staticmethod
    def get_user_by_id(id: str) -> OrganizationMember | None:
        """Retrieve an OrganizationMember by the user's primary key.

        PK lookups bypass the filter registry — the identifier is already
        unique, so scoping would only risk hiding a legitimate row (most
        critically, the executing admin's own row in role-change flows).
        """
        try:
            return OrganizationMember.objects.get(user=id)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    @staticmethod
    def get_members() -> QuerySet[OrganizationMember]:
        return UserFilterRegistry.apply(
            OrganizationMember.objects.filter(user__is_service_account=False),
            "org_member",
        )

    @staticmethod
    def get_members_by_role(role: str) -> QuerySet[OrganizationMember]:
        """Return members for the given role, ordered by member_id."""
        return UserFilterRegistry.apply(
            OrganizationMember.objects.filter(role=role, user__is_service_account=False),
            "org_member",
        ).order_by("member_id")

    @staticmethod
    def set_member_role(member_id: int, role: str) -> None:
        """Set the role of a member.

        Parameters:
            role (str): The role to set.
        """
        # Get and update member
        member = OrganizationMember.objects.get(member_id=member_id)
        member.role = role.lower()
        member.save()

    @staticmethod
    def get_members_by_user_email(
        user_emails: list[str], values_list_fields: list[str]
    ) -> list[dict[str, Any]]:
        """Get members by user emails.

        Parameters:
            user_emails (list[str]): The emails of the users to get.
            values_list_fields (list[str]): The fields to include in the result.

        Returns:
            list[dict[str, Any]]: The members.
        """
        if not user_emails:
            return []
        queryset = UserFilterRegistry.apply(
            OrganizationMember.objects.filter(user__email__in=user_emails),
            "org_member",
        )
        if values_list_fields is None:
            users = queryset.values()
        else:
            users = queryset.values_list(*values_list_fields)

        return list(users)

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
