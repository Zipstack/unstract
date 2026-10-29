import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class InboxItemManager(DefaultOrganizationManagerMixin, BaseModelManager):
    pass


class InboxItem(DefaultOrganizationMixin, BaseModel):
    """One notification in a user's inbox for one organization."""

    class Kind(models.TextChoices):
        RESOURCE_SHARED = "resource_shared", "Resource shared"
        EXECUTION_FAILED = "execution_failed", "Execution failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inbox_items")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    route = models.JSONField(
        null=True,
        blank=True,
        db_comment="Where the item opens: {key, params} as in global search, or null",
    )
    dedupe_key = models.CharField(
        max_length=255,
        db_comment=(
            "One item per user per key. A failed run's key names its source, so "
            "later failures refresh the item; each share action has its own key"
        ),
    )
    read_at = models.DateTimeField(null=True, blank=True)

    objects = InboxItemManager()

    class Meta:
        db_table = "inbox_item"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "dedupe_key"],
                name="unique_inbox_item_per_event",
            ),
            # NULLs are distinct in the unique constraint above, so a NULL
            # organization would escape it.
            models.CheckConstraint(
                check=models.Q(organization__isnull=False),
                name="inbox_item_has_organization",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "user", "-created_at"],
                name="inbox_item_user_newest",
            ),
            # The daily purge's cutoff.
            models.Index(fields=["created_at"], name="inbox_item_created"),
            # Withdrawing a failed-run item when its run finishes clean.
            models.Index(fields=["organization", "dedupe_key"], name="inbox_item_event"),
        ]
