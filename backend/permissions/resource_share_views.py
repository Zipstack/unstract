"""Shared share-management surface for resource ViewSets.

The mixin is **axis-agnostic** — it reads the sharing "axes" named in
``_SUPPORTED_SHARE_AXES``. ``shared_users`` is the direct-viewer axis, backed by
VIEWER membership rows, while ``shared_groups`` is stored polymorphically in
``ResourceGroupShare`` (not an M2M) and routed through the sharing helpers.
"""

import logging
from typing import Any

from django.db.models import Model
from plugins import get_plugin
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)

notification_plugin = get_plugin("notification")

_SUPPORTED_SHARE_AXES = ("shared_users", "shared_groups", "shared_to_org")


def _extract_desired_share_state(payload: Any) -> dict[str, Any]:
    """Normalize a POST /share/ body into the dispatcher's keyword shape.

    Accepts only the three known axes; unknown keys are rejected so client
    bugs surface loudly. Empty payload is allowed (no-op) for symmetry with
    "clear my share state" requests.
    """
    if not isinstance(payload, dict):
        raise ValidationError({"detail": "Request body must be a JSON object."})
    unknown = set(payload) - set(_SUPPORTED_SHARE_AXES)
    if unknown:
        raise ValidationError({"detail": f"Unsupported share axes: {sorted(unknown)}."})
    desired: dict[str, Any] = {}
    for axis in ("shared_users", "shared_groups"):
        if axis in payload:
            desired[axis] = _coerce_id_list(axis, payload[axis])
    if "shared_to_org" in payload:
        desired["shared_to_org"] = bool(payload["shared_to_org"])
    return desired


def _coerce_id_list(axis: str, value: Any) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValidationError({axis: "Must be a list of integer IDs."})
    coerced: list[int] = []
    for raw in value:
        try:
            coerced.append(int(raw))
        except (TypeError, ValueError) as exc:
            raise ValidationError({axis: f"Invalid ID: {raw!r}"}) from exc
    return coerced


def _notification_context(view: Any, instance: Any) -> tuple[str, str] | None:
    """Resolve ``(resource_type, resource_name)`` for the email senders.

    ``None`` when the plugin is absent or the host ViewSet has not opted in by
    setting ``notification_resource_name_field`` and overriding
    ``get_notification_resource_type`` (both declared on
    ``OwnerManagementMixin``, which every share host also mixes in).
    """
    name_field = getattr(view, "notification_resource_name_field", None)
    resolve_type = getattr(view, "get_notification_resource_type", None)
    if not notification_plugin or not name_field or resolve_type is None:
        return None
    resource_type = resolve_type(instance)
    resource_name = getattr(instance, name_field, None)
    if resource_type is None or not resource_name:
        return None
    return resource_type, resource_name


def _users_left_without_access(instance: Model, users: set[Any]) -> list[Any]:
    """Narrow ``users`` to those with no remaining access to ``instance``.

    Someone dropped from ``shared_users`` may still reach the resource via a
    group or an org-wide share; telling them their access was removed would be
    wrong.
    """
    if not users:
        return []
    from tenant_account_v2.sharing_helpers import compute_effective_members

    retained = {member["user_id"] for member in compute_effective_members(instance)}
    return [user for user in users if user.pk not in retained]


def _send_share_notification(
    instance: Model, context: tuple[str, str], users: set[Any], actor: Any
) -> None:
    """Email users newly granted direct access. Best-effort."""
    resource_type, resource_name = context
    try:
        notification_plugin["service_class"]().send_sharing_notification(
            resource_type=resource_type,
            resource_name=resource_name,
            resource_id=str(instance.pk),
            shared_by=actor,
            shared_to=list(users),
            resource_instance=instance,
        )
    except Exception:
        logger.exception("Failed to send sharing notification for %s", instance.pk)


def _send_revoke_notification(
    instance: Model, context: tuple[str, str], users: list[Any], actor: Any
) -> None:
    """Email users whose direct access was revoked. Best-effort."""
    resource_type, resource_name = context
    try:
        notification_plugin["service_class"]().send_access_removed_notification(
            resource_type=resource_type,
            resource_name=resource_name,
            resource_id=str(instance.pk),
            removed_from=users,
            removed_by=actor,
            resource_instance=instance,
        )
    except Exception:
        logger.exception("Failed to send access-removed notification for %s", instance.pk)


