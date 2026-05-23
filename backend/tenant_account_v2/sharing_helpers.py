"""Shared helpers for group-based resource sharing.

Centralizes the per-resource hooks so each shareable viewset and serializer
plugs into the same logic. Group shares are stored polymorphically in
:class:`tenant_account_v2.models.ResourceGroupShare` — these helpers are the
single layer that translates between the resource ergonomic surface (``obj``)
and the polymorphic table.

Helpers exposed:

* ``validate_shared_groups_in_org`` — serializer-level org scope check on
  the ``shared_groups`` write payload.
* ``get_resource_share_groups`` / ``set_resource_share_groups`` — read/write
  the set of groups currently shared with a resource.
* ``list_resources_shared_with_group`` — reverse lookup for the group-admin
  view.
* ``resources_visible_via_groups`` — subquery feeding each resource
  manager's ``for_user()`` Q-chain.
* ``compute_effective_members`` — union-with-priority dedup feeding the
  ``effective-members/`` resource action.
* ``serialize_group_refs`` — small ``[{id, name, source}]`` listing for
  the share modal's currently-shared listing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model, QuerySet
from rest_framework.exceptions import ValidationError

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
    ResourceGroupShare,
)

logger = logging.getLogger(__name__)


def validate_shared_groups_in_org(
    groups: Iterable[OrganizationGroup], organization: Organization
) -> list[OrganizationGroup]:
    """Reject any group not belonging to ``organization``.

    DRF's ``PrimaryKeyRelatedField`` resolves IDs to instances against the
    full table, so cross-org IDs must be filtered here.
    """
    groups = list(groups)
    foreign = [g for g in groups if g.organization_id != organization.id]
    if foreign:
        raise ValidationError(
            {
                "shared_groups": (
                    "All shared groups must belong to your organization "
                    f"(foreign group ids: {[g.id for g in foreign]})."
                )
            }
        )
    return groups


def get_resource_share_groups(resource_obj: Any) -> QuerySet[OrganizationGroup]:
    """Return the groups currently shared with ``resource_obj``."""
    return OrganizationGroup.objects.filter(
        resource_shares__content_type=ContentType.objects.get_for_model(
            type(resource_obj)
        ),
        resource_shares__object_id=str(resource_obj.pk),
    )


@transaction.atomic
def set_resource_share_groups(resource_obj: Any, group_ids: Iterable[int]) -> None:
    """Replace the set of groups shared with ``resource_obj``.

    Mirrors Django M2M ``.set()`` semantics for the polymorphic table —
    additions, removals, and no-ops are all handled. Caller is responsible
    for having already validated the IDs against the resource's
    organization via :func:`validate_shared_groups_in_org`.
    """
    content_type = ContentType.objects.get_for_model(type(resource_obj))
    object_id = str(resource_obj.pk)
    organization_id = getattr(resource_obj, "organization_id", None)
    if organization_id is None:
        raise ValueError(
            "set_resource_share_groups requires an org-scoped resource; "
            f"{type(resource_obj).__name__}({resource_obj.pk}) has no "
            "organization_id."
        )

    requested = set(group_ids)
    current_qs = ResourceGroupShare.objects.filter(
        content_type=content_type, object_id=object_id
    )
    current_ids = set(current_qs.values_list("group_id", flat=True))

    to_remove = current_ids - requested
    to_add = requested - current_ids

    if to_remove:
        current_qs.filter(group_id__in=to_remove).delete()

    if to_add:
        ResourceGroupShare.objects.bulk_create(
            [
                ResourceGroupShare(
                    group_id=group_id,
                    content_type=content_type,
                    object_id=object_id,
                    organization_id=organization_id,
                )
                for group_id in to_add
            ],
            ignore_conflicts=True,
        )


def list_resources_shared_with_group(
    group: OrganizationGroup, model: type[Model]
) -> QuerySet:
    """Resources of ``model`` shared with ``group`` (replaces
    ``model.objects.filter(shared_groups=group)``).
    """
    shared_object_ids = ResourceGroupShare.objects.filter(
        group=group,
        content_type=ContentType.objects.get_for_model(model),
    ).values("object_id")
    return model.objects.filter(pk__in=shared_object_ids)


def resources_visible_via_groups(
    model: type[Model], user_group_ids: Iterable[int]
) -> QuerySet[str]:
    """Subquery feeding ``for_user()``: object_ids of ``model`` rows
    shared with any group the user belongs to.
    """
    return ResourceGroupShare.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        group_id__in=user_group_ids,
    ).values("object_id")


def serialize_group_refs(resource_obj: Any) -> list[dict[str, Any]]:
    """Return a compact ``[{id, name, source}]`` listing for share modals."""
    return list(get_resource_share_groups(resource_obj).values("id", "name", "source"))


def compute_effective_members(resource_obj: Any) -> list[dict[str, Any]]:
    """Compute effective members of a shareable resource.

    Priority order: direct > group > org. A user listed via direct share
    suppresses any group/org entries for the same user; a group entry
    suppresses an org entry.

    Returns a list of dicts shaped for ``EffectiveMemberSerializer``.
    """
    seen: dict[int, dict[str, Any]] = {}

    # Direct shares
    direct_users = list(
        resource_obj.shared_users.filter(is_service_account=False).values(
            "id", "email", "first_name", "last_name"
        )
    )
    for u in direct_users:
        seen[u["id"]] = {
            "user_id": u["id"],
            "email": u["email"],
            "display_name": _display_name(u),
            "access_via": "direct",
            "group_id": None,
            "group_name": None,
        }

    # Group shares — via the polymorphic resource_group_share table
    group_memberships = GroupMembership.objects.filter(
        group__in=get_resource_share_groups(resource_obj),
    ).select_related("group", "user")
    for membership in group_memberships:
        user = membership.user
        if getattr(user, "is_service_account", False):
            continue
        if user.id in seen:
            continue
        seen[user.id] = {
            "user_id": user.id,
            "email": user.email,
            "display_name": _user_display_name(user),
            "access_via": "group",
            "group_id": membership.group_id,
            "group_name": membership.group.name,
        }

    # Org-wide share
    if getattr(resource_obj, "shared_to_org", False):
        organization = getattr(resource_obj, "organization", None)
        if organization is not None:
            org_members = (
                OrganizationMember.objects.filter(organization=organization)
                .exclude(user__is_service_account=True)
                .select_related("user")
            )
            for member in org_members:
                user = member.user
                if user.id in seen:
                    continue
                seen[user.id] = {
                    "user_id": user.id,
                    "email": user.email,
                    "display_name": _user_display_name(user),
                    "access_via": "org",
                    "group_id": None,
                    "group_name": None,
                }

    return list(seen.values())


def _display_name(user_dict: dict[str, Any]) -> str:
    parts = [
        (user_dict.get("first_name") or "").strip(),
        (user_dict.get("last_name") or "").strip(),
    ]
    full = " ".join(p for p in parts if p)
    return full or user_dict.get("email") or ""


def _user_display_name(user: User) -> str:
    full = (user.get_full_name() or "").strip()
    return full or user.email
