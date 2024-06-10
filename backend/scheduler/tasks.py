import json
import logging
from typing import Any

from account.models import Organization
from celery import shared_task
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django_tenants.utils import get_tenant_model, tenant_context
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from workflow_manager.workflow.models.workflow import Workflow
from workflow_manager.workflow.workflow_helper import WorkflowHelper

logger = logging.getLogger(__name__)


def create_periodic_task(
    cron_string: str,
    task_name: str,
    task_path: str,
    task_args: list[Any],
) -> None:
    # Convert task_args to JSON
    task_args_json = json.dumps(task_args)

    # Parse the cron string
    minute, hour, day_of_month, month_of_year, day_of_week = cron_string.split()

    # Create a crontab schedule
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
    )
    logger.info(f"Creating periodic task {task_name} with cron string: {cron_string}")

    # Create periodic task
    PeriodicTask.objects.create(
        crontab=schedule,
        name=task_name,
        task=task_path,
        args=task_args_json,
    )


# TODO: Remove unused args with a migration
@shared_task
def execute_pipeline_task(
    workflow_id: Any,
    org_schema: Any,
    execution_action: Any,
    execution_id: Any,
    pipepline_id: Any,
    with_logs: Any,
    name: Any,
) -> None:
    logger.info(f"Executing pipeline name: {name}")

    try:
        logger.info(f"Executing workflow id: {workflow_id}")
        tenant: Organization = (
            get_tenant_model().objects.filter(schema_name=org_schema).first()
        )
        with tenant_context(tenant):
            workflow = Workflow.objects.get(id=workflow_id)
            logger.info(f"Executing workflow: {workflow}")
            PipelineProcessor.update_pipeline(
                pipepline_id, Pipeline.PipelineStatus.INPROGRESS
            )
            execution_response = WorkflowHelper.complete_execution(
                workflow, execution_id, pipepline_id
            )
            logger.info(f"Execution response: {execution_response}")
        logger.info(f"Execution completed for pipeline: {name}")
    except Exception as e:
        logger.error(f"Failed to execute pipeline: {name}. Error: {e}")


def delete_periodic_task(task_name: str) -> None:
    try:
        task = PeriodicTask.objects.get(name=task_name)
        task.delete()

        logger.info(f"Deleted periodic task: {task_name}")
    except PeriodicTask.DoesNotExist:
        logger.error(f"Periodic task does not exist: {task_name}")


@shared_task
def disable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    task.enabled = False
    task.save()
    PipelineProcessor.update_pipeline(task_name, Pipeline.PipelineStatus.PAUSED, False)


@shared_task
def enable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    task.enabled = True
    task.save()
    PipelineProcessor.update_pipeline(
        task_name, Pipeline.PipelineStatus.RESTARTING, True
    )