class ResourceShareManagementMixin:
    """Adds the shared share-management surface to a resource ViewSet."""

    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request: Request, pk: str | None = None) -> Response:
        """Apply a replace-style share state for the resource.

        HTTP entry gate is the host viewset's ``get_permissions`` (currently
        ``IsOwnerOrSharedUserOrSharedToOrg`` on all 7 resources — see
        UN-2977 plan §B). Per-axis authorization (owner / org admin /
        shared user / group member) and scope checks (org-membership for
        users, group-membership for groups) live in
        ``ShareAuthorizationService``.
        """
        from tenant_account_v2.share_notifications import (
            notify_resource_group_share_changed,
        )
        from tenant_account_v2.sharing_helpers import ShareAuthorizationService

        resource = self.get_object()  # type: ignore[attr-defined]
        desired = _extract_desired_share_state(request.data)
        users_before = self._read_axis(resource, "shared_users")
        groups_before = self._read_axis(resource, "shared_groups")
        ShareAuthorizationService.authorize_and_commit(
            actor=request.user, resource=resource, desired=desired
        )
        # ``_commit`` is the only atomic block on this path, so it has already
        # committed — the diffs read persisted state and can never announce a
        # share that rolled back.
        resource.refresh_from_db()
        users_after = self._read_axis(resource, "shared_users")
        groups_after = self._read_axis(resource, "shared_groups")
        notify_resource_group_share_changed(
            resource=resource,
            added=groups_after - groups_before,
            removed=groups_before - groups_after,
            actor=request.user,
        )
        self._notify_shared_users(
            resource, users_after - users_before, users_before - users_after, request.user
        )
        return Response(status=status.HTTP_200_OK)

    def _notify_shared_users(
        self,
        instance: Any,
        added: set[Any],
        removed: set[Any],
        actor: Any,
        /,
    ) -> None:
        """Email users granted or denied direct access.

        Resource type and name come from the host's ``OwnerManagementMixin``
        seam, so every share host is covered without an override.
        """
        context = _notification_context(self, instance)
        if context is None:
            return
        if added:
            _send_share_notification(instance, context, added, actor)
        revoked = _users_left_without_access(instance, removed)
        if revoked:
            _send_revoke_notification(instance, context, revoked, actor)

    @action(detail=True, methods=["get"], url_path="effective-members")
    def effective_members(self, request: Request, pk: str | None = None) -> Response:
        """Return all users with access (direct/group/org), priority-deduped."""
        # Lazy import — ``tenant_account_v2`` is the canonical home of the
        # helper; importing at module load would pull a circular dep through
        # the permissions package.
        from tenant_account_v2.group_serializers import EffectiveMemberSerializer
        from tenant_account_v2.sharing_helpers import compute_effective_members

        # ``get_object`` is provided by the DRF ``GenericAPIView`` host class.
        members = compute_effective_members(self.get_object())  # type: ignore[attr-defined]
        return Response(EffectiveMemberSerializer(members, many=True).data)

    @staticmethod
    def _read_axis(instance: Model, axis: str) -> set[Any]:
        """Return the current set of related objects on the given axis.

        ``shared_users`` is the direct-viewer axis — since UN-2202 Phase 2 it
        is backed by VIEWER membership rows, not an M2M (all mixin hosts are
        membership-backed resources). ``shared_groups`` is stored
        polymorphically in ``ResourceGroupShare`` — route reads through the
        helper.
        """
        if axis == "shared_users":
            return set(instance.viewers())  # type: ignore[attr-defined]
        if axis == "shared_groups":
            # Lazy import — ``tenant_account_v2`` depends on the permissions
            # package being importable during Django app loading.
            from tenant_account_v2.sharing_helpers import (
                get_resource_share_groups,
            )

            return set(get_resource_share_groups(instance))
        return set(getattr(instance, axis).all())
