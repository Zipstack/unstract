from typing import Optional

from rest_framework import serializers
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution


# TODO: Optimize with select_related / prefetch_related to reduce DB queries
class ExecutionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.SerializerMethodField()
    pipeline_name = serializers.SerializerMethodField()
    successful_files = serializers.SerializerMethodField()
    failed_files = serializers.SerializerMethodField()
    execution_time = serializers.ReadOnlyField(source="pretty_execution_time")

    class Meta:
        model = WorkflowExecution
        exclude = ["task_id", "execution_log_id", "execution_type"]

    def get_workflow_name(self, obj: WorkflowExecution) -> Optional[str]:
        """Fetch the workflow name using workflow_id"""
        return obj.workflow_name

    def get_pipeline_name(self, obj: WorkflowExecution) -> Optional[str]:
        """Fetch the pipeline or API deployment name"""
        return obj.pipeline_name

    def get_successful_files(self, obj: WorkflowExecution) -> int:
        """Return the count of successfully executed files"""
        return obj.file_executions.filter(status=ExecutionStatus.COMPLETED).count()

    def get_failed_files(self, obj: WorkflowExecution) -> int:
        """Return the count of failed executed files"""
        return obj.file_executions.filter(status=ExecutionStatus.ERROR).count()
