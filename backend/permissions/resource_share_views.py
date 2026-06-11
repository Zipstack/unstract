"""Shared share-management surface for resource ViewSets.

The mixin is **axis-agnostic** — it operates over the sharing "axes" declared
in :attr:`ResourceShareManagementMixin.share_axes`. ``shared_users`` is an M2M
on the resource model, while ``shared_groups`` is stored polymorphically in
``ResourceGroupShare`` (not an M2M) and routed through the sharing helpers; new
axes can be added by extending that attribute.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

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


@dataclass
class AxisDiff:
    """Pre/post snapshot for a single share axis (M2M field)."""

    before: set[Any] = field(default_factory=set)
    after: set[Any] = field(default_factory=set)

    @property
    def added(self) -> set[Any]:
        return self.after - self.before

    @property
    def removed(self) -> set[Any]:
        return self.before - self.after


class ResourceShareManagementMixin:
    """Adds the shared share-management surface to a resource ViewSet.

    Subclasses declare share axes via :attr:`share_axes`. The default
    covers ``shared_users`` + ``shared_groups``.
    """

    share_axes: ClassVar[tuple[str, ...]] = ("shared_users", "shared_groups")

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

    def snapshot_share_axes(self, instance: Model) -> dict[str, set[Any]]:
        """Capture every declared axis's current contents.

        Call BEFORE ``super().partial_update(...)``; pair with
        :meth:`diff_share_axes` afterward.
        """
        return {axis: self._read_axis(instance, axis) for axis in self.share_axes}

    def diff_share_axes(
        self,
        instance: Model,
        before: dict[str, set[Any]],
        request_data: dict[str, Any],
    ) -> dict[str, AxisDiff]:
        """Diff each axis that was touched by the request.

        Returns a dict keyed by axis name with only the axes present in
        ``request_data`` — callers can skip notification fan-out for axes
        the client did not modify.
        """
        instance.refresh_from_db()
        return {
            axis: AxisDiff(
                before=before[axis],
                after=self._read_axis(instance, axis),
            )
            for axis in self.share_axes
            if axis in request_data
        }

    @staticmethod
    def _read_axis(instance: Model, axis: str) -> set[Any]:
        """Return the current set of related objects on the given axis.

        ``shared_groups`` is stored polymorphically in
        ``ResourceGroupShare`` rather than as an M2M on the resource model
        — route reads through the helper. Other axes still live as M2M
        fields on the resource and use ``getattr`` access.
        """
        if axis == "shared_groups":
            # Lazy import — ``tenant_account_v2`` depends on the permissions
            # package being importable during Django app loading.
            from tenant_account_v2.sharing_helpers import (
                get_resource_share_groups,
            )

            return set(get_resource_share_groups(instance))
        return set(getattr(instance, axis).all())
