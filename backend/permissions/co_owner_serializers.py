"""Shared serializers for co-owner management across resource types."""

from typing import Any
from uuid import UUID

from account_v2.models import User
from django.db import models
from rest_framework import serializers
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext


class AddCoOwnerSerializer(serializers.Serializer):  # type: ignore[misc]
    """Serializer for adding a co-owner to a resource."""

    user_id = serializers.UUIDField()

    def validate_user_id(self, value: UUID) -> UUID:
        """Validate user exists in same organization and is not already an owner."""
        resource: models.Model = self.context["resource"]
        organization = UserContext.get_organization()

        # Check user exists in organization
        if not OrganizationMember.objects.filter(
            user__id=value, organization=organization
        ).exists():
            raise serializers.ValidationError("User not found in your organization.")

        user = User.objects.get(id=value)

        # Check user is not already the creator
        if resource.created_by == user:
            raise serializers.ValidationError("User is already an owner.")

        # Check user is not already a co-owner
        if resource.co_owners.filter(id=user.id).exists():
            raise serializers.ValidationError("User is already a co-owner.")

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

        # Count total owners (created_by + co_owners)
        total_owners = 1 if resource.created_by else 0
        total_owners += resource.co_owners.count()

        # Check user is actually a co-owner or the creator
        is_creator = resource.created_by == user_to_remove
        is_co_owner = resource.co_owners.filter(id=user_to_remove.id).exists()

        if not is_creator and not is_co_owner:
            raise serializers.ValidationError("User is not an owner of this resource.")

        # Prevent removal of last owner
        if total_owners <= 1:
            raise serializers.ValidationError(
                "Cannot remove the last owner. "
                "Add another owner before removing this one."
            )

        return attrs

    def save(self, **kwargs: Any) -> models.Model:
        """Remove user as owner."""
        resource: models.Model = self.context["resource"]
        user_to_remove: User = self.context["user_to_remove"]

        if resource.created_by == user_to_remove:
            # If removing the creator, promote a co-owner to creator
            new_creator = resource.co_owners.first()
            resource.co_owners.remove(new_creator)
            resource.created_by = new_creator
            resource.save(update_fields=["created_by"])
        else:
            resource.co_owners.remove(user_to_remove)

        return resource
