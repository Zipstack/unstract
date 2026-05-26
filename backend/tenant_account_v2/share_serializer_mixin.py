"""Serializer mixin for the polymorphic ``shared_groups`` axis.

Each shareable resource serializer composes :class:`SharedGroupsSerializerMixin`
to write ``shared_groups`` into :class:`tenant_account_v2.models.ResourceGroupShare`
— the per-resource M2M field has been removed (see UN-2977).

Reads work via a ``shared_groups`` ``@property`` defined on each resource
model (returns ``QuerySet[OrganizationGroup]``); DRF's natural
``PrimaryKeyRelatedField`` serialization then yields a list of group IDs
without any custom ``to_representation``.

Two write modes share this mixin:

* **Writable field** (``queryset=…``) — ``create``/``update`` below commit the
  groups. Used by serializers that accept ``shared_groups`` on the resource
  payload directly (e.g. the cloud ``AgenticProject`` serializer).
* **Read-only field** (``read_only=True``) — the OSS resource serializers route
  every share mutation through the ``POST /<resource>/{id}/share/`` action, so
  ``create``/``update`` see no ``shared_groups`` and no-op for them.

Writable usage::

    class AgenticProjectSerializer(SharedGroupsSerializerMixin, ...):
        shared_groups = serializers.PrimaryKeyRelatedField(
            many=True,
            queryset=OrganizationGroup.objects.all(),
            required=False,
        )
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from tenant_account_v2.sharing_helpers import set_resource_share_groups


class SharedGroupsSerializerMixin:
    """Adds polymorphic ``shared_groups`` writes to a ModelSerializer."""

    def create(self, validated_data: dict[str, Any]) -> Any:
        groups = validated_data.pop("shared_groups", None)
        # Model save and group-share write must commit together so a failure
        # in the second step can't leave a created-but-unshared resource.
        with transaction.atomic():
            instance = super().create(validated_data)  # type: ignore[misc]
            if groups is not None:
                set_resource_share_groups(instance, [g.id for g in groups])
        return instance

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        groups = validated_data.pop("shared_groups", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)  # type: ignore[misc]
            if groups is not None:
                set_resource_share_groups(instance, [g.id for g in groups])
        return instance
