import logging

from notification_v2.helper import NotificationHelper
from notification_v2.models import Notification

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

    def send(self):
        if not self.notifications.count():
            logger.info(f"No notifications found for pipeline {self.pipeline}")
            return
        logger.info(f"Sending pipeline status notification for pipeline {self.pipeline}")
        payload_dto = PipelineStatusPayload(
            type=self.pipeline.pipeline_type,
            pipeline_id=str(self.pipeline.id),
            pipeline_name=self.pipeline.pipeline_name,
            status=self.pipeline.last_run_status,
            execution_id=self.execution_id,
            error_message=self.error_message,
        )

        NotificationHelper.send_notification(
            notifications=self.notifications, payload=payload_dto.to_dict()
        )
