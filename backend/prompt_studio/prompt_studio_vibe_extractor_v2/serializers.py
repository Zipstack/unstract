from rest_framework import serializers

from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)


class VibeExtractorProjectSerializer(serializers.ModelSerializer):
    """Serializer for VibeExtractorProject model."""

    class Meta:
        model = VibeExtractorProject
        fields = [
            "id",
            "document_type",
            "llm_adapter",
            "tool_id",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
        ]
        read_only_fields = [
            "id",
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


class VibeExtractorGenerateMetadataSerializer(serializers.Serializer):
    """Serializer for generating metadata only."""

    regenerate = serializers.BooleanField(
        default=False,
        help_text="Whether to regenerate if metadata already exists",
    )


class VibeExtractorGenerateExtractionFieldsSerializer(serializers.Serializer):
    """Serializer for generating extraction fields."""

    metadata = serializers.JSONField(
        required=True,
        help_text="Metadata dictionary to use for generation",
    )


class VibeExtractorGeneratePagePromptsSerializer(serializers.Serializer):
    """Serializer for generating page extraction prompts."""

    metadata = serializers.JSONField(
        required=True,
        help_text="Metadata dictionary to use for generation",
    )


class VibeExtractorGenerateScalarPromptsSerializer(serializers.Serializer):
    """Serializer for generating scalar extraction prompts."""

    metadata = serializers.JSONField(
        required=True,
        help_text="Metadata dictionary to use for generation",
    )
    extraction_yaml = serializers.CharField(
        required=True,
        help_text="Extraction YAML content",
    )


class VibeExtractorGenerateTablePromptsSerializer(serializers.Serializer):
    """Serializer for generating table extraction prompts."""

    metadata = serializers.JSONField(
        required=True,
        help_text="Metadata dictionary to use for generation",
    )
    extraction_yaml = serializers.CharField(
        required=True,
        help_text="Extraction YAML content",
    )


class VibeExtractorGuessDocumentTypeSerializer(serializers.Serializer):
    """Serializer for guessing document type from file."""

    file_name = serializers.CharField(
        required=True,
        help_text="Name of the file in permanent storage",
    )
    tool_id = serializers.UUIDField(
        required=True,
        help_text="Tool ID to construct the file path",
    )
