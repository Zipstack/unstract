"""SQLAlchemy-inspired Django models for Agentic Studio v2.

All models ported from autoprompt's SQLAlchemy implementation to Django ORM,
maintaining feature parity while integrating with Unstract's architecture.
"""

import uuid
from datetime import datetime, timezone

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


def utcnow():
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class AgenticProjectManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticProject with organization filtering."""

    pass


class AgenticProject(DefaultOrganizationMixin, BaseModel):
    """Agentic project for automated prompt generation.

    Extends CustomTool concept with multi-stage pipeline for:
    - Document summarization
    - Schema generation
    - Prompt generation
    - Iterative tuning
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=255,
        db_comment="Project name",
    )

    description = models.TextField(
        blank=True,
        null=True,
        db_comment="Project description",
    )

    # Project-level LLM settings (reuse existing AdapterInstance)
    extractor_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_extractor",
        db_comment="LLM adapter for extraction operations",
    )

    agent_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_agent",
        db_comment="LLM adapter for agent operations (summarization, tuning)",
    )

    llmwhisperer = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_llmwhisperer",
        db_comment="LLMWhisperer adapter for document processing",
    )

    lightweight_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_lightweight",
        db_comment="Lightweight LLM for comparison and classification tasks",
    )

    # Canary fields for regression testing during prompt tuning
    canary_fields = models.JSONField(
        null=True,
        blank=True,
        db_comment="List of high-value field paths to check for regressions during tuning",
    )

    # Wizard completion tracking
    wizard_completed = models.BooleanField(
        default=False,
        db_comment="Whether the agentic wizard setup has been completed",
    )

    # Pipeline state tracking (stored in database, no Redis)
    pipeline_state = models.JSONField(
        null=True,
        blank=True,
        db_comment="Pipeline processing state for stages (raw_text, summary, schema, prompt, extraction)",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_created",
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agentic_projects_modified",
    )

    # Use default manager instead of AgenticProjectManager to avoid UserContext issues
    # Filtering by organization is done at the ViewSet level
    objects = models.Manager()

    class Meta:
        verbose_name = "Agentic Project"
        verbose_name_plural = "Agentic Projects"
        db_table = "agentic_project"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_agentic_project_name_org",
            ),
        ]

    def get_pipeline_status(self):
        """Get current pipeline status from database (synchronous, no Redis).

        Returns dict with status for each stage: raw_text, summary, schema, prompt, extraction.
        """
        stages = ["raw_text", "summary", "schema", "prompt", "extraction"]

        # Initialize default state if not set
        if not self.pipeline_state:
            self.pipeline_state = {}

        # Build response with defaults for missing stages
        pipeline_status = {
            "project_id": str(self.id),
            "project_name": self.name,
            "stages": {},
        }

        for stage in stages:
            stage_data = self.pipeline_state.get(stage, {})
            pipeline_status["stages"][stage] = {
                "stage": stage,
                "status": stage_data.get("status", "pending"),
                "progress": stage_data.get("progress", 0),
                "message": stage_data.get("message", "Not started"),
                "metadata": stage_data.get("metadata", {}),
            }

        # Calculate overall progress
        total_progress = sum(s["progress"] for s in pipeline_status["stages"].values())
        pipeline_status["overall_progress"] = round(total_progress / len(stages), 2)

        # Determine overall status
        statuses = [s["status"] for s in pipeline_status["stages"].values()]
        if "failed" in statuses:
            pipeline_status["overall_status"] = "failed"
        elif "in_progress" in statuses:
            pipeline_status["overall_status"] = "in_progress"
        elif all(s == "completed" for s in statuses):
            pipeline_status["overall_status"] = "completed"
        else:
            pipeline_status["overall_status"] = "pending"

        return pipeline_status

    def set_stage_status(self, stage, status, progress=0, message="", metadata=None):
        """Update status for a specific pipeline stage (synchronous, database-backed).

        Args:
            stage: One of: raw_text, summary, schema, prompt, extraction
            status: One of: pending, in_progress, completed, failed
            progress: 0-100
            message: Human-readable status message
            metadata: Optional dict with additional data
        """
        if not self.pipeline_state:
            self.pipeline_state = {}

        self.pipeline_state[stage] = {
            "status": status,
            "progress": min(100, max(0, progress)),
            "message": message,
            "metadata": metadata or {},
        }
        self.save(update_fields=["pipeline_state"])

    def __str__(self):
        return f"AgenticProject: {self.name}"


class AgenticDocumentManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticDocument."""

    pass


class AgenticDocument(DefaultOrganizationMixin, BaseModel):
    """Document uploaded to agentic project for processing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="documents",
        db_comment="Parent agentic project",
    )

    original_filename = models.CharField(
        max_length=255,
        db_comment="Original filename of uploaded document",
    )

    stored_path = models.CharField(
        max_length=512,
        db_comment="Storage path for the document file",
    )

    size_bytes = models.BigIntegerField(
        default=0,
        db_comment="File size in bytes",
    )

    pages = models.IntegerField(
        null=True,
        blank=True,
        db_comment="Number of pages (for PDFs)",
    )

    uploaded_at = models.DateTimeField(
        default=utcnow,
        db_comment="Upload timestamp",
    )

    raw_text = models.TextField(
        null=True,
        blank=True,
        db_comment="Extracted text from LLMWhisperer",
    )

    highlight_metadata = models.TextField(
        null=True,
        blank=True,
        db_comment="JSON string of highlight coordinates for source references",
    )

    processing_job_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_comment="Celery task ID for async processing",
    )

    processing_error = models.TextField(
        null=True,
        blank=True,
        db_comment="Error message if processing failed",
    )

    objects = AgenticDocumentManager()

    class Meta:
        verbose_name = "Agentic Document"
        verbose_name_plural = "Agentic Documents"
        db_table = "agentic_document"
        indexes = [
            models.Index(fields=["project", "uploaded_at"]),
        ]

    def __str__(self):
        return f"AgenticDocument: {self.original_filename}"


class AgenticSchemaManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticSchema."""

    pass


class AgenticSchema(DefaultOrganizationMixin, BaseModel):
    """JSON Schema generated by agent workflow."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="schemas",
        db_comment="Parent agentic project",
    )

    json_schema = models.TextField(
        db_comment="JSON Schema string defining extraction structure",
    )

    version = models.IntegerField(
        default=1,
        db_comment="Schema version number",
    )

    is_active = models.BooleanField(
        default=True,
        db_comment="Whether this is the currently active schema",
    )

    created_by_agent = models.CharField(
        max_length=100,
        default="system",
        db_comment="Agent that generated this schema (uniformer, finalizer, manual)",
    )

    objects = AgenticSchemaManager()

    class Meta:
        verbose_name = "Agentic Schema"
        verbose_name_plural = "Agentic Schemas"
        db_table = "agentic_schema"
        indexes = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["project", "is_active"]),
        ]

    def __str__(self):
        return f"AgenticSchema v{self.version} for {self.project.name}"


class AgenticSummaryManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticSummary."""

    pass


class AgenticSummary(DefaultOrganizationMixin, BaseModel):
    """Document summary extracted by SummarizerAgent."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="summaries",
        db_comment="Parent agentic project",
    )

    document = models.ForeignKey(
        AgenticDocument,
        on_delete=models.CASCADE,
        related_name="summaries",
        db_comment="Source document",
    )

    summary_text = models.TextField(
        db_comment="Field candidates and descriptions extracted from document",
    )

    objects = AgenticSummaryManager()

    class Meta:
        verbose_name = "Agentic Summary"
        verbose_name_plural = "Agentic Summaries"
        db_table = "agentic_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "document"],
                name="unique_agentic_summary_project_doc",
            ),
        ]

    def __str__(self):
        return f"Summary for {self.document.original_filename}"


class AgenticVerifiedDataManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticVerifiedData."""

    pass


class AgenticVerifiedData(DefaultOrganizationMixin, BaseModel):
    """Ground truth data manually verified by user.

    Used for comparing against extracted data to measure accuracy.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="verified_data",
        db_comment="Parent agentic project",
    )

    document = models.ForeignKey(
        AgenticDocument,
        on_delete=models.CASCADE,
        related_name="verified_data",
        db_comment="Source document",
    )

    data = models.JSONField(
        db_comment="Ground truth JSON data",
    )

    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_comment="User who verified this data",
    )

    objects = AgenticVerifiedDataManager()

    class Meta:
        verbose_name = "Agentic Verified Data"
        verbose_name_plural = "Agentic Verified Data"
        db_table = "agentic_verified_data"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "document"],
                name="unique_agentic_verified_data_project_doc",
            ),
        ]

    def __str__(self):
        return f"Verified data for {self.document.original_filename}"


class AgenticExtractedDataManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticExtractedData."""

    pass


class AgenticExtractedData(DefaultOrganizationMixin, BaseModel):
    """Extracted data from running a prompt on a document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="extracted_data",
        db_comment="Parent agentic project",
    )

    document = models.ForeignKey(
        AgenticDocument,
        on_delete=models.CASCADE,
        related_name="extracted_data",
        db_comment="Source document",
    )

    prompt_version = models.ForeignKey(
        "AgenticPromptVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extracted_data",
        db_comment="Prompt version used for extraction",
    )

    data = models.JSONField(
        db_comment="Extracted JSON data",
    )

    extraction_job_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_comment="Celery task ID for async extraction",
    )

    objects = AgenticExtractedDataManager()

    class Meta:
        verbose_name = "Agentic Extracted Data"
        verbose_name_plural = "Agentic Extracted Data"
        db_table = "agentic_extracted_data"
        indexes = [
            models.Index(fields=["project", "document", "-created_at"]),
            models.Index(fields=["prompt_version", "-created_at"]),
        ]

    def __str__(self):
        return f"Extraction for {self.document.original_filename}"


class AgenticComparisonResultManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticComparisonResult."""

    pass


class AgenticComparisonResult(DefaultOrganizationMixin, BaseModel):
    """Field-level comparison result with error classification.

    Stores granular comparison data for analytics and mismatch matrix.
    """

    class ErrorType(models.TextChoices):
        TRUNCATION = "truncation", "Truncation"
        FORMAT = "format", "Format Error"
        MISSING = "missing", "Missing Value"
        MINOR = "minor", "Minor Difference"
        MAJOR = "major", "Major Difference"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="comparison_results",
        db_comment="Parent agentic project",
    )

    prompt_version = models.ForeignKey(
        "AgenticPromptVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_comment="Prompt version used",
    )

    document = models.ForeignKey(
        AgenticDocument,
        on_delete=models.CASCADE,
        related_name="comparison_results",
        db_comment="Source document",
    )

    field_path = models.CharField(
        max_length=512,
        db_comment="Dot-separated field path (e.g., 'customer.address.city')",
    )

    match = models.BooleanField(
        db_comment="Whether extracted value matches verified value",
    )

    normalized_extracted = models.TextField(
        null=True,
        blank=True,
        db_comment="Normalized extracted value for comparison",
    )

    normalized_verified = models.TextField(
        null=True,
        blank=True,
        db_comment="Normalized verified value for comparison",
    )

    error_type = models.CharField(
        max_length=50,
        choices=ErrorType.choices,
        null=True,
        blank=True,
        db_comment="Classification of the error type",
    )

    objects = AgenticComparisonResultManager()

    class Meta:
        verbose_name = "Agentic Comparison Result"
        verbose_name_plural = "Agentic Comparison Results"
        db_table = "agentic_comparison_result"
        indexes = [
            models.Index(fields=["project", "field_path", "document"]),
            models.Index(fields=["project", "match"]),
            models.Index(fields=["prompt_version", "match"]),
        ]

    def __str__(self):
        status = "✓" if self.match else "✗"
        return f"{status} {self.field_path} in {self.document.original_filename}"


class AgenticExtractionNoteManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticExtractionNote."""

    pass


