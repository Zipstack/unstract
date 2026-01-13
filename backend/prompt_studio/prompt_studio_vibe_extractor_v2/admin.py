from django.contrib import admin

from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)


@admin.register(VibeExtractorProject)
class VibeExtractorProjectAdmin(admin.ModelAdmin):
    """Admin interface for VibeExtractorProject."""

    list_display = [
        "project_id",
        "document_type",
        "status",
        "tool_id",
        "created_at",
        "modified_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["document_type", "project_id"]
    readonly_fields = [
        "project_id",
        "generation_output_path",
        "generation_progress",
        "created_by",
        "modified_by",
        "created_at",
        "modified_at",
    ]
