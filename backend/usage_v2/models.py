import uuid

from django.db import models
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

REFERENCE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("prompt_key", "Prompt Key"),
    ("lookup_version", "Lookup Version"),
]


class UsageModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    pass


class Usage(DefaultOrganizationMixin, BaseModel):
    # reference_type → reference_id (no FK; survives entity deletion):
    #   "prompt_key"     → ToolStudioPrompt UUID (OSS)
    #   "lookup_version" → LookupVersion UUID (cloud)

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
    reference_id = models.UUIDField(
        null=True,
        blank=True,
        db_comment=(
            "Polymorphic correlation ID (no FK constraint) linking to the "
            "entity that triggered this usage. Interpret via reference_type. "
            "OSS values: prompt_key UUID. "
            "NULL for most operations; survives entity deletion."
        ),
    )
    reference_type = models.CharField(
        max_length=64,
        choices=REFERENCE_TYPE_CHOICES,
        null=True,
        blank=True,
        db_comment=(
            "Discriminator for reference_id. "
            "OSS values: 'prompt_key'. "
            "NULL when reference_id is NULL."
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
                fields=["llm_usage_reason", "reference_id", "-created_at"],
                name="idx_usage_reason_ref_created",
            ),
        ]
        constraints = [
            # Both NULL or both set; a half-populated row is undecodable
            # at billing-aggregation time.
            models.CheckConstraint(
                check=(
                    models.Q(reference_id__isnull=True, reference_type__isnull=True)
                    | models.Q(reference_id__isnull=False, reference_type__isnull=False)
                ),
                name="usage_reference_pair_consistent",
            ),
            # TODO: add (usage_type, llm_usage_reason) consistency constraint
            # via ``ADD CONSTRAINT ... NOT VALID`` + batched ``VALIDATE`` —
            # legacy embedding rows have ``llm_usage_reason=''`` and the
            # default full-table scan would lock the billing table.
        ]
