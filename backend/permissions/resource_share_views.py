"""Shared share-management surface for resource ViewSets.

The mixin is **axis-agnostic** — it reads the sharing "axes" named in
``_SUPPORTED_SHARE_AXES``. ``shared_users`` is the direct-viewer axis, backed by
VIEWER membership rows, while ``shared_groups`` is stored polymorphically in
``ResourceGroupShare`` (not an M2M) and routed through the sharing helpers.
"""

from typing import Any

from django.db.models import Model
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

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
        from tenant_account_v2.sharing_helpers import ShareAuthorizationService

        resource = self.get_object()  # type: ignore[attr-defined]
        desired = _extract_desired_share_state(request.data)
        ShareAuthorizationService.authorize_and_commit(
            actor=request.user, resource=resource, desired=desired
        )
        return Response(status=status.HTTP_200_OK)

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

        The mixin's canonical axis reader — each axis has a different backing
        store, so callers that need an axis's contents (e.g. diffing a share
        before and after) go through here rather than touching the store.

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
