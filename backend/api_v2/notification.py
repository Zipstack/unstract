import logging

from notification_v2.helper import dispatch_notifications, is_failure_run
from notification_v2.models import Notification
from pipeline_v2.dto import PipelineStatusPayload
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from api_v2.models import APIDeployment

logger = logging.getLogger(__name__)


class APINotification:
    def __init__(self, api: APIDeployment, workflow_execution: WorkflowExecution) -> None:
        self.notifications = Notification.objects.filter(api=api, is_active=True)
        self.api = api
        self.workflow_execution = workflow_execution

    def send(self) -> None:
        # Shared failure rule (status ∈ {ERROR, STOPPED} OR any file errored) —
        # see notification_v2.helper.is_failure_run.
        failed_files = self.workflow_execution.failed_files or 0
        is_failure = is_failure_run(self.workflow_execution.status, failed_files)
        if not is_failure:
            # Success path: skip rows that opted into failure-only alerts.
            self.notifications = self.notifications.filter(notify_on_failures=False)

        if not self.notifications.exists():
            logger.info(
                "No notifications to dispatch for api %s (status=%s, failed_files=%s)",
                self.api,
                self.workflow_execution.status,
                failed_files,
            )
            return
        logger.info(
            "Sending api status notification for api %s (status=%s, successful=%s, failed=%s)",
            self.api,
            self.workflow_execution.status,
            self.workflow_execution.successful_files or 0,
            failed_files,
        )

        payload_dto = PipelineStatusPayload(
            type="API",
            pipeline_id=self.api.id,
            pipeline_name=self.api.api_name,
            status=self.workflow_execution.status,
            execution_id=self.workflow_execution.id,
            error_message=self.workflow_execution.error_message,
            total_files=self.workflow_execution.total_files,
            successful_files=self.workflow_execution.successful_files,
            failed_files=failed_files,
        )

        dispatch_notifications(
            list(self.notifications),
            payload_dto.to_dict(),
            error_context=f"api={self.api.id}",
        )
