import json
import logging
from typing import Any

from celery import shared_task
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django_tenants.utils import get_tenant_model, tenant_context

from backend.constants import FeatureFlag
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    from account_v2.subscription_loader import load_plugins, validate_etl_run
    from pipeline_v2.models import Pipeline
    from pipeline_v2.pipeline_processor import PipelineProcessor
    from utils.user_context import UserContext
    from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper
else:
    from account.models import Organization
    from account.subscription_loader import load_plugins, validate_etl_run
    from pipeline.models import Pipeline
    from pipeline.pipeline_processor import PipelineProcessor
    from workflow_manager.workflow.workflow_helper import WorkflowHelper


logger = logging.getLogger(__name__)
subscription_loader = load_plugins()


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
    if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
        execute_pipeline_task_v2(
            workflow_id=workflow_id,
            organization_id=org_schema,
            execution_id=execution_id,
            pipeline_id=pipepline_id,
            pipeline_name=name,
        )
        return
    logger.info(f"Executing pipeline name: {name}")
    try:
        tenant: Organization = (
            get_tenant_model().objects.filter(schema_name=org_schema).first()
        )
        with tenant_context(tenant):
            pipeline = PipelineProcessor.fetch_pipeline(
                pipeline_id=pipepline_id, check_active=True
            )
            workflow = pipeline.workflow
            logger.info(f"Executing workflow: {workflow} by pipeline {pipeline}")
            if (
                subscription_loader
                and subscription_loader[0]
                and not validate_etl_run(org_schema)
            ):
                try:
                    logger.info(f"Disabling ETL task: {pipepline_id}")
                    disable_task(pipepline_id)
                except Exception as e:
                    logger.warning(
                        f"Failed to disable task: {pipepline_id}. Error: {e}"
                    )
                return
            logger.info(f"Executing workflow: {workflow}")
            PipelineProcessor.initialize_pipeline_sync(pipeline_id=pipepline_id)
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


def execute_pipeline_task_v2(
    workflow_id: Any,
    organization_id: Any,
    execution_id: Any,
    pipeline_id: Any,
    pipeline_name: Any,
) -> None:
    """V2 of execute_pipeline method.

    Args:
        workflow_id (Any): UID of workflow entity
        org_schema (Any): Organization Identifier
        execution_id (Any): UID of execution entity
        pipeline_id (Any): UID of pipeline entity
        name (Any): pipeline name
    """
    try:
        logger.info(
            f"Executing workflow id: {workflow_id} for pipeline {pipeline_name}"
        )
        # Set organization in state store for execution
        UserContext.set_organization_identifier(organization_id)
        if (
            subscription_loader
            and subscription_loader[0]
            and not validate_etl_run(organization_id)
        ):
            try:
                logger.info(f"Disabling ETL task: {pipeline_id}")
                disable_task(pipeline_id)
            except Exception as e:
                logger.warning(f"Failed to disable task: {pipeline_id}. Error: {e}")
            return
        workflow = WorkflowHelper.get_workflow_by_id(
            id=workflow_id, organization_id=organization_id
        )
        logger.info(f"Executing workflow: {workflow}")
        PipelineProcessor.update_pipeline(
            pipeline_id, Pipeline.PipelineStatus.INPROGRESS
        )
        execution_response = WorkflowHelper.complete_execution(
            workflow, execution_id, pipeline_id
        )
        logger.info(
            f"Execution response for pipeline {pipeline_name} of organization "
            f"{organization_id}: {execution_response}"
        )
        logger.info(
            f"Execution completed for pipeline {pipeline_name} of organization: "
            f"{organization_id}"
        )
    except Exception as e:
        logger.error(f"Failed to execute pipeline: {pipeline_name}. Error: {e}")


def delete_periodic_task(task_name: str) -> None:
    try:
        task = PeriodicTask.objects.get(name=task_name)
        task.delete()

        logger.info(f"Deleted periodic task: {task_name}")
    except PeriodicTask.DoesNotExist:
        logger.error(f"Periodic task does not exist: {task_name}")


def disable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    task.enabled = False
    task.save()
    PipelineProcessor.update_pipeline(task_name, Pipeline.PipelineStatus.PAUSED, False)


def enable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    task.enabled = True
    task.save()
    PipelineProcessor.update_pipeline(
        task_name, Pipeline.PipelineStatus.RESTARTING, True
    )
