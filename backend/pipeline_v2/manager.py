import logging
from typing import Any, Optional

from django.conf import settings
from django.urls import reverse
from pipeline_v2.constants import PipelineKey, PipelineURL
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework.request import Request
from rest_framework.response import Response
from utils.request.constants import RequestConstants
from workflow_manager.workflow_v2.constants import WorkflowExecutionKey, WorkflowKey
from workflow_manager.workflow_v2.views import WorkflowViewSet

from backend.constants import RequestHeader

logger = logging.getLogger(__name__)


class PipelineManager:
    """Helps manage the execution and scheduling of pipelines."""

    @staticmethod
    def execute_pipeline(
        request: Request,
        pipeline_id: str,
        execution_id: Optional[str] = None,
    ) -> Response:
        """Used to execute a pipeline.

        Args:
            pipeline_id (str): UUID of the pipeline to execute
            execution_id (Optional[str], optional):
                Uniquely identifies an execution. Defaults to None.
        """
        logger.info(f"Executing pipeline {pipeline_id}, execution: {execution_id}")
        pipeline: Pipeline = PipelineProcessor.initialize_pipeline_sync(pipeline_id)
        # TODO: Use DRF's request and as_view() instead
        request.data[WorkflowKey.WF_ID] = pipeline.workflow.id
        if execution_id is not None:
            request.data[WorkflowExecutionKey.EXECUTION_ID] = execution_id
        wf_viewset = WorkflowViewSet()
        return wf_viewset.execute(request=request, pipeline_guid=str(pipeline.pk))

    @staticmethod
    def get_pipeline_execution_data_for_scheduled_run(
        pipeline_id: str,
    ) -> Optional[dict[str, Any]]:
        """Gets the required data to be passed while executing a pipeline Any
        changes to pipeline execution needs to be propagated here."""
        callback_url = settings.DJANGO_APP_BACKEND_URL + reverse(
            PipelineURL.EXECUTE_NAMESPACE
        )
        job_headers = {RequestHeader.X_API_KEY: settings.INTERNAL_SERVICE_API_KEY}
        job_kwargs = {
            RequestConstants.VERB: "POST",
            RequestConstants.URL: callback_url,
            RequestConstants.HEADERS: job_headers,
            RequestConstants.DATA: {PipelineKey.PIPELINE_ID: pipeline_id},
        }
        return job_kwargs
