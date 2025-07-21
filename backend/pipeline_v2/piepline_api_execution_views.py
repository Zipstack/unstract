import logging
from typing import Any

from rest_framework import status, views
from rest_framework.request import Request
from rest_framework.response import Response

from backend.celery_service import app as celery_app
from pipeline_v2.deployment_helper import DeploymentHelper
from pipeline_v2.models import Pipeline

logger = logging.getLogger(__name__)


class PipelineApiExecution(views.APIView):
    def initialize_request(self, request: Request, *args: Any, **kwargs: Any) -> Request:
        """To remove csrf request for public API.

        Args:
            request (Request): _description_

        Returns:
            Request: _description_
        """
        request.csrf_processing_done = True
        return super().initialize_request(request, *args, **kwargs)

    @DeploymentHelper.validate_api_key
    def post(
        self, request: Request, org_name: str, pipeline_id: str, pipeline: Pipeline
    ) -> Response:
        celery_app.send_task(
            "scheduler.tasks.execute_pipeline_task",
            args=[
                "",  # workflow_id
                org_name,  # org_schema
                "",  # execution_action
                "",  # execution_id
                pipeline_id,  # pipepline_id
                True,  # with_logs
                pipeline.pipeline_name,  # name
            ],
        )
        logger.info(f"Triggered {pipeline} by API")
        return Response({"message": f"Triggered {pipeline}"}, status=status.HTTP_200_OK)
