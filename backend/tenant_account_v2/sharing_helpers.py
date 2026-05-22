"""Shared helpers for group-based resource sharing.

Centralizes the per-resource hooks so each shareable viewset and serializer
plugs into the same logic.

* ``validate_shared_groups_in_org`` — serializer-level org scope check on
  the ``shared_groups`` M2M payload.
* ``compute_effective_members`` — union-with-priority dedup feeding the
  ``effective-members/`` resource action.
* ``serialize_group_refs`` — small ``[{id, name}]`` listing for the
  ``users/`` sharing-info endpoints, so the share modal can render the
  currently-shared groups.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from rest_framework.exceptions import ValidationError

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
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


def serialize_group_refs(resource_obj: Any) -> list[dict[str, Any]]:
    """Return a compact ``[{id, name, source}]`` listing for share modals."""
    return list(resource_obj.shared_groups.values("id", "name", "source"))


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

    # Group shares — collect via the resource's shared_groups M2M
    group_memberships = GroupMembership.objects.filter(
        group__in=resource_obj.shared_groups.all(),
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