class AgenticExtractionNote(DefaultOrganizationMixin, BaseModel):
    """Field-specific notes for extraction tuning guidance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="extraction_notes",
        db_comment="Parent agentic project",
    )

    document = models.ForeignKey(
        AgenticDocument,
        on_delete=models.CASCADE,
        related_name="extraction_notes",
        db_comment="Source document",
    )

    field_path = models.CharField(
        max_length=512,
        db_comment="Field path this note applies to",
    )

    note_text = models.TextField(
        db_comment="User's guidance for improving this field's extraction",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_comment="User who created the note",
    )

    objects = AgenticExtractionNoteManager()

    class Meta:
        verbose_name = "Agentic Extraction Note"
        verbose_name_plural = "Agentic Extraction Notes"
        db_table = "agentic_extraction_note"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "document", "field_path"],
                name="unique_agentic_note_project_doc_field",
            ),
        ]

    def __str__(self):
        return f"Note for {self.field_path} in {self.document.original_filename}"


class AgenticPromptVersionManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticPromptVersion."""

    pass


class AgenticPromptVersion(DefaultOrganizationMixin, BaseModel):
    """Versioned extraction prompts with accuracy tracking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        related_name="prompt_versions",
        db_comment="Parent agentic project",
    )

    version = models.IntegerField(
        db_comment="Sequential version number",
    )

    short_desc = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_comment="Brief description of changes",
    )

    long_desc = models.TextField(
        null=True,
        blank=True,
        db_comment="Detailed description of prompt evolution",
    )

    prompt_text = models.TextField(
        db_comment="The actual prompt template",
    )

    accuracy = models.FloatField(
        null=True,
        blank=True,
        db_comment="Overall accuracy (0.0 to 1.0) when tested",
    )

    is_active = models.BooleanField(
        default=False,
        db_comment="Whether this is the currently active prompt",
    )

    created_by_agent = models.CharField(
        max_length=100,
        default="prompt_architect",
        db_comment="Agent or process that created this version",
    )

    parent_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_versions",
        db_comment="Previous version this was tuned from",
    )

    objects = AgenticPromptVersionManager()

    class Meta:
        verbose_name = "Agentic Prompt Version"
        verbose_name_plural = "Agentic Prompt Versions"
        db_table = "agentic_prompt_version"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version"],
                name="unique_agentic_prompt_version",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "-version"]),
            models.Index(fields=["project", "is_active"]),
        ]

    def __str__(self):
        return f"Prompt v{self.version} for {self.project.name} (acc: {self.accuracy:.2%})" if self.accuracy else f"Prompt v{self.version} for {self.project.name}"


class AgenticSettingManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticSetting."""

    pass


class AgenticSetting(DefaultOrganizationMixin, BaseModel):
    """System-wide settings for agentic studio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        db_comment="Setting key",
    )

    value = models.TextField(
        db_comment="Setting value (JSON string for complex values)",
    )

    description = models.TextField(
        null=True,
        blank=True,
        db_comment="Human-readable description",
    )

    objects = AgenticSettingManager()

    class Meta:
        verbose_name = "Agentic Setting"
        verbose_name_plural = "Agentic Settings"
        db_table = "agentic_setting"

    def __str__(self):
        return f"Setting: {self.key}"


class AgenticLogManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for AgenticLog."""

    pass


class AgenticLog(DefaultOrganizationMixin, BaseModel):
    """Processing logs for debugging and audit trail."""

    class LogLevel(models.TextChoices):
        DEBUG = "DEBUG", "Debug"
        INFO = "INFO", "Info"
        WARN = "WARN", "Warning"
        ERROR = "ERROR", "Error"
        FATAL = "FATAL", "Fatal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(
        AgenticProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="logs",
        db_comment="Parent agentic project (null for system logs)",
    )

    level = models.CharField(
        max_length=20,
        choices=LogLevel.choices,
        db_comment="Log level",
    )

    message = models.TextField(
        db_comment="Log message",
    )

    metadata = models.JSONField(
        null=True,
        blank=True,
        db_comment="Additional structured data",
    )

    timestamp = models.DateTimeField(
        default=utcnow,
        db_index=True,
        db_comment="Log timestamp",
    )

    objects = AgenticLogManager()

    class Meta:
        verbose_name = "Agentic Log"
        verbose_name_plural = "Agentic Logs"
        db_table = "agentic_log"
        indexes = [
            models.Index(fields=["project", "-timestamp"]),
            models.Index(fields=["level", "-timestamp"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"
