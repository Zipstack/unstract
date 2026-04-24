import logging

from notification_v2.enums import NotificationTrigger
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

    def send(self) -> None:
        # Partition notifications by the run outcome so each row's notify_on
        # preference is honored. PipelineUtils.update_pipeline_status collapses
        # both ERROR and STOPPED execution statuses into PipelineStatus.FAILURE,
        # so FAILURES_ONLY subscribers get alerts for both on the pipeline side.
        status = self.pipeline.last_run_status
        if status == Pipeline.PipelineStatus.FAILURE:
            self.notifications = self.notifications.exclude(
                notify_on=NotificationTrigger.SUCCESS_ONLY.value
            )
        elif status == Pipeline.PipelineStatus.SUCCESS:
            self.notifications = self.notifications.exclude(
                notify_on=NotificationTrigger.FAILURES_ONLY.value
            )
        else:
            self.notifications = self.notifications.filter(
                notify_on=NotificationTrigger.ALL.value
            )

        if not self.notifications.exists():
            logger.info(
                "No notifications to dispatch for pipeline %s (status=%s)",
                self.pipeline,
                status,
            )
            return
        logger.info("Sending pipeline status notification for pipeline %s", self.pipeline)
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
