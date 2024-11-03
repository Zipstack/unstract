import logging
from typing import Any

from pipeline_v2.models import Pipeline
from rest_framework.serializers import ValidationError
from scheduler.constants import SchedulerConstants as SC
from scheduler.exceptions import JobDeletionError, JobSchedulingError
from scheduler.serializer import AddJobSerializer
from scheduler.tasks import (
    create_or_update_periodic_task,
    delete_periodic_task,
    disable_task,
    enable_task,
)
from utils.user_context import UserContext
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.serializers import ExecuteWorkflowSerializer

logger = logging.getLogger(__name__)


class SchedulerHelper:

    @staticmethod
    def _schedule_task_job(pipeline: Pipeline, job_data: Any) -> None:
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

        task_data[WorkflowKey.WF_ID] = pipeline.workflow.id
        serializer = ExecuteWorkflowSerializer(data=task_data)
        serializer.is_valid(raise_exception=True)
        workflow_id = serializer.get_workflow_id(serializer.validated_data)
        # TODO: Remove unused argument in execute_pipeline_task
        execution_action = serializer.get_execution_action(serializer.validated_data)
        organization_id = UserContext.get_organization_identifier()

        create_or_update_periodic_task(
            cron_string=cron_string,
            task_name=str(pipeline.pk),
            task_path="scheduler.tasks.execute_pipeline_task",
            task_args=[
                str(workflow_id),
                organization_id,
                execution_action or "",
                # TODO: execution_id parameter cannot be removed without a migration.
                "",
                str(pipeline.pk),
                # Added to remain backward compatible - remove after data migration
                # which removes unused args in execute_pipeline_task
                bool(False),
                str(name),
            ],
            enabled=pipeline.active,
        )

    @staticmethod
    def add_or_update_job(pipeline: Pipeline) -> None:
        logger.info(f"Scheduling job for {pipeline}")
        name = f"Pipeline job-{str(pipeline.id)}"
        job_serialize_data = {
            SC.ID: str(pipeline.id),
            SC.CRON_STRING: pipeline.cron_string,
            SC.NAME: name,
        }
        job_serializer = AddJobSerializer(data=job_serialize_data)
        job_serializer.is_valid(raise_exception=True)
        try:
            SchedulerHelper._schedule_task_job(pipeline, job_serializer.validated_data)
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
