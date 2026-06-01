import uuid

from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.db import models
from pipeline_v2.models import Pipeline
from utils.models.base_model import BaseModel

from .enums import (
    AuthorizationType,
    BufferStatus,
    NotificationType,
    PlatformType,
)

NOTIFICATION_NAME_MAX_LENGTH = 255
AUTH_SIG_LENGTH = 64  # SHA-256 hex digest


class Notification(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=NOTIFICATION_NAME_MAX_LENGTH,
        db_comment="Name of the notification.",
        default="Notification",
    )
    url = models.URLField(null=True)  # URL for webhook or other endpoints
    authorization_key = models.CharField(
        max_length=255, blank=True, null=True
    )  # Authorization Key or API Key
    authorization_header = models.CharField(
        max_length=255, blank=True, null=True
    )  # Header Name for custom headers
    authorization_type = models.CharField(
        max_length=50,
        choices=AuthorizationType.choices(),
        default=AuthorizationType.NONE.value,
    )
    max_retries = models.IntegerField(
        default=0
    )  # Maximum number of times to retry webhook
    platform = models.CharField(
        max_length=50,
        choices=PlatformType.choices(),
        blank=True,
        null=True,
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices(),
        default=NotificationType.WEBHOOK.value,
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating whether the notification is active or not.",
    )
    notify_on_failures = models.BooleanField(
        default=False,
        db_comment=(
            "When True, fire only on failed runs — terminal status ERROR/STOPPED "
            "or any file in the run errored (partial failure). When False "
            "(default), fire on every terminal completion."
        ),
    )
    # Foreign keys to specific models
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    api = models.ForeignKey(
        APIDeployment,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        db_table = "notification"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "pipeline"], name="unique_name_pipeline"
            ),
            models.UniqueConstraint(fields=["name", "api"], name="unique_name_api"),
        ]

    def save(self, *args, **kwargs):
        # Validation for platforms
        valid_platforms = NotificationType(self.notification_type).get_valid_platforms()
        if self.platform and self.platform not in valid_platforms:
            raise ValueError(
                f"Invalid platform '{self.platform}' for notification type "
                f"'{self.notification_type}'. "
                f"Valid options are: {', '.join(valid_platforms)}."
            )

        # Allow saving only if the platform is valid or not required
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Notification {self.id}: (Type: {self.notification_type}, "
            f"Platform: {self.platform}, Url: {self.url}))"
        )


class NotificationBuffer(BaseModel):
    """Per-execution event buffered for clubbed (batched) dispatch.

    One row is written per workflow completion. The flush job groups rows by
    (organization, webhook_url, auth_sig), renders one clubbed message per
    group, and dispatches via the existing send_webhook_notification Celery
    task. Group key includes auth_sig because two notifications may share the
    same URL but use different credentials — they must dispatch separately.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="buffer_rows",
        db_comment=(
            "Source Notification. Cascade-delete is intentional: removing a "
            "Notification expresses intent to stop all future deliveries, "
            "including buffered ones."
        ),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="notification_buffer_rows",
        db_comment=(
            "Tenant scope. Mandatory grouping key — prevents cross-tenant "
            "leakage at flush time."
        ),
    )
    webhook_url = models.URLField(
        db_comment="Denormalized destination URL; grouping key.",
    )
    payload = models.JSONField(
        db_comment=(
            "Pre-structured execution data (execution_id, status, error_message, "
            "pipeline_name, pipeline_type) — NOT a final rendered message. The "
            "renderer formats this at dispatch time."
        ),
    )
    platform = models.CharField(
        max_length=50,
        choices=PlatformType.choices(),
        db_comment="SLACK / API — drives renderer selection at flush time.",
    )
    auth_sig = models.CharField(
        max_length=AUTH_SIG_LENGTH,
        db_comment=(
            "SHA-256 hex of (auth_type + auth_key + auth_header), computed at "
            "enqueue time. Grouping key — never store raw credentials here."
        ),
    )
    flush_after = models.DateTimeField(
        db_comment=(
            "created_at + NOTIFICATION_CLUB_INTERVAL, precomputed at enqueue. "
            "Read-at-enqueue contract: changing the env var only affects rows "
            "enqueued after the restart."
        ),
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatch_attempts = models.PositiveIntegerField(
        default=0,
        db_comment=(
            "Count of times this row has been claimed for dispatch (incremented "
            "on each PENDING -> SENDING transition). Bounds the reaper reclaim "
            "loop: at NOTIFICATION_MAX_DISPATCH_ATTEMPTS the row is dead-lettered "
            "instead of re-dispatched, so a lost terminal callback cannot redeliver "
            "forever."
        ),
    )
    status = models.CharField(
        max_length=16,
        choices=BufferStatus.choices(),
        default=BufferStatus.PENDING.value,
        db_comment=(
            "Lifecycle: PENDING -> SENDING (claimed by a flush tick) -> "
            "DISPATCHED on success / DEAD_LETTER on retry exhaustion or once "
            "dispatch_attempts hits NOTIFICATION_MAX_DISPATCH_ATTEMPTS. A SENDING "
            "row whose lease expires is reclaimed back to PENDING by the reaper."
        ),
    )

    class Meta:
        verbose_name = "Notification Buffer"
        verbose_name_plural = "Notification Buffers"
        db_table = "notification_buffer"
        indexes = [
            # Partial covering index — supports Index Only Scans on the flush
            # GROUP BY query and bounds index size to live PENDING backlog.
            # `platform` is part of the grouping key so SLACK and API rows on
            # the same (org, url, auth) split into separate dispatches.
            models.Index(
                fields=[
                    "organization",
                    "webhook_url",
                    "auth_sig",
                    "platform",
                    "flush_after",
                ],
                name="idx_notif_buffer_pending",
                condition=models.Q(status=BufferStatus.PENDING.value),
            ),
        ]

    def __str__(self) -> str:
        return (
            f"NotificationBuffer {self.id}: status={self.status} "
            f"flush_after={self.flush_after.isoformat() if self.flush_after else 'n/a'}"
        )
