import logging
import uuid
from typing import Any

from django.db import connection
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework.response import Response
from scheduler.tasks import create_periodic_task
from workflow_manager.workflow.constants import WorkflowExecutionKey, WorkflowKey
from workflow_manager.workflow.exceptions import WorkflowExecutionBadRequestException
from workflow_manager.workflow.serializers import ExecuteWorkflowSerializer
from workflow_manager.workflow.views import WorkflowViewSet

logger = logging.getLogger(__name__)


def schedule_task_job(pipeline_id: str, job_data: Any) -> Response:
    try:
        # Validating request
        if "cron_string" not in job_data:
            return Response({"error": "cron_string is required"}, status=400)
        if "id" not in job_data:
            return Response({"error": "id is required"}, status=400)
        if "job_kwargs" in job_data and not isinstance(job_data["job_kwargs"], dict):
            return Response(
                {"error": "job_kwargs is required to be a dict"}, status=400
            )

        cron_string = job_data.get("cron_string")
        name = job_data.get("name")
        job_kwargs = job_data.get("job_kwargs", {})
        task_data = job_kwargs.get("data", {})
        params = job_kwargs.get("params", {})
        with_logs = params.get("with_logs", False)

        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(pipeline_id)

        task_data[WorkflowKey.WF_ID] = pipeline.workflow.id
        execution_id = str(uuid.uuid4())
        task_data[WorkflowExecutionKey.EXECUTION_ID] = execution_id
        workflow_viewset = WorkflowViewSet()
        workflow_viewset.serializer_class = ExecuteWorkflowSerializer
        serializer = ExecuteWorkflowSerializer(data=task_data)

        if not serializer.is_valid():
            raise WorkflowExecutionBadRequestException(
                workflow_viewset.get_error_from_serializer(serializer.errors)
            )

        workflow_id = serializer.get_workflow_id(serializer.validated_data)

        execution_action = serializer.get_execution_action(serializer.validated_data)
        org_schema = connection.tenant.schema_name

        create_periodic_task(
            cron_string=cron_string,
            task_name=pipeline.pk,
            task_path="scheduler.tasks.execute_pipeline_task",
            task_args=[
                str(workflow_id),
                org_schema,
                execution_action or "",
                execution_id,
                str(pipeline.pk),
                bool(with_logs),
                str(name),
            ],
        )

        return Response({"message": "Job scheduled successfully"}, status=200)

    except Exception as e:
        logger.error(f"Exception while scheduling job: {e}")
        return Response({"error": str(e)}, status=500)
