"""Django admin configuration for Agentic Studio v2 models."""

from django.contrib import admin

from .models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticExtractedData,
    AgenticExtractionNote,
    AgenticLog,
    AgenticProject,
    AgenticPromptVersion,
    AgenticSchema,
    AgenticSetting,
    AgenticSummary,
    AgenticVerifiedData,
)


@admin.register(AgenticProject)
class AgenticProjectAdmin(admin.ModelAdmin):
    """Admin for AgenticProject."""

    list_display = (
        "name",
        "wizard_completed",
        "created_at",
        "organization",
    )
    list_filter = ("wizard_completed", "created_at", "organization")
    search_fields = ("name", "description")
    readonly_fields = ("id", "created_at", "modified_at")
    filter_horizontal = ()

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "id",
                    "name",
                    "description",
                    "wizard_completed",
                )
            },
        ),
        (
            "LLM Configuration",
            {
                "fields": (
                    "extractor_llm",
                    "agent_llm",
                    "llmwhisperer",
                    "lightweight_llm",
                )
            },
        ),
        (
            "Advanced",
            {
                "fields": ("canary_fields",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "organization",
                    "created_by",
                    "modified_by",
                    "created_at",
                    "modified_at",
                )
            },
        ),
    )


@admin.register(AgenticDocument)
class AgenticDocumentAdmin(admin.ModelAdmin):
    """Admin for AgenticDocument."""

    list_display = (
        "original_filename",
        "project",
        "size_bytes",
        "pages",
        "uploaded_at",
        "has_raw_text",
    )
    list_filter = ("uploaded_at", "project")
    search_fields = ("original_filename", "stored_path")
    readonly_fields = ("id", "uploaded_at", "created_at", "modified_at")

    fieldsets = (
        (
            "Document Information",
            {
                "fields": (
                    "id",
                    "project",
                    "original_filename",
                    "stored_path",
                    "size_bytes",
                    "pages",
                    "uploaded_at",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "raw_text",
                    "highlight_metadata",
                    "processing_job_id",
                    "processing_error",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "organization",
                    "created_at",
                    "modified_at",
                )
            },
        ),
    )

    def has_raw_text(self, obj):
        """Check if document has extracted text."""
        return bool(obj.raw_text)

    has_raw_text.boolean = True
    has_raw_text.short_description = "Text Extracted"


@admin.register(AgenticSchema)
class AgenticSchemaAdmin(admin.ModelAdmin):
    """Admin for AgenticSchema."""

    list_display = (
        "project",
        "version",
        "is_active",
        "created_by_agent",
        "created_at",
    )
    list_filter = ("is_active", "created_by_agent", "created_at")
    search_fields = ("project__name", "json_schema")
    readonly_fields = ("id", "created_at", "modified_at")

    fieldsets = (
        (
            "Schema Information",
            {
                "fields": (
                    "id",
                    "project",
                    "version",
                    "is_active",
                    "created_by_agent",
                )
            },
        ),
        (
            "Schema Content",
            {
                "fields": ("json_schema",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "organization",
                    "created_at",
                    "modified_at",
                )
            },
        ),
    )


@admin.register(AgenticSummary)
class AgenticSummaryAdmin(admin.ModelAdmin):
    """Admin for AgenticSummary."""

    list_display = ("document", "project", "created_at")
    list_filter = ("created_at", "project")
    search_fields = ("document__original_filename", "summary_text")
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(AgenticVerifiedData)
class AgenticVerifiedDataAdmin(admin.ModelAdmin):
    """Admin for AgenticVerifiedData."""

    list_display = ("document", "project", "verified_by", "created_at")
    list_filter = ("created_at", "project", "verified_by")
    search_fields = ("document__original_filename",)
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(AgenticExtractedData)
class AgenticExtractedDataAdmin(admin.ModelAdmin):
    """Admin for AgenticExtractedData."""

    list_display = ("document", "project", "prompt_version", "created_at")
    list_filter = ("created_at", "project", "prompt_version")
    search_fields = ("document__original_filename",)
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(AgenticComparisonResult)
class AgenticComparisonResultAdmin(admin.ModelAdmin):
    """Admin for AgenticComparisonResult."""

    list_display = (
        "field_path",
        "document",
        "match",
        "error_type",
        "prompt_version",
        "created_at",
    )
    list_filter = ("match", "error_type", "created_at", "project")
    search_fields = ("field_path", "document__original_filename")
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(AgenticExtractionNote)
class AgenticExtractionNoteAdmin(admin.ModelAdmin):
    """Admin for AgenticExtractionNote."""

    list_display = ("field_path", "document", "project", "created_by", "created_at")
    list_filter = ("created_at", "project", "created_by")
    search_fields = ("field_path", "note_text", "document__original_filename")
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(AgenticPromptVersion)
class AgenticPromptVersionAdmin(admin.ModelAdmin):
    """Admin for AgenticPromptVersion."""

    list_display = (
        "project",
        "version",
        "accuracy_percentage",
        "is_active",
        "created_by_agent",
        "created_at",
    )
    list_filter = ("is_active", "created_by_agent", "created_at")
    search_fields = ("project__name", "short_desc", "prompt_text")
    readonly_fields = ("id", "created_at", "modified_at")

    fieldsets = (
        (
            "Version Information",
            {
                "fields": (
                    "id",
                    "project",
                    "version",
                    "is_active",
                    "parent_version",
                    "created_by_agent",
                )
            },
        ),
        (
            "Description",
            {
                "fields": (
                    "short_desc",
                    "long_desc",
                )
            },
        ),
        (
            "Prompt Content",
            {
                "fields": ("prompt_text",),
            },
        ),
        (
            "Performance",
            {
                "fields": ("accuracy",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "organization",
                    "created_at",
                    "modified_at",
                )
            },
        ),
    )

    def accuracy_percentage(self, obj):
        """Display accuracy as percentage."""
        if obj.accuracy is not None:
            return f"{obj.accuracy * 100:.2f}%"
        return "N/A"

    accuracy_percentage.short_description = "Accuracy"


@admin.register(AgenticSetting)
class AgenticSettingAdmin(admin.ModelAdmin):
    """Admin for AgenticSetting."""

    list_display = ("key", "value_preview", "description", "created_at")
    search_fields = ("key", "value", "description")
    readonly_fields = ("id", "created_at", "modified_at")

    def value_preview(self, obj):
        """Show truncated value."""
        if len(obj.value) > 50:
            return f"{obj.value[:50]}..."
        return obj.value

    value_preview.short_description = "Value"


@admin.register(AgenticLog)
class AgenticLogAdmin(admin.ModelAdmin):
    """Admin for AgenticLog."""

    list_display = ("level", "message_preview", "project", "timestamp")
    list_filter = ("level", "timestamp", "project")
    search_fields = ("message",)
    readonly_fields = ("id", "timestamp", "created_at", "modified_at")

    def message_preview(self, obj):
        """Show truncated message."""
        if len(obj.message) > 100:
            return f"{obj.message[:100]}..."
        return obj.message

    message_preview.short_description = "Message"
