import logging

from notification_v2.helper import NotificationHelper
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

    def send(self):
        if not self.notifications.count():
            logger.info(f"No notifications found for api {self.api}")
            return
        logger.info(f"Sending api status notification for api {self.api}")

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
