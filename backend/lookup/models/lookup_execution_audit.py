"""LookupExecutionAudit model for tracking Look-Up execution history."""

import uuid
from decimal import Decimal

from django.db import models


class LookupExecutionAudit(models.Model):
    """Audit log for Look-Up executions.

    Tracks all execution attempts with detailed metadata for debugging
    and performance monitoring.
    """

    STATUS_CHOICES = [
        ("success", "Success"),
        ("partial", "Partial Success"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Execution Context
    lookup_project = models.ForeignKey(
        "lookup.LookupProject",
        on_delete=models.CASCADE,
        related_name="execution_audits",
        help_text="Look-Up project that was executed",
    )
    prompt_studio_project_id = models.UUIDField(
        null=True, blank=True, help_text="Associated Prompt Studio project if applicable"
    )
    execution_id = models.UUIDField(
        help_text="Groups all Look-Ups in a single execution batch"
    )
    file_execution_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Workflow file execution ID for tracking in API/ETL pipelines",
    )

    # Input/Output
    input_data = models.JSONField(help_text="Input data from Prompt Studio extraction")
    reference_data_version = models.IntegerField(
        help_text="Version of reference data used"
    )
    enriched_output = models.JSONField(
        null=True, blank=True, help_text="Enrichment data produced"
    )

    # LLM Details
    llm_provider = models.CharField(max_length=50, help_text="LLM provider used")
    llm_model = models.CharField(max_length=100, help_text="LLM model used")
    llm_prompt = models.TextField(help_text="Full prompt sent to LLM")
    llm_response = models.TextField(null=True, blank=True, help_text="Raw LLM response")
    llm_response_cached = models.BooleanField(
        default=False, help_text="Whether response was from cache"
    )

    # Performance Metrics
    execution_time_ms = models.IntegerField(
        null=True, blank=True, help_text="Total execution time in milliseconds"
    )
    llm_call_time_ms = models.IntegerField(
        null=True, blank=True, help_text="LLM API call time in milliseconds"
    )

    # Status & Errors
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, help_text="Execution status"
    )
    error_message = models.TextField(
        null=True, blank=True, help_text="Error details if failed"
    )
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[],
        help_text="Confidence score from LLM (0.00 to 1.00)",
    )

    # Timestamps
    executed_at = models.DateTimeField(
        auto_now_add=True, help_text="When the execution occurred"
    )

    class Meta:
        """Model metadata."""

        db_table = "lookup_execution_audit"
        ordering = ["-executed_at"]
        verbose_name = "Look-Up Execution Audit"
        verbose_name_plural = "Look-Up Execution Audits"
        indexes = [
            models.Index(fields=["lookup_project"]),
            models.Index(fields=["execution_id"]),
            models.Index(fields=["file_execution_id"]),
            models.Index(fields=["executed_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        """String representation."""
        return f"{self.lookup_project.name} - {self.status} - {self.executed_at}"

    @property
    def was_successful(self) -> bool:
        """Check if execution was successful."""
        return self.status in ["success", "partial"]

    @property
    def execution_duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        if self.execution_time_ms:
            return self.execution_time_ms / 1000.0
        return 0.0

    def clean(self):
        """Validate the audit record."""
        super().clean()
        from django.core.exceptions import ValidationError

        # Validate confidence score range
        if self.confidence_score is not None:
            if not (Decimal("0.00") <= self.confidence_score <= Decimal("1.00")):
                raise ValidationError(
                    f"Confidence score must be between 0.00 and 1.00, "
                    f"got {self.confidence_score}"
                )

        # Ensure error_message is provided for failed status
        if self.status == "failed" and not self.error_message:
            raise ValidationError("Error message is required for failed executions")

        # Ensure enriched_output is provided for success status
        if self.status == "success" and not self.enriched_output:
            raise ValidationError("Enriched output is required for successful executions")
