"""Shared serializers for co-owner management across resource types."""

from typing import Any

from account_v2.models import User
from django.db import models
from rest_framework import serializers
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext


class SharedUserListMixin:
    """Mixin providing shared_users, co_owners, and created_by serializer methods."""

    def get_shared_users(self, obj: models.Model) -> list[dict[str, Any]]:
        """Return list of shared users with id and email."""
        return [{"id": user.id, "email": user.email} for user in obj.shared_users.all()]

    def get_co_owners(self, obj: models.Model) -> list[dict[str, Any]]:
        """Return list of co-owners with id and email."""
        return [{"id": user.id, "email": user.email} for user in obj.co_owners.all()]

    def get_created_by(self, obj: models.Model) -> dict[str, Any] | None:
        """Return creator details."""
        if obj.created_by:
            return {"id": obj.created_by.id, "email": obj.created_by.email}
        return None


class CoOwnerRepresentationMixin:
    """Mixin to add co_owners_count, is_owner, created_by_email fields."""

    def add_co_owner_fields(
        self,
        instance: models.Model,
        representation: dict[str, Any],
        request: Any = None,
    ) -> dict[str, Any]:
        first_co_owner = instance.co_owners.first()
        if first_co_owner:
            created_by_email = first_co_owner.email
        elif instance.created_by:
            created_by_email = instance.created_by.email
        else:
            created_by_email = None
        representation["created_by_email"] = created_by_email
        representation["co_owners_count"] = instance.co_owners.count()
        representation["is_owner"] = (
            instance.co_owners.filter(pk=request.user.pk).exists()
            if request and hasattr(request, "user")
            else False
        )
        return representation


class AddCoOwnerSerializer(serializers.Serializer):  # type: ignore[misc]
    """Serializer for adding a co-owner to a resource."""

    user_id = serializers.IntegerField()

    def validate_user_id(self, value: int) -> int:
        """Validate user exists in same organization and is not already an owner."""
        resource: models.Model = self.context["resource"]
        organization = UserContext.get_organization()

        # Check user exists in organization
        if not OrganizationMember.objects.filter(
            user__id=value, organization=organization
        ).exists():
            raise serializers.ValidationError("User not found in your organization.")

        user = User.objects.get(id=value)

        # Check user is not already a co-owner (creator is always in co_owners)
        if resource.co_owners.filter(id=user.id).exists():
            raise serializers.ValidationError("User is already an owner.")

        return value

    def save(self, **kwargs: Any) -> models.Model:
        """Add user as co-owner."""
        resource: models.Model = self.context["resource"]
        user_id = self.validated_data["user_id"]
        user = User.objects.get(id=user_id)
        resource.co_owners.add(user)
        return resource


class RemoveCoOwnerSerializer(serializers.Serializer):  # type: ignore[misc]
    """Serializer for validating co-owner removal."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate removal won't leave resource without owners."""
        resource: models.Model = self.context["resource"]
        user_to_remove: User = self.context["user_to_remove"]

        # co_owners is the single source of truth (creator is always in it)
        if not resource.co_owners.filter(id=user_to_remove.id).exists():
            raise serializers.ValidationError("User is not an owner of this resource.")

        if resource.co_owners.count() <= 1:
            raise serializers.ValidationError(
                "Cannot remove the last owner. "
                "Add another owner before removing this one."
            )

        return attrs

    def save(self, **kwargs: Any) -> models.Model:
        """Remove user as owner. created_by is audit-only and never changes."""
        resource: models.Model = self.context["resource"]
        user_to_remove: User = self.context["user_to_remove"]
        resource.co_owners.remove(user_to_remove)
        return resource
