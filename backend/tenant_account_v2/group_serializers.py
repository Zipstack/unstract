"""Serializers for org-scoped group sharing (UN-2977 / mfbt UNS-612)."""

import logging
from typing import Any

from django.conf import settings
from django.db.models import Count, IntegerField, OuterRef, Subquery
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
)

logger = logging.getLogger(__name__)


class OrganizationGroupReadSerializer(serializers.ModelSerializer):
    """Read-side serializer for org-scoped groups."""

    member_count = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationGroup
        fields = (
            "id",
            "name",
            "description",
            "created_by",
            "member_count",
            "created_at",
            "modified_at",
        )
        read_only_fields = fields

    def get_member_count(self, obj: OrganizationGroup) -> int:
        # ``memberships__count`` is annotated by the viewset's queryset when
        # available; fall back to a count() so single-object serialization works.
        annotated = getattr(obj, "memberships__count", None)
        if annotated is not None:
            return int(annotated)
        return int(obj.memberships.count())


class OrganizationGroupWriteSerializer(serializers.ModelSerializer):
    """Write-side serializer for org-scoped groups."""

    class Meta:
        model = OrganizationGroup
        fields = ("name", "description")

    def _organization(self) -> Any:
        return self.context["organization"]

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValidationError("Group name must not be empty.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        organization = self._organization()

        # Quota check applies on create only (rename within an existing row
        # doesn't change the group count).
        if self.instance is None:
            current = OrganizationGroup.objects.filter(organization=organization).count()
            if current >= settings.MAX_GROUPS_PER_ORG:
                raise ValidationError(
                    {
                        "code": "MAX_GROUPS_PER_ORG_EXCEEDED",
                        "detail": (
                            f"Organization already has {current} groups "
                            f"(limit: {settings.MAX_GROUPS_PER_ORG})."
                        ),
                    }
                )
        return attrs


class GroupMemberSerializer(serializers.ModelSerializer):
    """List-side representation of a single group member."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    display_name = serializers.SerializerMethodField()
    joined_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = GroupMembership
        fields = ("user_id", "email", "display_name", "joined_at")

    def get_display_name(self, obj: GroupMembership) -> str:
        user = obj.user
        full_name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        return full_name or user.email


class GroupMemberAddSerializer(serializers.Serializer):
    """Validates a bulk-add payload of user ids against org membership + quota."""

    user_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        group: OrganizationGroup = self.context["group"]
        user_ids = list(dict.fromkeys(attrs["user_ids"]))  # dedupe, preserve order

        # All targets must be members of the same org.
        org_user_ids = set(
            OrganizationMember.objects.filter(
                organization=group.organization, user_id__in=user_ids
            ).values_list("user_id", flat=True)
        )
        missing = [uid for uid in user_ids if uid not in org_user_ids]
        if missing:
            raise ValidationError(
                {
                    "code": "USERS_NOT_IN_ORG",
                    "detail": "All users must be members of this organization.",
                    "missing_user_ids": missing,
                }
            )

        # Quota: count after this add (excluding duplicates already in the group).
        already_in_group = set(
            group.memberships.filter(user_id__in=user_ids).values_list(
                "user_id", flat=True
            )
        )
        to_add = [uid for uid in user_ids if uid not in already_in_group]
        projected = group.memberships.count() + len(to_add)
        if projected > settings.MAX_MEMBERS_PER_GROUP:
            raise ValidationError(
                {
                    "code": "MAX_MEMBERS_PER_GROUP_EXCEEDED",
                    "detail": (
                        f"Adding these users would bring the group to {projected} "
                        f"members (limit: {settings.MAX_MEMBERS_PER_GROUP})."
                    ),
                }
            )
        attrs["user_ids_to_add"] = to_add
        return attrs


class EffectiveMemberSerializer(serializers.Serializer):
    """Serializer for the ``effective-members/`` resource action.

    Output of the union-with-priority dedup (direct > group > org) on each
    shareable resource viewset.
    """

    ACCESS_DIRECT = "direct"
    ACCESS_GROUP = "group"
    ACCESS_ORG = "org"

    user_id = serializers.IntegerField()
    email = serializers.CharField()
    display_name = serializers.CharField()
    access_via = serializers.ChoiceField(
        choices=[ACCESS_DIRECT, ACCESS_GROUP, ACCESS_ORG]
    )
    group_id = serializers.IntegerField(required=False, allow_null=True)
    group_name = serializers.CharField(required=False, allow_null=True)


def list_groups_with_member_counts(organization: Any, user: Any | None = None) -> Any:
    """Helper: return OrganizationGroup queryset annotated with member_count.

    When ``user`` is provided, the result is restricted to groups the user
    belongs to — used by the ``?member=me`` filter for non-admin callers.
    """
    # Count via a decoupled subquery: an optional ``memberships__user`` filter
    # below constrains the same relation, so a join-based Count would collapse
    # to the filtered rows (member_count=1). The subquery counts independently.
    member_count_sq = (
        GroupMembership.objects.filter(group=OuterRef("pk"))
        .order_by()
        .values("group")
        .annotate(c=Count("pk"))
        .values("c")
    )
    qs = OrganizationGroup.objects.filter(organization=organization)
    if user is not None:
        qs = qs.filter(memberships__user=user)
    return qs.annotate(
        memberships__count=Subquery(member_count_sq, output_field=IntegerField())
    ).distinct()
