"""Django REST Framework serializers for Look-Up API.

This module provides serializers for all Look-Up models
to support RESTful API operations.
"""

import logging
from typing import Any

from adapter_processor_v2.adapter_processor import AdapterProcessor
from rest_framework import serializers

from backend.serializers import AuditSerializer

from .constants import LookupProfileManagerKeys
from .models import (
    LookupDataSource,
    LookupExecutionAudit,
    LookupProfileManager,
    LookupProject,
    LookupPromptTemplate,
    PromptStudioLookupLink,
)

logger = logging.getLogger(__name__)


class LookupPromptTemplateSerializer(serializers.ModelSerializer):
    """Serializer for LookupPromptTemplate model."""

    class Meta:
        model = LookupPromptTemplate
        fields = [
            "id",
            "project",
            "name",
            "template_text",
            "llm_config",
            "is_active",
            "created_by",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "modified_at"]

    def validate_template_text(self, value: str) -> str:
        """Validate that template text contains required placeholders."""
        if "{{reference_data}}" not in value:
            raise serializers.ValidationError(
                "Template must contain {{reference_data}} placeholder"
            )
        return value

    def validate_llm_config(self, value: dict[str, Any]) -> dict[str, Any]:
        """Validate LLM configuration structure."""
        # Accept either new format (adapter_id) or legacy format (provider + model)
        has_adapter_id = "adapter_id" in value
        has_legacy = "provider" in value and "model" in value

        if not has_adapter_id and not has_legacy:
            raise serializers.ValidationError(
                "llm_config must contain either 'adapter_id' (recommended) "
                "or both 'provider' and 'model' fields"
            )
        return value


class LookupDataSourceSerializer(serializers.ModelSerializer):
    """Serializer for LookupDataSource model."""

    extraction_status_display = serializers.CharField(
        source="get_extraction_status_display", read_only=True
    )

    class Meta:
        model = LookupDataSource
        fields = [
            "id",
            "project",
            "file_name",
            "file_path",
            "file_size",
            "file_type",
            "extracted_content_path",
            "extraction_status",
            "extraction_status_display",
            "extraction_error",
            "version_number",
            "is_latest",
            "uploaded_by",
            "created_at",
            "modified_at",
        ]
        read_only_fields = [
            "id",
            "version_number",
            "is_latest",
            "uploaded_by",
            "created_at",
            "modified_at",
            "extraction_status_display",
        ]


class LookupProjectSerializer(serializers.ModelSerializer):
    """Serializer for LookupProject model."""

    template = LookupPromptTemplateSerializer(read_only=True)
    template_id = serializers.PrimaryKeyRelatedField(
        queryset=LookupPromptTemplate.objects.all(),
        source="template",
        write_only=True,
        allow_null=True,
        required=False,
    )
    data_source_count = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = LookupProject
        fields = [
            "id",
            "name",
            "description",
            "reference_data_type",
            "template",
            "template_id",
            "is_active",
            "data_source_count",
            "latest_version",
            "metadata",
            "created_by",
            "created_at",
            "modified_at",
        ]
        read_only_fields = [
            "id",
            "data_source_count",
            "latest_version",
            "created_by",
            "created_at",
            "modified_at",
        ]

    def get_data_source_count(self, obj) -> int:
        """Get count of data sources for this project."""
        return obj.data_sources.filter(is_latest=True).count()

    def get_latest_version(self, obj) -> int:
        """Get latest version number of data sources."""
        latest = obj.data_sources.filter(is_latest=True).first()
        return latest.version_number if latest else 0


class PromptStudioLookupLinkSerializer(serializers.ModelSerializer):
    """Serializer for linking Look-Ups to Prompt Studio projects."""

    lookup_project_name = serializers.CharField(
        source="lookup_project.name", read_only=True
    )

    class Meta:
        model = PromptStudioLookupLink
        fields = [
            "id",
            "prompt_studio_project_id",
            "lookup_project",
            "lookup_project_name",
            "created_at",
        ]
        read_only_fields = ["id", "lookup_project_name", "created_at"]

    def validate(self, attrs):
        """Validate that the link doesn't already exist."""
        ps_project_id = attrs.get("prompt_studio_project_id")
        lookup_project = attrs.get("lookup_project")

        # Check if this combination already exists
        existing = PromptStudioLookupLink.objects.filter(
            prompt_studio_project_id=ps_project_id, lookup_project=lookup_project
        ).exists()

        if existing and not self.instance:  # Only check for creation, not update
            raise serializers.ValidationError(
                "This Look-Up is already linked to the Prompt Studio project"
            )

        return attrs


