from typing import Optional

from rest_framework import serializers
from workflow_manager.file_execution.models import (
    WorkflowFileExecution as FileExecution,
)


class FileCentricExecutionSerializer(serializers.ModelSerializer):
    latest_log = serializers.SerializerMethodField()

    class Meta:
        model = FileExecution
        exclude = ["file_hash"]

    def get_latest_log(self, obj: FileExecution) -> Optional[dict[str, any]]:
        latest_log = (
            obj.execution_logs.exclude(data__level__in=["DEBUG", "WARN"])
            .order_by("-event_time")
            .first()
        )
        return (
            latest_log.data["log"] if latest_log and "log" in latest_log.data else None
        )
