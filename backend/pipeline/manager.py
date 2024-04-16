import logging
from typing import Any, Optional

from django.conf import settings
from django.urls import reverse
from pipeline.constants import PipelineKey, PipelineURL
from pipeline.exceptions import PipelineExecuteError
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework.request import Request
from rest_framework.response import Response
from utils.request.constants import RequestConstants
from workflow_manager.workflow.constants import WorkflowExecutionKey, WorkflowKey
from workflow_manager.workflow.views import WorkflowViewSet

from backend.constants import RequestHeader

logger = logging.getLogger(__name__)


class PipelineManager:
    """Helps manage the execution and scheduling of pipelines."""

    @staticmethod
    def execute_pipeline(
        request: Request,
        pipeline_id: str,
        execution_id: Optional[str] = None,
        with_log: Optional[bool] = None,
    ) -> Response:
        """Used to execute a pipeline.

        Args:
            pipeline_id (str): UUID of the pipeline to execute
            execution_id (Optional[str], optional):
                Uniquely identifies an execution. Defaults to None.
            with_log (Optional[bool], optional): Flag to pass logs to FE.
                Defaults to None.
        """
        logger.info(
            f"Executing pipeline {pipeline_id}, execution: {execution_id}, "
            f"with_log = {with_log}"
        )
        try:
            pipeline: Pipeline = PipelineProcessor.initialize_pipeline_sync(pipeline_id)
            # TODO: Use DRF's request and as_view() instead
            request.data[WorkflowKey.WF_ID] = pipeline.workflow.id
            if execution_id is not None:
                request.data[WorkflowExecutionKey.EXECUTION_ID] = execution_id
            wf_viewset = WorkflowViewSet()
            return WorkflowViewSet.execute(
                wf_viewset,
                request=request,
                pipeline_guid=pipeline.pk,
                with_log=with_log,
            )
        except Exception as e:
            logger.error(f"Error executing pipeline: {e}")
            raise PipelineExecuteError()

    @staticmethod
    def get_pipeline_execution_data_for_scheduled_run(
        pipeline_id: str,
    ) -> Optional[dict[str, Any]]:
        """Gets the required data to be passed while executing a pipeline Any
        changes to pipeline execution needs to be propagated here."""
        callback_url = settings.DJANGO_APP_BACKEND_URL + reverse(PipelineURL.EXECUTE)
        job_headers = {RequestHeader.X_API_KEY: settings.INTERNAL_SERVICE_API_KEY}
        job_params = {WorkflowExecutionKey.WITH_LOG: "False"}
        job_kwargs = {
            RequestConstants.VERB: "POST",
            RequestConstants.URL: callback_url,
            RequestConstants.HEADERS: job_headers,
            RequestConstants.PARAMS: job_params,
            RequestConstants.DATA: {PipelineKey.PIPELINE_ID: pipeline_id},
        }
        return job_kwargs
