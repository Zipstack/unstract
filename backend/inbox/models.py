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
        max_length=255, db_comment="Identifies the event, so it lands once per user"
    )
    read_at = models.DateTimeField(null=True, blank=True)

    objects = InboxItemManager()

    class Meta:
        db_table = "inbox_item"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "dedupe_key"],
                name="unique_inbox_item_per_event",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "user", "-created_at"],
                name="inbox_item_user_newest",
            )
        ]
