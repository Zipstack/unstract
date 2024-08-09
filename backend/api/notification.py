import logging

from api.models import APIDeployment
from notification.helper import NotificationHelper
from notification.models import Notification
from pipeline.dto import PipelineStatusPayload
from workflow_manager.workflow.dto import ExecutionResponse

logger = logging.getLogger(__name__)


class APINotification:
    def __init__(self, api: APIDeployment, result: ExecutionResponse) -> None:
        self.notifications = Notification.objects.filter(api=api, is_active=True)
        self.api = api
        self.result = result

    def send(self):
        if not self.notifications.count():
            logger.info(f"No notifications found for api {self.api}")
            return
        logger.info(f"Sending api status notification for api {self.api}")

        payload_dto = PipelineStatusPayload(
            type="API",
            pipeline_id=self.api.id,
            pipeline_name=self.api.api_name,
            status=self.result.execution_status,
            execution_id=self.result.execution_id,
            error_message=self.result.error,
        )

        NotificationHelper.send_notification(
            notifications=self.notifications, payload=payload_dto.to_dict()
        )