class LookupExecutionAuditSerializer(serializers.ModelSerializer):
    """Serializer for execution audit records."""

    lookup_project_name = serializers.CharField(
        source="lookup_project.name", read_only=True
    )

    class Meta:
        model = LookupExecutionAudit
        fields = [
            "id",
            "lookup_project",
            "lookup_project_name",
            "prompt_studio_project_id",
            "execution_id",
            "input_data",
            "enriched_output",
            "reference_data_version",
            "llm_provider",
            "llm_model",
            "llm_prompt",
            "llm_response",
            "llm_response_cached",
            "execution_time_ms",
            "llm_call_time_ms",
            "status",
            "error_message",
            "confidence_score",
            "executed_at",
        ]
        read_only_fields = fields  # All fields are read-only for audit records


class LookupExecutionRequestSerializer(serializers.Serializer):
    """Serializer for Look-Up execution requests."""

    input_data = serializers.JSONField(help_text="Input data for variable resolution")
    lookup_project_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="List of Look-Up project IDs to execute",
    )
    use_cache = serializers.BooleanField(
        default=True, help_text="Whether to use cached LLM responses"
    )
    timeout_seconds = serializers.IntegerField(
        default=30,
        min_value=1,
        max_value=300,
        help_text="Timeout for execution in seconds",
    )


class LookupExecutionResponseSerializer(serializers.Serializer):
    """Serializer for Look-Up execution responses."""

    lookup_enrichment = serializers.JSONField(
        help_text="Merged enrichment data from all Look-Ups"
    )
    _lookup_metadata = serializers.JSONField(
        help_text="Execution metadata including timing and status"
    )


class ReferenceDataUploadSerializer(serializers.Serializer):
    """Serializer for reference data upload requests."""

    file = serializers.FileField(help_text="Reference data file to upload")
    extract_text = serializers.BooleanField(
        default=True, help_text="Whether to extract text from the file"
    )
    metadata = serializers.JSONField(
        required=False, default=dict, help_text="Additional metadata for the data source"
    )


class BulkLinkSerializer(serializers.Serializer):
    """Serializer for bulk linking operations."""

    prompt_studio_project_id = serializers.UUIDField(help_text="Prompt Studio project ID")
    lookup_project_ids = serializers.ListField(
        child=serializers.UUIDField(), help_text="List of Look-Up project IDs to link"
    )
    unlink = serializers.BooleanField(
        default=False, help_text="If true, unlink instead of link"
    )


class TemplateValidationSerializer(serializers.Serializer):
    """Serializer for template validation requests."""

    template_text = serializers.CharField(help_text="Template text to validate")
    sample_data = serializers.JSONField(
        required=False, help_text="Sample input data for testing variable resolution"
    )
    sample_reference = serializers.CharField(
        required=False, help_text="Sample reference data for testing"
    )


class LookupProfileManagerSerializer(AuditSerializer):
    """Serializer for LookupProfileManager model.

    Follows the same pattern as Prompt Studio's ProfileManagerSerializer.
    Expands adapter UUIDs to full adapter details in the response.
    """

    class Meta:
        model = LookupProfileManager
        fields = "__all__"

    def to_representation(self, instance):
        """Expand adapter UUIDs to full adapter details.

        This converts the FK references to AdapterInstance objects
        into full adapter details including adapter_name, adapter_type, etc.
        """
        rep: dict[str, str] = super().to_representation(instance)

        # Expand each adapter FK to full details
        llm = rep.get(LookupProfileManagerKeys.LLM)
        embedding = rep.get(LookupProfileManagerKeys.EMBEDDING_MODEL)
        vector_db = rep.get(LookupProfileManagerKeys.VECTOR_STORE)
        x2text = rep.get(LookupProfileManagerKeys.X2TEXT)

        if llm:
            rep[LookupProfileManagerKeys.LLM] = (
                AdapterProcessor.get_adapter_instance_by_id(llm)
            )
        if embedding:
            rep[LookupProfileManagerKeys.EMBEDDING_MODEL] = (
                AdapterProcessor.get_adapter_instance_by_id(embedding)
            )
        if vector_db:
            rep[LookupProfileManagerKeys.VECTOR_STORE] = (
                AdapterProcessor.get_adapter_instance_by_id(vector_db)
            )
        if x2text:
            rep[LookupProfileManagerKeys.X2TEXT] = (
                AdapterProcessor.get_adapter_instance_by_id(x2text)
            )

        return rep
