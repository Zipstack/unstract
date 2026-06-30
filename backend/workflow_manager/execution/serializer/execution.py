import logging

from rest_framework import serializers

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution

logger = logging.getLogger(__name__)


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

    def _status_count(self, obj: WorkflowExecution, status_value: str) -> int:
        """COUNT of this execution's file rows in ``status_value``, memoised per
        (execution, status) so the successful/failed fields don't issue
        duplicate COUNTs for the same status within one serialization pass.
        """
        cache = self.__dict__.setdefault("_status_count_cache", {})
        key = (str(obj.id), status_value)
        if key not in cache:
            cache[key] = obj.file_executions.filter(status=status_value).count()
        return cache[key]

    def get_successful_files(self, obj: WorkflowExecution) -> int:
        """Return the count of successfully executed files"""
        return self._status_count(obj, ExecutionStatus.COMPLETED.value)

    def get_failed_files(self, obj: WorkflowExecution) -> int:
        """Return the count of failed files.

        For a terminal *failure* run (ERROR/STOPPED), files that never reached a
        terminal row — orchestration aborted before creating them, or they were
        left PENDING/EXECUTING — are failures, not "in progress". The UI derives
        in-progress as ``total - successful - failed`` (frontend
        ``DetailedLogs.jsx``), so without this a finished failure run shows
        phantom in-progress files. A no-op whenever every file already has a
        terminal COMPLETED/ERROR row.

        Never under-reports below the real ERROR-row count: if the terminal rows
        already exceed ``total_files`` (counter drift / an impossible count) the
        derived value would be too low, so fall back to the ERROR rows and log
        the drift instead of silently clamping it away.
        """
        error_rows = self._status_count(obj, ExecutionStatus.ERROR.value)
        # is_failure swallows ValueError -> False for an unrecognised status, so a
        # malformed/legacy status safely takes the plain row-count path (no raise,
        # so it can't 500 the executions list — but also no reconcile for it).
        if not ExecutionStatus.is_failure(obj.status):
            return error_rows
        successful = self._status_count(obj, ExecutionStatus.COMPLETED.value)
        total = obj.total_files or 0
        if successful + error_rows > total:
            logger.warning(
                "Execution %s terminal file counts exceed total_files "
                "(status=%s total=%s successful=%s error_rows=%s); reporting "
                "failed=%s",
                obj.id,
                obj.status,
                total,
                successful,
                error_rows,
                error_rows,
            )
            return error_rows
        return total - successful

    def get_aggregated_total_pages_processed(self, obj: WorkflowExecution) -> int | None:
        """Return the total pages processed across all file executions."""
        return obj.aggregated_total_pages_processed
