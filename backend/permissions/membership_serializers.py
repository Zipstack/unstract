from django.db import transaction
from rest_framework import serializers
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from permissions.roles import ResourceRole


class AddOwnerSerializer(serializers.Serializer):
    """Validate and add a user as an OWNER of the resource in context.

    Context requires ``resource``. A user already holding VIEWER access is
    promoted to OWNER.
    """

    user_id = serializers.IntegerField()

    def validate_user_id(self, value: int) -> int:
        resource = self.context["resource"]
        organization = UserContext.get_organization()
        member = (
            OrganizationMember.objects.filter(user__id=value, organization=organization)
            .select_related("user")
            .first()
        )
        if member is None:
            raise serializers.ValidationError("User not found in your organization.")
        # Service accounts are machine identities excluded from sharing/membership
        # everywhere else (see ``compute_effective_members``); keep them out of
        # ownership too.
        if member.user.is_service_account:
            raise serializers.ValidationError(
                "Service accounts cannot be added as owners."
            )
        if resource.memberships.filter(user_id=value, role=ResourceRole.OWNER).exists():
            raise serializers.ValidationError("User is already an owner.")
        return value

    def save(self, **kwargs) -> None:
        resource = self.context["resource"]
        # Reverse manager auto-scopes to this resource; promote a viewer or
        # create the owner row.
        resource.memberships.update_or_create(
            user_id=self.validated_data["user_id"],
            defaults={"role": ResourceRole.OWNER},
        )


class RemoveOwnerSerializer(serializers.Serializer):
    """Validate and remove an OWNER, guarding the last-owner invariant.

    Context requires ``resource`` and ``user_to_remove``.
    """

    def validate(self, attrs: dict) -> dict:
        resource = self.context["resource"]
        user = self.context["user_to_remove"]
        if not resource.memberships.filter(user=user, role=ResourceRole.OWNER).exists():
            raise serializers.ValidationError("User is not an owner of this resource.")
        return attrs

    def save(self, **kwargs) -> None:
        resource = self.context["resource"]
        user = self.context["user_to_remove"]
        with transaction.atomic():
            # Lock the resource so a concurrent removal can't drop the last two
            # owners at once.
            locked = type(resource).objects.select_for_update().get(pk=resource.pk)
            if locked.memberships.filter(role=ResourceRole.OWNER).count() <= 1:
                raise serializers.ValidationError(
                    "Cannot remove the last owner. Add another owner first."
                )
            locked.memberships.filter(user=user, role=ResourceRole.OWNER).delete()
