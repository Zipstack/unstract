import logging
import uuid
from typing import Any

from django.db import connection
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework.serializers import ValidationError
from scheduler.constants import SchedulerConstants as SC
from scheduler.exceptions import JobDeletionError, JobSchedulingError
from scheduler.serializer import AddJobSerializer
from scheduler.tasks import (
    create_periodic_task,
    delete_periodic_task,
    disable_task,
    enable_task,
)
from workflow_manager.workflow.constants import WorkflowExecutionKey, WorkflowKey
from workflow_manager.workflow.serializers import ExecuteWorkflowSerializer

logger = logging.getLogger(__name__)


class SchedulerHelper:

    @staticmethod
    def _schedule_task_job(pipeline_id: str, job_data: Any) -> None:
        if "cron_string" not in job_data:
            raise ValidationError("cron_string is required in job_data")
        if "id" not in job_data:
            raise ValidationError("id is required in job_data")
        if "job_kwargs" in job_data and not isinstance(job_data["job_kwargs"], dict):
            raise ValidationError("job_kwargs is required to be a dict")

        cron_string = job_data.get("cron_string")
        name = job_data.get("name")
        job_kwargs = job_data.get("job_kwargs", {})
        task_data = job_kwargs.get("data", {})

        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(pipeline_id)
        task_data[WorkflowKey.WF_ID] = pipeline.workflow.id
        execution_id = str(uuid.uuid4())
        task_data[WorkflowExecutionKey.EXECUTION_ID] = execution_id
        serializer = ExecuteWorkflowSerializer(data=task_data)
        serializer.is_valid(raise_exception=True)
        workflow_id = serializer.get_workflow_id(serializer.validated_data)
        # TODO: Remove unused argument in execute_pipeline_task
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
                # Added to remain backward compatible - remove after data migration
                # which removes unused args in execute_pipeline_task
                bool(False),
                str(name),
            ],
        )

    @staticmethod
    def add_job(pipeline_id: str, cron_string: str = SC.DEFAULT_CRON_STRING) -> None:
        logger.info(f"Scheduling job for {pipeline_id} with {cron_string}")
        name = f"Pipeline job-{pipeline_id}"
        job_serialize_data = {
            SC.ID: pipeline_id,
            SC.CRON_STRING: cron_string,
            SC.NAME: name,
        }
        job_serializer = AddJobSerializer(data=job_serialize_data)
        job_serializer.is_valid(raise_exception=True)
        try:
            SchedulerHelper._schedule_task_job(
                pipeline_id, job_serializer.validated_data
            )
        except Exception as e:
            logger.error(f"Exception while adding job: {e}")
            raise JobSchedulingError from e

    @staticmethod
    def remove_job(pipeline_id: str) -> None:
        logger.info(f"Removing job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - removing job")
            delete_periodic_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while removing job: {e}")
            raise JobDeletionError from e

    @staticmethod
    def pause_job(pipeline_id: str) -> None:
        logger.info(f"Pausing job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - pausing job")
            disable_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while pausing job: {e}")
            raise JobSchedulingError from e

    @staticmethod
    def resume_job(pipeline_id: str) -> None:
        logger.info(f"Resuming job for {pipeline_id}")
        try:
            logger.info("Celery scheduler - resuming job")
            enable_task(pipeline_id)
        except Exception as e:
            logger.error(f"Exception while resuming job: {e}")
            raise JobSchedulingError from e
