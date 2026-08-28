import uuid

from account_v2.models import User
from django.db import models
from django.utils import timezone
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class AgentKVKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=512, blank=True, default="")
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="agent_kv_keys_created",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    class Meta:
        db_table = "agent_kv_key"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_agent_kv_key_name_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"


class JobStatus(models.TextChoices):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentKVJob(DefaultOrganizationMixin, BaseModel):
    TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(
        AgentKVKey,
        on_delete=models.SET_NULL,
        null=True,
        related_name="jobs",
    )
    task_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    stage = models.CharField(max_length=32, blank=True, default="")
    stages = models.JSONField(default=dict, blank=True)
    pages_total = models.IntegerField(null=True, blank=True)
    input_ref = models.CharField(max_length=512, blank=True, default="")
    result_ref = models.CharField(max_length=512, blank=True, default="")
    usage_summary = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(null=True, blank=True)
    webhook_url = models.URLField(max_length=1024, blank=True, default="")

    class Meta:
        db_table = "agent_kv_job"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    @classmethod
    def mark_terminal(
        cls,
        job_id,
        organization_id,
        new_status,
        *,
        error="",
        result_ref="",
        usage_summary=None,
    ) -> bool:
        """The ONLY way to reach a terminal state (spec §5.4 write guard).

        Guarded UPDATE: at-least-once callbacks, cancel, and the sweep can all
        race; whoever lands first wins and everyone else no-ops.
        """
        fields = {"status": new_status, "completed_at": timezone.now()}
        if error:
            fields["error"] = error
        if result_ref:
            fields["result_ref"] = result_ref
        if usage_summary is not None:
            fields["usage_summary"] = usage_summary
        updated = (
            cls.objects.filter(id=job_id, organization_id=organization_id)
            .exclude(status__in=list(cls.TERMINAL))
            .update(**fields)
        )
        return updated == 1
