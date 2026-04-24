import logging

from notification_v2.enums import NotificationTrigger
from notification_v2.helper import NotificationHelper
from notification_v2.models import Notification
from pipeline_v2.dto import PipelineStatusPayload
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from api_v2.models import APIDeployment

logger = logging.getLogger(__name__)


class APINotification:
    def __init__(self, api: APIDeployment, workflow_execution: WorkflowExecution) -> None:
        self.notifications = Notification.objects.filter(api=api, is_active=True)
        self.api = api
        self.workflow_execution = workflow_execution

    def send(self) -> None:
        # Partition notifications by the run outcome so each row's notify_on
        # preference is honored. STOPPED and any other non-terminal status
        # fire only for ALL — explicit opt-ins to FAILURES/SUCCESS shouldn't.
        status = self.workflow_execution.status
        if status == ExecutionStatus.ERROR.value:
            self.notifications = self.notifications.exclude(
                notify_on=NotificationTrigger.SUCCESS_ONLY.value
            )
        elif status == ExecutionStatus.COMPLETED.value:
            self.notifications = self.notifications.exclude(
                notify_on=NotificationTrigger.FAILURES_ONLY.value
            )
        else:
            self.notifications = self.notifications.filter(
                notify_on=NotificationTrigger.ALL.value
            )

        if not self.notifications.exists():
            logger.info(
                "No notifications to dispatch for api %s (status=%s)",
                self.api,
                status,
            )
            return
        logger.info("Sending api status notification for api %s", self.api)

        payload_dto = PipelineStatusPayload(
            type="API",
            pipeline_id=self.api.id,
            pipeline_name=self.api.api_name,
            status=self.workflow_execution.status,
            execution_id=self.workflow_execution.id,
            error_message=self.workflow_execution.error_message,
        )

        NotificationHelper.send_notification(
            notifications=self.notifications, payload=payload_dto.to_dict()
        )
