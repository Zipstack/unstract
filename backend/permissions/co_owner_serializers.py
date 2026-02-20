"""Shared serializers for co-owner management across resource types."""

from typing import Any

from account_v2.models import User
from django.db import models
from rest_framework import serializers
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext


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
