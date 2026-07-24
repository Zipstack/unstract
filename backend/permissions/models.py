from typing import Any

from django.db import models

from permissions.roles import ResourceRole


class HasMembersMixin:
    """Owner / viewer accessors for resource models.

    Requires the resource to expose a ``memberships`` relation — a
    ``GenericRelation`` to :class:`tenant_account_v2.ResourceMembership`.
    """

    def owner_memberships(self) -> "models.QuerySet[Any]":
        return self.memberships.filter(  # type: ignore[attr-defined]
            role=ResourceRole.OWNER
        ).select_related("user")

    def owners(self) -> list[Any]:
        # Service accounts (machine identities) are excluded from the co-owner
        # surface everywhere (see ``AddOwnerSerializer``); keep them off the
        # roster so they never appear as removable co-owners.
        return [m.user for m in self.owner_memberships() if not m.user.is_service_account]

    def viewer_memberships(self) -> "models.QuerySet[Any]":
        return self.memberships.filter(  # type: ignore[attr-defined]
            role=ResourceRole.VIEWER
        ).select_related("user")

    def viewers(self) -> list[Any]:
        """Direct viewers (VIEWER role) — the membership successor to the old
        ``shared_users`` M2M (UN-2202 Phase 2).
        """
        return [membership.user for membership in self.viewer_memberships()]

    def co_owners_count(self) -> int:
        # ``.all()`` hits the prefetch cache in list views (``memberships__user``
        # keeps ``m.user`` cached); 1 query otherwise. Service accounts excluded
        # to match ``owners()``.
        return sum(
            m.role == ResourceRole.OWNER and not m.user.is_service_account
            for m in self.memberships.all()  # type: ignore[attr-defined]
        )

    def owner_email(self) -> str | None:
        # Email for the "Owned By" label. ``created_by`` is audit-only (UN-2202)
        # and the creator can be removed as owner, so it must not name the owner.
        # Reads the prefetched ``memberships`` (list views set ``memberships__user``)
        # to stay query-free; earliest live OWNER wins so the label names the same
        # roster as ``co_owners_count()`` and is stable across page loads.
        owners = [
            m
            for m in self.memberships.all()  # type: ignore[attr-defined]
            if m.role == ResourceRole.OWNER and not m.user.is_service_account
        ]
        if not owners:
            return None
        return min(owners, key=lambda m: m.created_at).user.email

    def is_owner(self, user: Any) -> bool:
        if user is None:
            return False
        return any(
            m.user_id == user.id and m.role == ResourceRole.OWNER
            for m in self.memberships.all()  # type: ignore[attr-defined]
        )
