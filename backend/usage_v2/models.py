import uuid

from django.db import models
from django.db.models import Q
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class UsageType(models.TextChoices):
    LLM = "llm", "LLM Usage"
    EMBEDDING = "embedding", "Embedding Usage"


class UsageStatus(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    ERROR = "ERROR", "Error"
    SKIPPED = "SKIPPED", "Skipped"


# Static union of OSS + cloud values — keeps OSS model state aligned with
# migration state so ``makemigrations --check`` doesn't drift in CI.

LLM_USAGE_REASON_CHOICES: list[tuple[str, str]] = [
    ("extraction", "Extraction"),
    ("challenge", "Challenge"),
    ("summarize", "Summarize"),
    ("lookup", "Lookup"),
]


class UsageModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    pass


class Usage(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Primary key for the usage entry, automatically generated UUID",
    )
    workflow_id = models.CharField(
        max_length=255, null=True, blank=True, db_comment="Identifier for the workflow"
    )
    execution_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_comment="Identifier for the execution instance",
    )
    adapter_instance_id = models.CharField(
        max_length=255, db_comment="Identifier for the adapter instance"
    )
    run_id = models.UUIDField(
        max_length=255, null=True, blank=True, db_comment="Identifier for the run"
    )
    usage_type = models.CharField(
        max_length=255,
        choices=UsageType.choices,
        db_comment="Type of usage, either 'llm' or 'embedding'",
    )
    llm_usage_reason = models.CharField(
        max_length=255,
        choices=LLM_USAGE_REASON_CHOICES,
        null=True,
        blank=True,
        db_comment="Reason for LLM usage. Empty if usage_type is 'embedding'. ",
    )
    model_name = models.CharField(max_length=255, db_comment="Name of the model used")
    embedding_tokens = models.IntegerField(
        db_comment="Number of tokens used for embedding"
    )
    prompt_tokens = models.IntegerField(db_comment="Number of tokens used for the prompt")
    completion_tokens = models.IntegerField(
        db_comment="Number of tokens used for the completion"
    )
    total_tokens = models.IntegerField(db_comment="Total number of tokens used")
    cost_in_dollars = models.FloatField(db_comment="Total number of tokens used")
    project_id = models.UUIDField(
        null=True,
        blank=True,
        db_comment=(
            "Prompt Studio project (tool) the call belongs to (no FK; survives "
            "tool deletion). NULL for embeddings and historical rows."
        ),
    )
    prompt_id = models.UUIDField(
        null=True,
        blank=True,
        db_comment=(
            "Prompt key UUID that triggered the call (no FK; survives prompt "
            "deletion). NULL for single-pass / embeddings / historical rows."
        ),
    )
    execution_time_ms = models.IntegerField(
        null=True,
        blank=True,
        db_comment="Wall-clock time for the operation in milliseconds",
    )
    status = models.CharField(
        max_length=16,
        choices=UsageStatus.choices,
        null=True,
        blank=True,
        db_comment="Operation outcome: SUCCESS, ERROR, or SKIPPED",
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        db_comment="Error details when status is ERROR",
    )
    # Manager
    objects = UsageModelManager()

    def __str__(self):
        return str(self.id)

    class Meta:
        db_table = "usage"
        indexes = [
            models.Index(fields=["run_id"]),
            models.Index(fields=["execution_id"]),
            models.Index(
                fields=["project_id", "-created_at"],
                name="idx_usage_project_created",
            ),
            models.Index(
                fields=["prompt_id", "-created_at"],
                name="idx_usage_prompt_created",
            ),
            models.Index(
                fields=["organization", "-created_at"],
                name="idx_usage_lookup_recent",
                condition=Q(llm_usage_reason="lookup"),
            ),
        ]
