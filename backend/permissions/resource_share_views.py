"""Shared share-management surface for resource ViewSets.

The mixin is **axis-agnostic** — it operates over any number of M2M sharing
"axes" declared on the resource model. Phase-1 axes for UN-2977 are
``shared_users`` and ``shared_groups``; UN-2022 (co-owners) will append
``co_owners`` via the :attr:`ResourceShareManagementMixin.share_axes`
attribute without changes here.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

from django.db.models import Model
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response


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

    Subclasses declare share axes via :attr:`share_axes`. Phase-1 default
    covers ``shared_users`` + ``shared_groups``; UN-2022 will set
    ``share_axes = (..., "co_owners")`` on the relevant ViewSets.
    """

    share_axes: ClassVar[tuple[str, ...]] = ("shared_users", "shared_groups")

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
