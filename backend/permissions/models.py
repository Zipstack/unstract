from typing import Any

from django.conf import settings
from django.db import models

from permissions.roles import ResourceRole


class ResourceMemberBase(models.Model):
    """Abstract membership row linking a user to a resource with a role.

    Concrete per-resource subclasses add the resource FK with
    ``related_name="memberships"`` plus ``unique_together`` and an index.
    Ownership (and, later, viewer access) lives here; the resource's
    ``created_by`` becomes audit-only.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",  # queried from the resource side only
    )
    role = models.CharField(
        max_length=16,
        choices=ResourceRole.choices,
        default=ResourceRole.VIEWER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class HasMembersMixin:
    """Owner accessors for resource models backed by the membership table.

    Requires the resource to expose the ``memberships`` reverse relation from
    its per-resource membership through model.
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
        return self.memberships.filter(  # type: ignore[attr-defined]
            role=ResourceRole.OWNER
        ).count()

    def is_owner(self, user: Any) -> bool:
        if user is None:
            return False
        return self.memberships.filter(  # type: ignore[attr-defined]
            user=user, role=ResourceRole.OWNER
        ).exists()
