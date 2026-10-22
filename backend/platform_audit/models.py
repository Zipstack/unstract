import uuid

from account_v2.models import Organization, User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

IMMUTABLE_MESSAGE = (
    "Platform audit events are immutable. Expired events are removed by the "
    "purge_platform_audit_events management command."
)


class ActorType(models.TextChoices):
    USER = "user", "User"
    API_KEY = "api_key", "API key"
    SYSTEM = "system", "System"


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError(IMMUTABLE_MESSAGE)

    def delete(self):
        raise PermissionError(IMMUTABLE_MESSAGE)


class PlatformAuditEventManager(models.Manager.from_queryset(ImmutableQuerySet)):
    def bulk_update(self, objs, fields, **kwargs):
        raise PermissionError(IMMUTABLE_MESSAGE)

    def purge(self, queryset: models.QuerySet) -> int:
        """Physically delete ``queryset``. Meant only for the retention purge."""
        deleted, _ = models.QuerySet.delete(queryset)
        return deleted


class PlatformAuditEvent(models.Model):
    """One admin-visible change to an organisation's platform settings.

    Rows are written only through :func:`platform_audit.recorder.record_platform_event`.
    The ORM refuses to update or delete one (``save()`` of an existing row,
    ``delete()``, queryset ``update()``/``delete()``); foreign-key cascades
    still apply (deleting the actor nulls ``actor``, deleting the organisation
    deletes its events), and so does ``objects.purge()``. This is a guard
    against accidental edits, not tamper evidence.

    The actor's identity is copied onto the row, so an event still reads
    correctly after the member is removed or the key deleted; ``actor`` itself
    is kept only as a convenience link.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="+",
        editable=False,
        # Every composite index below leads with organization, so a separate
        # one would only cost each insert another B-tree.
        db_index=False,
    )
    occurred_at = models.DateTimeField(default=timezone.now)

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    # Lower-cased so the case-insensitive ``actor`` filter can use the index.
    actor_email = models.CharField(max_length=254, blank=True, default="")
    actor_name = models.CharField(max_length=255, blank=True, default="")
    actor_key_id = models.CharField(max_length=64, blank=True, default="")
    actor_key_name = models.CharField(max_length=255, blank=True, default="")

    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=255, blank=True, default="")
    target_name = models.CharField(max_length=255, blank=True, default="")

    summary = models.TextField(blank=True, default="")
    changes = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    request_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    objects = PlatformAuditEventManager()

    class Meta:
        db_table = "platform_audit_event"
        verbose_name = "Platform Audit Event"
        verbose_name_plural = "Platform Audit Events"
        indexes = [
            models.Index(
                fields=["organization", "-occurred_at"], name="pae_org_time_idx"
            ),
            models.Index(
                fields=["organization", "action", "-occurred_at"],
                name="pae_org_action_time_idx",
            ),
            models.Index(
                fields=["organization", "actor_email", "-occurred_at"],
                name="pae_org_actor_time_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError(IMMUTABLE_MESSAGE)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(IMMUTABLE_MESSAGE)

    def __str__(self) -> str:
        return f"PlatformAuditEvent({self.id}, {self.action})"
