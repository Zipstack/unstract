import logging

from django.utils import timezone

from pipeline_v2.exceptions import InactivePipelineError
from pipeline_v2.models import Pipeline
from pipeline_v2.notification import PipelineNotification

logger = logging.getLogger(__name__)


class PipelineProcessor:
    @staticmethod
    def initialize_pipeline_sync(pipeline_id: str) -> Pipeline:
        """Fetches and initializes the sync for a pipeline.

        Args:
            pipeline_id (str): UUID of the pipeline to sync
        """
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(pipeline_id)
        pipeline.run_count = pipeline.run_count + 1
        return PipelineProcessor._update_pipeline_status(
            pipeline=pipeline,
            status=Pipeline.PipelineStatus.RESTARTING,
            is_end=False,
        )

    @staticmethod
    def fetch_pipeline(pipeline_id: str, check_active: bool = True) -> Pipeline:
        """Retrieves and checks for an active pipeline.

        Args:
            pipeline_id (str): UUID of the pipeline
            check_active (bool): Whether to check if the pipeline is active

        Raises:
            InactivePipelineError: If an active pipeline is not found
        """
        pipeline: Pipeline = Pipeline.objects.get(pk=pipeline_id)
        if check_active and not pipeline.is_active():
            logger.error(f"Inactive pipeline fetched: {pipeline_id}")
            raise InactivePipelineError(pipeline_name=pipeline.pipeline_name)
        return pipeline

    @classmethod
    def get_active_pipeline(cls, pipeline_id: str) -> Pipeline | None:
        """Retrieves a list of active pipelines."""
        try:
            return cls.fetch_pipeline(pipeline_id, check_active=True)
        except Pipeline.DoesNotExist:
            return None

    @staticmethod
    def _update_pipeline_status(
        pipeline: Pipeline,
        status: tuple[str, str],
        is_end: bool,
        is_active: bool | None = None,
    ) -> Pipeline:
        """Updates pipeline status during execution.

        Raises:
            PipelineSaveError: Exception while saving a pipeline

        Returns:
            Pipeline: Updated pipeline
        """
        if is_end:
            pipeline.last_run_time = timezone.now()
        if status:
            pipeline.last_run_status = status
        if is_active is not None:
            pipeline.active = is_active

        pipeline.save()
        return pipeline

    @staticmethod
    def _send_notification(
        pipeline: Pipeline,
        execution_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Sends a notification for the pipeline.

        Args:
            pipeline (Pipeline): Pipeline to send notification for

        Returns:
            None
        """
        pipeline_notification = PipelineNotification(
            pipeline=pipeline, execution_id=execution_id, error_message=error_message
        )
        pipeline_notification.send()

    @staticmethod
    def update_pipeline(
        pipeline_guid: str | None,
        status: tuple[str, str],
        is_active: bool | None = None,
        execution_id: str | None = None,
        error_message: str | None = None,
        is_end: bool = False,
    ) -> None:
        if not pipeline_guid:
            return
        # Skip check if we are enabling an inactive pipeline
        check_active = not is_active
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(
            pipeline_id=pipeline_guid, check_active=check_active
        )
        pipeline = PipelineProcessor._update_pipeline_status(
            pipeline=pipeline, is_end=is_end, status=status, is_active=is_active
        )
        PipelineProcessor._send_notification(
            pipeline=pipeline, execution_id=execution_id, error_message=error_message
        )
        logger.info(f"Updated pipeline {pipeline_guid} status: {status}")
