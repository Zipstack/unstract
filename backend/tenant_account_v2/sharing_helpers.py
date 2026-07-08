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
* ``serialize_group_refs`` — small ``[{id, name}]`` listing for
  the share modal's currently-shared listing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from account_v2.models import Organization, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.db.models import Model, QuerySet
from rest_framework.exceptions import ValidationError

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
    ResourceGroupShare,
    ResourceMembership,
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
            {"shared_groups": ("All shared groups must belong to your organization.")}
        )
    return groups


def get_resource_share_groups(resource_obj: Any) -> QuerySet[OrganizationGroup]:
    """Return the groups currently shared with ``resource_obj``."""
    filters: dict[str, Any] = {
        "resource_shares__content_type": ContentType.objects.get_for_model(
            type(resource_obj)
        ),
        "resource_shares__object_id": str(resource_obj.pk),
    }
    # Defense in depth: constrain to the resource's org so tenant isolation
    # lives in the read query itself, not only in UUID uniqueness + write-time
    # checks. ``organization_id`` is present on every shareable resource.
    organization_id = getattr(resource_obj, "organization_id", None)
    if organization_id is not None:
        filters["resource_shares__organization_id"] = organization_id
    return OrganizationGroup.objects.filter(**filters)


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
        # Guard the representable illegal state: a share row whose
        # ``organization`` disagrees with its group's. Callers validate org
        # membership upstream, so a mismatch here is a programming error.
        valid_ids = set(
            OrganizationGroup.objects.filter(
                id__in=to_add, organization_id=organization_id
            ).values_list("id", flat=True)
        )
        invalid = to_add - valid_ids
        if invalid:
            raise ValueError(
                "Cannot share with groups outside the resource's organization: "
                f"{sorted(invalid)}"
            )
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


def _safe_uuids(raw_ids: Iterable[Any]) -> list[uuid.UUID]:
    """Cast varchar ``object_id`` values to UUID, skipping malformed ones.

    ``ResourceGroupShare.object_id`` is intentionally varchar, so one corrupt
    value must not 500 the entire resource list for every member of the group.
    Malformed ids are skipped and logged rather than raised.
    """
    result: list[uuid.UUID] = []
    for s in raw_ids:
        if not s:
            continue
        try:
            result.append(uuid.UUID(s))
        except (ValueError, AttributeError, TypeError):
            logger.warning("Skipping malformed ResourceGroupShare.object_id=%r", s)
    return result


def list_resources_shared_with_group(
    group: OrganizationGroup, model: type[Model]
) -> QuerySet:
    """Resources of ``model`` shared with ``group`` (replaces
    ``model.objects.filter(shared_groups=group)``).

    Materialises IDs to Python so UUID-keyed PKs can be cast before the
    ``pk__in`` lookup — Postgres refuses the implicit ``uuid = character
    varying`` comparison when the varchar ``object_id`` subquery is fed in
    directly (same constraint as :func:`resources_visible_via_groups`).
    """
    raw_ids = ResourceGroupShare.objects.filter(
        group=group,
        content_type=ContentType.objects.get_for_model(model),
        organization_id=group.organization_id,
    ).values_list("object_id", flat=True)
    if isinstance(model._meta.pk, models.UUIDField):
        pks: list[Any] = _safe_uuids(raw_ids)
    else:
        pks = list(raw_ids)
    return model.objects.filter(pk__in=pks)


def resources_visible_via_groups(
    model: type[Model], user_group_ids: Iterable[int]
) -> list[Any]:
    """IDs of ``model`` rows shared with any group the user belongs to.

    Returns a Python list (not a subquery) so each value can be coerced to
    the resource PK type. ``ResourceGroupShare.object_id`` is a varchar; for
    UUID-keyed resources (all 7 in-scope today) Postgres refuses the
    implicit ``uuid = character varying`` comparison when this is fed into
    ``Q(pk__in=...)``, so we cast in Python instead. The result set is
    bounded by ``(groups user belongs to) × (shared rows of that model)``.
    """
    raw_ids = ResourceGroupShare.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        group_id__in=user_group_ids,
    ).values_list("object_id", flat=True)
    if isinstance(model._meta.pk, models.UUIDField):
        return _safe_uuids(raw_ids)
    return list(raw_ids)


