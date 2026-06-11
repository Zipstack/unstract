import logging

from notification_v2.helper import dispatch_notifications, is_failure_run
from notification_v2.models import Notification
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from pipeline_v2.dto import PipelineStatusPayload
from pipeline_v2.models import Pipeline

logger = logging.getLogger(__name__)


class PipelineNotification:
    def __init__(
        self,
        pipeline: Pipeline,
        execution_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.notifications = Notification.objects.filter(
            pipeline=pipeline, is_active=True
        )
        self.pipeline = pipeline
        self.error_message = error_message
        self.execution_id = execution_id

    def _load_execution(self) -> WorkflowExecution | None:
        """Load the WorkflowExecution row for this dispatch, if available.

        Falls back to None when no execution_id was supplied (e.g. legacy
        callers); callers must handle the None case.
        """
        if not self.execution_id:
            return None
        try:
            return WorkflowExecution.objects.get(id=self.execution_id)
        except WorkflowExecution.DoesNotExist:
            logger.warning(
                "WorkflowExecution %s not found for pipeline notification",
                self.execution_id,
            )
            return None

    def send(self) -> None:
        execution = self._load_execution()
        # Source of truth for partial-failure detection is the per-run aggregate
        # written by the worker callback. Pipeline.last_run_status is a coarse
        # collapse (ERROR/STOPPED → FAILURE) that hides per-file errors when
        # at least one file succeeded.
        failed_files = (execution.failed_files or 0) if execution else 0
        execution_status = execution.status if execution else None
        # Shared rule (see notification_v2.helper.is_failure_run), plus a
        # pipeline-only backstop: when the WorkflowExecution can't be loaded
        # (legacy caller / missing execution_id) the per-run aggregate is
        # unavailable, so fall back to the pipeline's collapsed last_run_status.
        is_failure = (
            is_failure_run(execution_status, failed_files)
            or self.pipeline.last_run_status == Pipeline.PipelineStatus.FAILURE
        )
        if not is_failure:
            self.notifications = self.notifications.filter(notify_on_failures=False)

        if not self.notifications.exists():
            logger.info(
                "No notifications to dispatch for pipeline %s (status=%s, failed_files=%s)",
                self.pipeline,
                self.pipeline.last_run_status,
                failed_files,
            )
            return
        successful_files = (execution.successful_files or 0) if execution else 0
        total_files = execution.total_files if execution else None
        logger.info(
            "Sending pipeline status notification for pipeline %s "
            "(status=%s, successful=%s, failed=%s)",
            self.pipeline,
            self.pipeline.last_run_status,
            successful_files,
            failed_files,
        )
        payload_dto = PipelineStatusPayload(
            type=self.pipeline.pipeline_type,
            pipeline_id=str(self.pipeline.id),
            pipeline_name=self.pipeline.pipeline_name,
            status=self.pipeline.last_run_status,
            execution_id=self.execution_id,
            error_message=self.error_message,
            total_files=total_files,
            successful_files=successful_files,
            failed_files=failed_files,
            # Carry the verdict the routing filter used so the rendered outcome
            # can't disagree with it — last_run_status is PipelineStatus vocab
            # (SUCCESS/FAILURE) the renderer's is_failure_run can't classify.
            is_failure=is_failure,
        )
        dispatch_notifications(
            list(self.notifications),
            payload_dto.to_dict(),
            error_context=f"pipeline={self.pipeline.id}",
        )
