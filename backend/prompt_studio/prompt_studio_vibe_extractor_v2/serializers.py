from rest_framework import serializers

from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)


class VibeExtractorProjectSerializer(serializers.ModelSerializer):
    """Serializer for VibeExtractorProject model."""

    class Meta:
        model = VibeExtractorProject
        fields = [
            "project_id",
            "document_type",
            "status",
            "generation_output_path",
            "error_message",
            "generation_progress",
            "tool_id",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
        ]
        read_only_fields = [
            "project_id",
            "status",
            "generation_output_path",
            "error_message",
            "generation_progress",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
        ]


class VibeExtractorProjectCreateSerializer(serializers.Serializer):
    """Serializer for creating a new Vibe Extractor project."""

    document_type = serializers.CharField(
        required=True,
        help_text="Document type name (e.g., invoice, receipt)",
    )
    tool_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Associated custom tool ID",
    )


class VibeExtractorGenerateSerializer(serializers.Serializer):
    """Serializer for triggering generation for a project."""

    regenerate = serializers.BooleanField(
        default=False,
        help_text="Whether to regenerate if files already exist",
    )


class VibeExtractorFileReadSerializer(serializers.Serializer):
    """Serializer for reading generated files."""

    file_type = serializers.ChoiceField(
        choices=[
            "metadata",
            "extraction",
            "page_extraction_system",
            "page_extraction_user",
            "scalars_extraction_system",
            "scalars_extraction_user",
            "tables_extraction_system",
            "tables_extraction_user",
        ],
        required=True,
        help_text="Type of file to read",
    )
