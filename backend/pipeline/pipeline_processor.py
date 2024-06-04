import logging
from typing import Any, Optional

from django.utils import timezone
from pipeline.exceptions import InactivePipelineError, PipelineSaveError
from pipeline.models import Pipeline

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

        Raises:
            InactivePipelineError: If an active pipeline is not found
        """
        pipeline: Pipeline = Pipeline.objects.get(pk=pipeline_id)
        if check_active and not pipeline.is_active():
            logger.error(f"Inactive pipeline fetched: {pipeline_id}")
            raise InactivePipelineError(pipeline_name=pipeline.pipeline_name)
        return pipeline

    @staticmethod
    def _update_pipeline_status(
        pipeline: Pipeline,
        status: tuple[str, str],
        is_end: bool,
        is_active: Optional[bool] = None,
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

        try:
            pipeline.save()
        except Exception as exc:
            logger.error(f"Error occured while saving pipeline : {exc}")
            raise PipelineSaveError()
        return pipeline

    @staticmethod
    def update_pipeline(
        pipeline_guid: Optional[str],
        status: tuple[str, str],
        is_active: Optional[bool] = None,
    ) -> Any:
        if not pipeline_guid:
            return
        # Skip check if we are enabling an inactive pipeline
        check_active = not is_active
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(
            pipeline_id=pipeline_guid, check_active=check_active
        )
        PipelineProcessor._update_pipeline_status(
            pipeline=pipeline, is_end=True, status=status, is_active=is_active
        )
        logger.info(f"Updated pipeline status: {status}")
