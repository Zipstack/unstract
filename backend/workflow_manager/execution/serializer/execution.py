from typing import Optional

from rest_framework import serializers
from workflow_manager.workflow_v2.models import WorkflowExecution


# TODO: Optimize with select_related / prefetch_related to reduce DB queries
class ExecutionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.SerializerMethodField()
    pipeline_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowExecution
        exclude = ["task_id", "execution_log_id", "execution_type"]

    def get_workflow_name(self, obj: WorkflowExecution) -> Optional[str]:
        """Fetch the workflow name using workflow_id"""
        return obj.workflow_name

    def get_pipeline_name(self, obj: WorkflowExecution) -> Optional[str]:
        """Fetch the pipeline or API deployment name"""
        return obj.pipeline_name