def resources_visible_via_memberships(model: type[Model], user: Any) -> list[Any]:
    """PKs of ``model`` rows on which ``user`` holds a ``ResourceMembership``
    (OWNER or VIEWER).

    Per-user analogue of :func:`resources_visible_via_groups`.
    ``ResourceMembership.object_id`` is varchar, so a ``memberships__user`` JOIN
    makes Postgres refuse the implicit ``uuid = character varying`` comparison;
    we materialise the ids and cast in Python instead. Bounded by the rows the
    user is a member of.
    """
    raw_ids = ResourceMembership.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        user=user,
    ).values_list("object_id", flat=True)
    if isinstance(model._meta.pk, models.UUIDField):
        return _safe_uuids(raw_ids)
    return list(raw_ids)


def serialize_group_refs(resource_obj: Any) -> list[dict[str, Any]]:
    """Return a compact ``[{id, name}]`` listing for share modals."""
    return list(get_resource_share_groups(resource_obj).values("id", "name"))


def compute_effective_members(resource_obj: Any) -> list[dict[str, Any]]:
    """Compute effective members of a shareable resource.

    Priority order: direct > group > org. A user listed via direct share
    suppresses any group/org entries for the same user; a group entry
    suppresses an org entry.

    Returns a list of dicts shaped for ``EffectiveMemberSerializer``.
    """
    seen: dict[int, dict[str, Any]] = {}

    # Direct shares — VIEWER membership rows (UN-2202 Phase 2 successor to the
    # old ``shared_users`` M2M). Owners are excluded here: they hold the
    # resource, they are not "shared with" it (parity with prior behavior).
    for membership in resource_obj.viewer_memberships():
        user = membership.user
        if getattr(user, "is_service_account", False):
            continue
        seen[user.id] = {
            "user_id": user.id,
            "email": user.email,
            "display_name": _user_display_name(user),
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
    _add_org_members(seen, resource_obj)

    return list(seen.values())


def _add_org_members(seen: dict[int, dict[str, Any]], resource_obj: Any) -> None:
    """Add org-wide members to ``seen`` (skips users already recorded)."""
    if not getattr(resource_obj, "shared_to_org", False):
        return
    organization = getattr(resource_obj, "organization", None)
    if organization is None:
        return
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


def _user_display_name(user: User) -> str:
    full = (user.get_full_name() or "").strip()
    return full or user.email


# ---------------------------------------------------------------------------
# Share authorization (UN-2977 plan §A)
# ---------------------------------------------------------------------------


def is_org_admin(user: Any) -> bool:
    """Resolve admin role for ``user`` in their current organization.

    Returns ``False`` on any lookup failure or for service accounts. The
    role lookup goes through ``AuthenticationController`` so it honors the
    same admin definition the group viewset uses. Accepts ``Any`` to match
    DRF's ``request.user`` typing (``AbstractBaseUser | AnonymousUser``).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_service_account", False):
        return False
    try:
        # Lazy import to keep ``tenant_account_v2`` boot light and to avoid
        # circular import with ``account_v2.authentication_controller``.
        from account_v2.authentication_controller import AuthenticationController

        controller = AuthenticationController()
        member = controller.get_organization_members_by_user(user=user)
        return controller.is_admin_by_role(member.role)
    except (ObjectDoesNotExist, LookupError):
        # Not a member of any org (onboarding / just removed) is a normal
        # state, not an error — treat as non-admin without logging noise.
        return False
    except Exception:
        logger.exception("Error resolving admin role for user_id=%s", user.pk)
        return False


class ShareAuthorizationService:
    """Authorize and commit a desired share-state for a resource.

    Encapsulates the matrix from the UN-2977 plan: owner has full control;
    org admin can add or remove; direct shared users and group members can
    add (with scope limits) but not remove, and cannot toggle
    ``shared_to_org``. Service accounts bypass authorization — they already
    bypass other access controls.
    """

    USERS_AXIS = "shared_users"
    GROUPS_AXIS = "shared_groups"
    ORG_AXIS = "shared_to_org"

    AXIS_LABELS = {
        USERS_AXIS: "shared users",
        GROUPS_AXIS: "shared groups",
        ORG_AXIS: "organization sharing",
    }

    @classmethod
    def authorize_and_commit(
        cls,
        actor: Any,
        resource: Any,
        desired: dict[str, Any],
    ) -> None:
        """Validate, authorize, then apply the requested share state.

        ``desired`` may include any subset of ``shared_users``,
        ``shared_groups`` (lists of int IDs), and ``shared_to_org`` (bool).
        Axes absent from ``desired`` are not touched. ``actor`` is typed
        ``Any`` to match DRF's ``request.user``.
        """
        if getattr(actor, "is_service_account", False):
            cls._commit(resource, desired)
            return

        # Ownership is role-based (OWNER membership), not ``created_by``, since
        # UN-2202 — ``created_by`` is audit-only.
        is_owner = resource.is_owner(actor)
        is_admin = is_org_admin(actor)
        cls._authorize(actor, resource, desired, is_owner, is_admin)
        cls._commit(resource, desired)

    # ------------------------------------------------------------------ auth

    @classmethod
    def _authorize(
        cls,
        actor: Any,
        resource: Any,
        desired: dict[str, Any],
        is_owner: bool,
        is_admin: bool,
    ) -> None:
        if cls.USERS_AXIS in desired:
            cls._check_users_axis(resource, desired[cls.USERS_AXIS], is_owner, is_admin)
        if cls.GROUPS_AXIS in desired:
            cls._check_groups_axis(
                actor, resource, desired[cls.GROUPS_AXIS], is_owner, is_admin
            )
        if cls.ORG_AXIS in desired:
            cls._check_org_toggle(resource, desired[cls.ORG_AXIS], is_owner, is_admin)

    @classmethod
    def _check_users_axis(
        cls,
        resource: Any,
        desired_ids: Iterable[int],
        is_owner: bool,
        is_admin: bool,
    ) -> None:
        before, after = cls._diff_id_axis(resource, cls.USERS_AXIS, desired_ids)
        cls._reject_removal_if_unprivileged(
            axis=cls.USERS_AXIS,
            removed=before - after,
            is_owner=is_owner,
            is_admin=is_admin,
        )
        cls._validate_users_in_org(resource, after - before)

    @classmethod
    def _check_groups_axis(
        cls,
        actor: Any,
        resource: Any,
        desired_ids: Iterable[int],
        is_owner: bool,
        is_admin: bool,
    ) -> None:
        before, after = cls._diff_id_axis(resource, cls.GROUPS_AXIS, desired_ids)
        cls._reject_removal_if_unprivileged(
            axis=cls.GROUPS_AXIS,
            removed=before - after,
            is_owner=is_owner,
            is_admin=is_admin,
        )
        added = after - before
        if added:
            cls._validate_groups_in_org(resource, added)
            if not (is_owner or is_admin):
                cls._reject_groups_actor_not_member(actor, added)

    @classmethod
    def _check_org_toggle(
        cls, resource: Any, desired: bool, is_owner: bool, is_admin: bool
    ) -> None:
        if bool(desired) == bool(getattr(resource, cls.ORG_AXIS)):
            return
        if not (is_owner or is_admin):
            cls._raise_permission_denied(
                "Only the resource owner or an organization admin can toggle "
                "'shared_to_org'."
            )

    # ----------------------------------------------------------------- check

    @staticmethod
    def _reject_removal_if_unprivileged(
        axis: str, removed: set[int], is_owner: bool, is_admin: bool
    ) -> None:
        if not removed:
            return
        if is_owner or is_admin:
            return
        label = ShareAuthorizationService.AXIS_LABELS.get(axis, axis)
        ShareAuthorizationService._raise_permission_denied(
            f"Only the resource owner or an organization admin can remove {label}."
        )

    @staticmethod
    def _validate_users_in_org(resource: Any, added_user_ids: set[int]) -> None:
        if not added_user_ids:
            return
        member_user_ids = set(
            OrganizationMember.objects.filter(
                organization_id=resource.organization_id, user_id__in=added_user_ids
            ).values_list("user_id", flat=True)
        )
        missing = added_user_ids - member_user_ids
        if missing:
            raise ValidationError(
                {
                    ShareAuthorizationService.USERS_AXIS: (
                        "One or more users are not members of this organization."
                    )
                }
            )

    @staticmethod
    def _validate_groups_in_org(resource: Any, added_group_ids: set[int]) -> None:
        org_group_ids = set(
            OrganizationGroup.objects.filter(
                organization_id=resource.organization_id, id__in=added_group_ids
            ).values_list("id", flat=True)
        )
        missing = added_group_ids - org_group_ids
        if missing:
            raise ValidationError(
                {
                    ShareAuthorizationService.GROUPS_AXIS: (
                        "One or more groups don't belong to this organization."
                    )
                }
            )

    @staticmethod
    def _reject_groups_actor_not_member(actor: Any, added_group_ids: set[int]) -> None:
        member_group_ids = set(
            GroupMembership.objects.filter(
                user=actor, group_id__in=added_group_ids
            ).values_list("group_id", flat=True)
        )
        unauthorized = added_group_ids - member_group_ids
        if unauthorized:
            names = list(
                OrganizationGroup.objects.filter(id__in=unauthorized)
                .order_by("name")
                .values_list("name", flat=True)
            )
            label = (
                ", ".join(names)
                if names
                else ", ".join(str(i) for i in sorted(unauthorized))
            )
            ShareAuthorizationService._raise_permission_denied(
                f"Cannot share with groups you are not a member of: {label}."
            )

    # ----------------------------------------------------------- diff helpers

    @staticmethod
    def _diff_id_axis(
        resource: Any, axis: str, desired_ids: Iterable[int]
    ) -> tuple[set[int], set[int]]:
        before = ShareAuthorizationService._current_ids(resource, axis)
        after = {int(pk) for pk in desired_ids or ()}
        return before, after

    @staticmethod
    def _current_ids(resource: Any, axis: str) -> set[int]:
        if axis == ShareAuthorizationService.USERS_AXIS:
            return ShareAuthorizationService._current_viewer_ids(resource)
        if axis == ShareAuthorizationService.GROUPS_AXIS:
            return set(get_resource_share_groups(resource).values_list("id", flat=True))
        return set(getattr(resource, axis).values_list("pk", flat=True))

    @staticmethod
    def _current_viewer_ids(resource: Any) -> set[int]:
        """User ids holding a VIEWER membership row on ``resource``."""
        from permissions.roles import ResourceRole

        return set(
            resource.memberships.filter(role=ResourceRole.VIEWER).values_list(
                "user_id", flat=True
            )
        )

    # ----------------------------------------------------------------- write

    @classmethod
    @transaction.atomic
    def _commit(cls, resource: Any, desired: dict[str, Any]) -> None:
        if cls.USERS_AXIS in desired:
            cls._set_viewer_members(resource, desired[cls.USERS_AXIS] or [])
        if cls.GROUPS_AXIS in desired:
            set_resource_share_groups(resource, desired[cls.GROUPS_AXIS] or [])
        if cls.ORG_AXIS in desired:
            new_value = bool(desired[cls.ORG_AXIS])
            if bool(getattr(resource, cls.ORG_AXIS)) != new_value:
                setattr(resource, cls.ORG_AXIS, new_value)
                resource.save(update_fields=[cls.ORG_AXIS, "modified_at"])

    @staticmethod
    def _set_viewer_members(resource: Any, desired_ids: Iterable[int]) -> None:
        """Replace ``resource``'s VIEWER membership rows to match ``desired_ids``.

        Mirrors M2M ``.set()`` semantics over the membership table. OWNER rows
        are never touched: a desired id that is already an OWNER is left as-is
        (``unique_together`` forbids a second row), so owners are never demoted
        or duplicated (UN-2202 Phase 2).
        """
        from permissions.roles import ResourceRole

        desired = {int(pk) for pk in desired_ids or ()}
        memberships = resource.memberships
        current_viewer_ids = set(
            memberships.filter(role=ResourceRole.VIEWER).values_list("user_id", flat=True)
        )
        to_remove = current_viewer_ids - desired
        if to_remove:
            memberships.filter(role=ResourceRole.VIEWER, user_id__in=to_remove).delete()
        for user_id in desired - current_viewer_ids:
            # get_or_create: an existing OWNER row is returned untouched.
            memberships.get_or_create(
                user_id=user_id, defaults={"role": ResourceRole.VIEWER}
            )

    # ------------------------------------------------------------ exceptions

    @staticmethod
    def _raise_permission_denied(detail: str) -> None:
        # Lazy import — DRF's exceptions module is light but the local import
        # keeps the public surface of this helper module unchanged.
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied(detail)
