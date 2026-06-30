from rest_framework import serializers

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution


# TODO: Optimize with select_related / prefetch_related to reduce DB queries
class ExecutionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.SerializerMethodField()
    pipeline_name = serializers.SerializerMethodField()
    successful_files = serializers.SerializerMethodField()
    failed_files = serializers.SerializerMethodField()
    aggregated_total_pages_processed = serializers.SerializerMethodField()
    execution_time = serializers.ReadOnlyField(source="pretty_execution_time")

    class Meta:
        model = WorkflowExecution
        exclude = ["task_id", "execution_log_id", "execution_type"]

    def get_workflow_name(self, obj: WorkflowExecution) -> str | None:
        """Fetch the workflow name using workflow_id"""
        return obj.workflow_name

    def get_pipeline_name(self, obj: WorkflowExecution) -> str | None:
        """Fetch the pipeline or API deployment name"""
        return obj.pipeline_name

    def get_successful_files(self, obj: WorkflowExecution) -> int:
        """Return the count of successfully executed files"""
        return obj.file_executions.filter(status=ExecutionStatus.COMPLETED.value).count()

    def get_failed_files(self, obj: WorkflowExecution) -> int:
        """Return the count of failed executed files.

        For a terminal *failure* run (ERROR/STOPPED), every file that did not
        succeed is a failure — including files that never got a file-execution
        row because orchestration aborted before creating them, or were left
        PENDING/EXECUTING by the abort. The UI derives "in progress" as
        ``total - successful - failed``, so without this a finished failure run
        shows phantom in-progress files (e.g. an early barrier-dispatch failure
        with 0 rows reads as "N in progress" instead of "N failed").

        Scoped to ``is_failure`` (ERROR/STOPPED) so COMPLETED runs and live
        runs (PENDING/EXECUTING) keep the exact row-count behaviour — a no-op
        whenever the rows already account for every file, so the success path
        and real-time progress are untouched on every transport.
        """
        if ExecutionStatus.is_failure(obj.status):
            total = obj.total_files or 0
            return max(0, total - self.get_successful_files(obj))
        return obj.file_executions.filter(status=ExecutionStatus.ERROR.value).count()

    def get_aggregated_total_pages_processed(self, obj: WorkflowExecution) -> int | None:
        """Return the total pages processed across all file executions."""
        return obj.aggregated_total_pages_processed
