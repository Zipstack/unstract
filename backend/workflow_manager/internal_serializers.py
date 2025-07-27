"""Workflow Manager Internal API Serializers
Handles serialization for workflow execution related internal endpoints.
"""

from pipeline_v2.models import Pipeline
from rest_framework import serializers

# Import shared dataclasses for type safety and consistency
from unstract.core.data_models import (
    FileExecutionStatusUpdateRequest,
    WorkflowFileExecutionData,
)
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    """Serializer for WorkflowExecution model for internal API."""

    workflow_id = serializers.CharField(source="workflow.id", read_only=True)
    workflow_name = serializers.CharField(source="workflow.workflow_name", read_only=True)
    pipeline_id = serializers.SerializerMethodField()

    def get_pipeline_id(self, obj):
        """ROOT CAUSE FIX: Return None for pipeline_id if the referenced pipeline doesn't exist.
        This prevents callback workers from attempting to update deleted pipelines.
        PERFORMANCE: Cache pipeline existence to avoid repeated DB queries.
        """
        if not obj.pipeline_id:
            return None

        # Use instance-level cache to avoid repeated DB queries within same request
        cache_key = f"_pipeline_exists_{obj.pipeline_id}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        try:
            # Check if the pipeline actually exists
            Pipeline.objects.get(id=obj.pipeline_id)
            result = str(obj.pipeline_id)
            setattr(self, cache_key, result)
            return result
        except Pipeline.DoesNotExist:
            # Pipeline was deleted - return None to prevent stale reference usage
            setattr(self, cache_key, None)
            return None

    class Meta:
        model = WorkflowExecution
        fields = [
            "id",
            "workflow_id",
            "workflow_name",
            "pipeline_id",
            "task_id",
            "execution_mode",
            "execution_method",
            "execution_type",
            "execution_log_id",
            "status",
            "result_acknowledged",
            "total_files",
            "error_message",
            "attempts",
            "execution_time",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class WorkflowFileExecutionSerializer(serializers.ModelSerializer):
    """Serializer for WorkflowFileExecution model for internal API.
    Enhanced with shared dataclass integration for type safety.
    """

    workflow_execution_id = serializers.CharField(
        source="workflow_execution.id", read_only=True
    )

    class Meta:
        model = WorkflowFileExecution
        fields = [
            "id",
            "workflow_execution_id",
            "file_name",
            "file_path",
            "file_size",
            "file_hash",
            "provider_file_uuid",
            "mime_type",
            "fs_metadata",
            "status",
            "execution_error",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

    def to_dataclass(self, instance=None) -> WorkflowFileExecutionData:
        """Convert serialized data to shared dataclass."""
        if instance is None:
            instance = self.instance
        return WorkflowFileExecutionData.from_dict(self.to_representation(instance))

    @classmethod
    def from_dataclass(cls, data: WorkflowFileExecutionData) -> dict:
        """Convert shared dataclass to serializer-compatible dict."""
        return data.to_dict()


class FileExecutionStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating file execution status.
    Enhanced with shared dataclass integration for type safety.
    """

    status = serializers.ChoiceField(choices=ExecutionStatus.choices)
    error_message = serializers.CharField(required=False, allow_blank=True)
    result = serializers.CharField(required=False, allow_blank=True)
    execution_time = serializers.FloatField(required=False, min_value=0)

    def to_dataclass(self) -> FileExecutionStatusUpdateRequest:
        """Convert validated data to shared dataclass."""
        return FileExecutionStatusUpdateRequest(
            status=self.validated_data["status"],
            error_message=self.validated_data.get("error_message"),
            result=self.validated_data.get("result"),
        )

    @classmethod
    def from_dataclass(cls, data: FileExecutionStatusUpdateRequest):
        """Create serializer from shared dataclass."""
        return cls(data=data.to_dict())


class WorkflowExecutionStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating workflow execution status."""

    status = serializers.ChoiceField(choices=ExecutionStatus.choices)
    error_message = serializers.CharField(required=False, allow_blank=True)
    total_files = serializers.IntegerField(
        required=False, min_value=0
    )  # Allow 0 but backend will only update if > 0
    attempts = serializers.IntegerField(required=False, min_value=0)
    execution_time = serializers.FloatField(required=False, min_value=0)


class OrganizationContextSerializer(serializers.Serializer):
    """Serializer for organization context information."""

    organization_id = serializers.CharField(allow_null=True, required=False)
    organization_name = serializers.CharField(required=False, allow_blank=True)
    settings = serializers.DictField(required=False)


class WorkflowExecutionContextSerializer(serializers.Serializer):
    """Serializer for complete workflow execution context."""

    execution = WorkflowExecutionSerializer()
    workflow_definition = serializers.DictField()
    source_config = serializers.DictField()
    destination_config = serializers.DictField(required=False)
    organization_context = OrganizationContextSerializer()
    file_executions = serializers.ListField(required=False)


class FileBatchCreateSerializer(serializers.Serializer):
    """Serializer for creating file execution batches."""

    workflow_execution_id = serializers.UUIDField()
    files = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    is_api = serializers.BooleanField(default=False)


class FileBatchResponseSerializer(serializers.Serializer):
    """Serializer for file batch creation response."""

    batch_id = serializers.CharField()
    workflow_execution_id = serializers.CharField()
    total_files = serializers.IntegerField()
    created_file_executions = serializers.ListField()
    skipped_files = serializers.ListField(required=False)
