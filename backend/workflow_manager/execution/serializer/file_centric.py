from datetime import timedelta
from typing import Optional

from rest_framework import serializers
from utils.common_utils import CommonUtils
from workflow_manager.file_execution.models import (
    WorkflowFileExecution as FileExecution,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus

INIT_STATUS_MSG = "Waiting for a worker to pick up file's execution..."

DEFAULT_STATUS_MSG = (
    "No status message available, please check again after a few minutes."
)


class FileCentricExecutionSerializer(serializers.ModelSerializer):
    status_msg = serializers.SerializerMethodField()

    class Meta:
        model = FileExecution
        exclude = ["file_hash"]

    def get_status_msg(self, obj: FileExecution) -> Optional[dict[str, any]]:
        if obj.status in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
            return INIT_STATUS_MSG

        latest_log = (
            obj.execution_logs.exclude(data__level__in=["DEBUG", "WARN"])
            .order_by("-event_time")
            .first()
        )
        return (
            latest_log.data["log"]
            if latest_log and "log" in latest_log.data
            else DEFAULT_STATUS_MSG
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Convert file_size from bytes to human-readable format
        data["file_size"] = CommonUtils.pretty_file_size(instance.file_size)

        # Convert execution_time from seconds to HH:MM:SS format
        data["execution_time"] = str(timedelta(seconds=instance.execution_time)).split(
            "."
        )[0]

        return data
