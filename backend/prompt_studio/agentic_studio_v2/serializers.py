"""DRF Serializers for Agentic Studio V2 models."""

from rest_framework import serializers

from adapter_processor_v2.models import AdapterInstance
from utils.user_context import UserContext

from .models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticExtractionNote,
    AgenticExtractedData,
    AgenticLog,
    AgenticProject,
    AgenticPromptVersion,
    AgenticSchema,
    AgenticSetting,
    AgenticSummary,
    AgenticVerifiedData,
)


class AgenticProjectSerializer(serializers.ModelSerializer):
    """Serializer for AgenticProject model."""

    # Frontend expects these field names with _connector_id suffix
    # Note: queryset is set dynamically in __init__ to filter by organization
    llm_connector_id = serializers.PrimaryKeyRelatedField(
        source="extractor_llm",
        queryset=AdapterInstance.objects.none(),  # Will be set in __init__
        required=False,
        allow_null=True,
    )
    agent_llm_connector_id = serializers.PrimaryKeyRelatedField(
        source="agent_llm",
        queryset=AdapterInstance.objects.none(),  # Will be set in __init__
        required=False,
        allow_null=True,
    )
    lightweight_llm_connector_id = serializers.PrimaryKeyRelatedField(
        source="lightweight_llm",
        queryset=AdapterInstance.objects.none(),  # Will be set in __init__
        required=False,
        allow_null=True,
    )
    llmwhisperer_connector_id = serializers.PrimaryKeyRelatedField(
        source="llmwhisperer",
        queryset=AdapterInstance.objects.none(),  # Will be set in __init__
        required=False,
        allow_null=True,
    )

    # Human-readable names for display
    extractor_llm_name = serializers.CharField(
        source="extractor_llm.adapter_name", read_only=True, allow_null=True
    )
    agent_llm_name = serializers.CharField(
        source="agent_llm.adapter_name", read_only=True, allow_null=True
    )
    llmwhisperer_name = serializers.CharField(
        source="llmwhisperer.adapter_name", read_only=True, allow_null=True
    )
    lightweight_llm_name = serializers.CharField(
        source="lightweight_llm.adapter_name", read_only=True, allow_null=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, allow_null=True
    )
    document_count = serializers.SerializerMethodField()
    active_prompt_version = serializers.SerializerMethodField()

    class Meta:
        model = AgenticProject
        fields = [
            "id",
            "name",
            "description",
            # Frontend-compatible field names
            "llm_connector_id",
            "agent_llm_connector_id",
            "lightweight_llm_connector_id",
            "llmwhisperer_connector_id",
            # Human-readable names
            "extractor_llm_name",
            "agent_llm_name",
            "llmwhisperer_name",
            "lightweight_llm_name",
            "canary_fields",
            "wizard_completed",
            "created_by",
            "created_by_username",
            "modified_by",
            "created_at",
            "modified_at",
            "document_count",
            "active_prompt_version",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

    def __init__(self, *args, **kwargs):
        """Initialize serializer and set adapter querysets based on user's organization."""
        super().__init__(*args, **kwargs)

        # Get organization from context
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            organization = UserContext.get_organization()
            if organization:
                # Filter adapters by organization (AdapterInstance has organization field from DefaultOrganizationMixin)
                adapter_queryset = AdapterInstance.objects.filter(
                    organization=organization
                )

                # Update querysets for all adapter fields
                self.fields['llm_connector_id'].queryset = adapter_queryset
                self.fields['agent_llm_connector_id'].queryset = adapter_queryset
                self.fields['lightweight_llm_connector_id'].queryset = adapter_queryset
                self.fields['llmwhisperer_connector_id'].queryset = adapter_queryset

    def create(self, validated_data):
        """Create AgenticProject."""
        request = self.context.get("request")
        user = request.user if request else None

        # Add user info to validated_data
        validated_data["created_by"] = user
        validated_data["modified_by"] = user

        # Set organization from UserContext if not already set
        if "organization" not in validated_data:
            organization = UserContext.get_organization()
            if organization:
                validated_data["organization"] = organization

        return super().create(validated_data)

    def get_document_count(self, obj):
        """Get total number of documents in project."""
        return obj.documents.count()

    def get_active_prompt_version(self, obj):
        """Get the currently active prompt version."""
        active_prompt = obj.prompt_versions.filter(is_active=True).first()
        if active_prompt:
            return {
                "id": active_prompt.id,
                "version": active_prompt.version,
                "accuracy": active_prompt.accuracy,
            }
        return None


class AgenticDocumentSerializer(serializers.ModelSerializer):
    """Serializer for AgenticDocument model."""

    processing_status = serializers.SerializerMethodField()
    has_verified_data = serializers.SerializerMethodField()
    has_summary = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = AgenticDocument
        fields = [
            "id",
            "project",
            "original_filename",
            "stored_path",
            "size_bytes",
            "pages",
            "uploaded_at",
            "raw_text",
            "highlight_metadata",
            "processing_job_id",
            "processing_error",
            "created_at",
            "modified_at",
            "processing_status",
            "has_verified_data",
            "has_summary",
            "file_url",
        ]
        read_only_fields = [
            "id",
            "uploaded_at",
            "created_at",
            "modified_at",
            "processing_job_id",
        ]

    def get_processing_status(self, obj):
        """Get document processing status."""
        if obj.processing_error:
            return "failed"
        elif obj.raw_text:
            return "completed"
        elif obj.processing_job_id:
            return "processing"
        else:
            return "pending"

    def get_has_verified_data(self, obj):
        """Check if document has verified data."""
        return obj.verified_data.exists()

    def get_has_summary(self, obj):
        """Check if document has been summarized."""
        return obj.summaries.exists()

    def get_file_url(self, obj):
        """Get the URL to access the document file."""
        request = self.context.get('request')
        if request:
            # Generate URL dynamically based on the current request path
            # Extract the base path from request (e.g., /api/v1/unstract/{orgId}/agentic/)
            path = request.path
            # Find the agentic base path
            if '/agentic/' in path:
                base_path = path.split('/agentic/')[0] + '/agentic'
                return f"{base_path}/documents/{obj.id}/file/"
            # Fallback
            return f"/api/v1/unstract/agentic/documents/{obj.id}/file/"
        return None


class AgenticSchemaSerializer(serializers.ModelSerializer):
    """Serializer for AgenticSchema model."""

    json_schema_parsed = serializers.SerializerMethodField()

    class Meta:
        model = AgenticSchema
        fields = [
            "id",
            "project",
            "json_schema",
            "json_schema_parsed",
            "version",
            "is_active",
            "created_by_agent",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

    def get_json_schema_parsed(self, obj):
        """Parse JSON schema string to dict."""
        import json

        try:
            return json.loads(obj.json_schema)
        except json.JSONDecodeError:
            return None


class AgenticSummarySerializer(serializers.ModelSerializer):
    """Serializer for AgenticSummary model."""

    document_name = serializers.CharField(
        source="document.original_filename", read_only=True
    )

    class Meta:
        model = AgenticSummary
        fields = [
            "id",
            "project",
            "document",
            "document_name",
            "summary_text",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class AgenticVerifiedDataSerializer(serializers.ModelSerializer):
    """Serializer for AgenticVerifiedData model."""

    document_name = serializers.CharField(
        source="document.original_filename", read_only=True
    )
    verified_by_username = serializers.CharField(
        source="verified_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticVerifiedData
        fields = [
            "id",
            "project",
            "document",
            "document_name",
            "data",
            "verified_by",
            "verified_by_username",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class AgenticExtractedDataSerializer(serializers.ModelSerializer):
    """Serializer for AgenticExtractedData model."""

    document_name = serializers.CharField(
        source="document.original_filename", read_only=True
    )
    prompt_version_number = serializers.IntegerField(
        source="prompt_version.version", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticExtractedData
        fields = [
            "id",
            "project",
            "document",
            "document_name",
            "prompt_version",
            "prompt_version_number",
            "data",
            "extraction_job_id",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at", "extraction_job_id"]


class AgenticComparisonResultSerializer(serializers.ModelSerializer):
    """Serializer for AgenticComparisonResult model."""

    document_name = serializers.CharField(
        source="document.original_filename", read_only=True
    )
    prompt_version_number = serializers.IntegerField(
        source="prompt_version.version", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticComparisonResult
        fields = [
            "id",
            "project",
            "prompt_version",
            "prompt_version_number",
            "document",
            "document_name",
            "field_path",
            "match",
            "normalized_extracted",
            "normalized_verified",
            "error_type",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class AgenticExtractionNoteSerializer(serializers.ModelSerializer):
    """Serializer for AgenticExtractionNote model."""

    document_name = serializers.CharField(
        source="document.original_filename", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticExtractionNote
        fields = [
            "id",
            "project",
            "document",
            "document_name",
            "field_path",
            "note_text",
            "created_by",
            "created_by_username",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class AgenticPromptVersionSerializer(serializers.ModelSerializer):
    """Serializer for AgenticPromptVersion model."""

    accuracy_percentage = serializers.SerializerMethodField()
    parent_version_number = serializers.IntegerField(
        source="parent_version.version", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticPromptVersion
        fields = [
            "id",
            "project",
            "version",
            "short_desc",
            "long_desc",
            "prompt_text",
            "accuracy",
            "accuracy_percentage",
            "is_active",
            "created_by_agent",
            "parent_version",
            "parent_version_number",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

    def get_accuracy_percentage(self, obj):
        """Convert accuracy to percentage."""
        return round(obj.accuracy * 100, 2) if obj.accuracy else 0.0


class AgenticSettingSerializer(serializers.ModelSerializer):
    """Serializer for AgenticSetting model."""

    class Meta:
        model = AgenticSetting
        fields = [
            "id",
            "key",
            "value",
            "description",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class AgenticLogSerializer(serializers.ModelSerializer):
    """Serializer for AgenticLog model."""

    project_name = serializers.CharField(
        source="project.name", read_only=True, allow_null=True
    )

    class Meta:
        model = AgenticLog
        fields = [
            "id",
            "project",
            "project_name",
            "level",
            "message",
            "metadata",
            "timestamp",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "timestamp", "created_at", "modified_at"]

    def validate_level(self, value):
        """Ensure level is a string, not an Enum object."""
        # If it's an Enum, extract the value
        if hasattr(value, 'value'):
            return value.value
        # If it's already a string, return as-is
        return value


# Lightweight serializers for nested representations
class AgenticDocumentLightSerializer(serializers.ModelSerializer):
    """Lightweight serializer for document references."""

    class Meta:
        model = AgenticDocument
        fields = ["id", "original_filename", "uploaded_at"]


class AgenticPromptVersionLightSerializer(serializers.ModelSerializer):
    """Lightweight serializer for prompt version references."""

    class Meta:
        model = AgenticPromptVersion
        fields = ["id", "version", "accuracy", "is_active"]
