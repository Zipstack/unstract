import logging
import uuid

from django.db import models
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

logger = logging.getLogger(__name__)


class UsageType(models.TextChoices):
    LLM = "llm", "LLM Usage"
    EMBEDDING = "embedding", "Embedding Usage"


# ── Extensible choice lists ─────────────────────────────────────────
# OSS defines base values. Cloud plugins append via try-import so that
# Django validation accepts cloud-specific values when the plugin is
# installed, without leaking cloud details into OSS code.

_LLM_USAGE_REASON_CHOICES: list[tuple[str, str]] = [
    ("extraction", "Extraction"),
    ("challenge", "Challenge"),
    ("summarize", "Summarize"),
]

_REFERENCE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("prompt_key", "Prompt Key"),
]

try:
    from pluggable_apps.lookups.constants import (
        CLOUD_LLM_USAGE_REASON_CHOICES,
        CLOUD_REFERENCE_TYPE_CHOICES,
    )

    _LLM_USAGE_REASON_CHOICES.extend(CLOUD_LLM_USAGE_REASON_CHOICES)
    _REFERENCE_TYPE_CHOICES.extend(CLOUD_REFERENCE_TYPE_CHOICES)
except ImportError:
    pass
except Exception:
    logger.warning("Failed to load cloud usage choices", exc_info=True)

LLM_USAGE_REASON_CHOICES = _LLM_USAGE_REASON_CHOICES
REFERENCE_TYPE_CHOICES = _REFERENCE_TYPE_CHOICES


class UsageModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    pass


class Usage(DefaultOrganizationMixin, BaseModel):
    # reference_type → reference_id mapping (no FK constraint):
    #   "prompt_key"  → ToolStudioPrompt UUID (OSS)
    #   Cloud plugins register additional types via CLOUD_REFERENCE_TYPE_CHOICES.
    # Usage records survive entity deletion.

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
