import uuid

from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class UsageType(models.TextChoices):
    LLM = "llm", "LLM Usage"
    EMBEDDING = "embedding", "Embedding Usage"


class LLMUsageReason(models.TextChoices):
    EXTRACTION = "extraction", "Extraction"
    CHALLENGE = "challenge", "Challenge"
    SUMMARIZE = "summarize", "Summarize"


class UsageModelManager(DefaultOrganizationManagerMixin, models.Manager):
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
        choices=LLMUsageReason.choices,
        null=True,
        blank=True,
        db_comment="Reason for LLM usage. Empty if usage_type is 'embedding'. ",
    )
    model_name = models.CharField(max_length=255, db_comment="Name of the model used")
    embedding_tokens = models.IntegerField(
        db_comment="Number of tokens used for embedding"
    )
    prompt_tokens = models.IntegerField(
        db_comment="Number of tokens used for the prompt"
    )
    completion_tokens = models.IntegerField(
        db_comment="Number of tokens used for the completion"
    )
    total_tokens = models.IntegerField(db_comment="Total number of tokens used")
    cost_in_dollars = models.FloatField(db_comment="Total number of tokens used")
    # Manager
    objects = UsageModelManager()

    def __str__(self):
        return str(self.id)

    class Meta:
        db_table = "usage"
        indexes = [
            models.Index(fields=["run_id"]),
            models.Index(fields=["execution_id"]),
        ]
