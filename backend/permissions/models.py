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
        return [membership.user for membership in self.owner_memberships()]

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
        # ``.all()`` hits the prefetch cache in list views; 1 query otherwise.
        return sum(
            m.role == ResourceRole.OWNER
            for m in self.memberships.all()  # type: ignore[attr-defined]
        )

    def is_owner(self, user: Any) -> bool:
        if user is None:
            return False
        return any(
            m.user_id == user.id and m.role == ResourceRole.OWNER
            for m in self.memberships.all()  # type: ignore[attr-defined]
        )
