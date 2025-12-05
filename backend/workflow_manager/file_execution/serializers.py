from rest_framework import serializers

from workflow_manager.file_execution.models import (
    WorkflowFileExecution as FileExecution,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus

from .models import WorkflowFileExecution


class WorkflowFileExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowFileExecution
        fields = "__all__"


class FileCentricExecutionSerializer(serializers.ModelSerializer):
    INIT_STATUS_MSG = "Waiting for a worker to pick up file's execution..."

    DEFAULT_STATUS_MSG = (
        "No status message available yet, please check again after a few minutes."
    )

    status_msg = serializers.SerializerMethodField()
    file_size = serializers.ReadOnlyField(source="pretty_file_size")
    execution_time = serializers.ReadOnlyField(source="pretty_execution_time")

    class Meta:
        model = FileExecution
        exclude = ["file_hash"]

    def get_status_msg(self, obj: FileExecution) -> dict[str, any] | None:
        if obj.status in [ExecutionStatus.PENDING.value]:
            return self.INIT_STATUS_MSG
        elif obj.status == ExecutionStatus.ERROR.value:
            return obj.execution_error

        # Use pre-annotated field from viewset queryset to avoid N+1 queries
        if hasattr(obj, "latest_log_data") and obj.latest_log_data:
            return obj.latest_log_data.get("log", self.DEFAULT_STATUS_MSG)
        return self.DEFAULT_STATUS_MSG
