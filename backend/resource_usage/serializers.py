"""The usage response, typed for the published schema (with README.md)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db.models import Model
from rest_framework import serializers

from resource_usage.constants import (
    ConnectorRole,
    ItemType,
    ProfileKind,
    UsageGroup,
    UsedAs,
)
from resource_usage.references import ProfileUsage, Reference


class UsageItemSerializer(serializers.Serializer):
    id = serializers.CharField(
        allow_null=True, help_text="Identifier to route to; null if not accessible."
    )
    name = serializers.CharField(
        allow_null=True, help_text="Display name; null if not accessible."
    )
    type = serializers.ChoiceField(
        choices=[item.value for item in ItemType],
        help_text="What the item is. Cloud groups can add other values.",
    )
    accessible = serializers.BooleanField(
        help_text="The caller may open the item. Items they can't open are "
        "still listed and counted, without id or name."
    )
    blocks_delete = serializers.BooleanField(
        help_text="This item is why deleting the profile is refused."
    )


class ConnectorUsageItemSerializer(UsageItemSerializer):
    role = serializers.ChoiceField(
        choices=[role.value for role in ConnectorRole], allow_null=True
    )


def _groups_field(item: type[serializers.Serializer]) -> serializers.DictField:
    return serializers.DictField(
        child=serializers.ListField(child=item()),
        help_text="Keyed by group: always workflows, prompt_studio_projects, "
        "deployments and pipelines; other groups appear when they have items.",
    )


class AdapterUsageSerializer(serializers.Serializer):
    id = serializers.CharField()
    used_in_count = serializers.IntegerField()
    groups = _groups_field(UsageItemSerializer)


class ConnectorUsageSerializer(serializers.Serializer):
    id = serializers.CharField()
    used_in_count = serializers.IntegerField()
    used_as = serializers.ChoiceField(choices=[used.value for used in UsedAs])
    groups = _groups_field(ConnectorUsageItemSerializer)


def _accessible_pks(user: Any, refs: list[Reference]) -> set[tuple[type[Model], str]]:
    """``(model, pk)`` of each referenced item the user may open."""
    by_model: dict[type[Model], list[Any]] = defaultdict(list)
    for ref in refs:
        by_model[ref.model].append(ref.pk)
    accessible: set[tuple[type[Model], str]] = set()
    for model, pks in by_model.items():
        for_user = getattr(model.objects, "for_user", None)
        if for_user is None:
            continue
        visible = for_user(user).filter(pk__in=pks).values_list("pk", flat=True)
        accessible |= {(model, str(pk)) for pk in visible}
    return accessible


def usage_payload(
    kind: ProfileKind, profile: Model, usage: ProfileUsage, user: Any
) -> dict[str, Any]:
    refs = list(usage.references.values())
    accessible = _accessible_pks(user, refs)
    groups: dict[str, list[dict[str, Any]]] = {group.value: [] for group in UsageGroup}
    items = []
    for ref in refs:
        can_open = (ref.model, str(ref.pk)) in accessible
        item: dict[str, Any] = {
            "id": str(ref.pk) if can_open else None,
            "name": ref.name if can_open else None,
            "type": ref.item_type,
            "accessible": can_open,
            "blocks_delete": ref.blocks_delete,
        }
        if kind == ProfileKind.CONNECTOR:
            item["role"] = ref.role
        items.append((ref.group, item))
    # Accessible items first, by name; the rest after.
    items.sort(
        key=lambda pair: (not pair[1]["accessible"], (pair[1]["name"] or "").lower())
    )
    for group, item in items:
        groups.setdefault(group, []).append(item)

    payload: dict[str, Any] = {
        "id": str(profile.pk),
        "used_in_count": usage.used_in_count,
    }
    if kind == ProfileKind.CONNECTOR:
        payload["used_as"] = usage.used_as
    payload["groups"] = groups
    return payload
