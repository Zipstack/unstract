import json
import logging
import traceback
from typing import Any, Optional

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


def create_or_update_periodic_task(
    cron_string: str,
    task_name: str,
    task_path: str,
    task_args: list[Any],
    enabled: bool = True,
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

    periodic_task, created = PeriodicTask.objects.update_or_create(
        name=task_name,
        defaults={
            "task": task_path,
            "crontab": schedule,
            "enabled": enabled,
            "args": task_args_json,
        },
    )

    if created:
        logger.info(f"Created periodic task {periodic_task}")
    else:
        logger.info(f"Updated periodic task {periodic_task}")


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
            organization_id=org_schema,
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
            logger.info(
                f"Executing pipeline: {pipeline}, "
                f"workflow: {workflow}, pipeline name: {name}"
            )
            if (
                subscription_loader
                and subscription_loader[0]
                and not validate_etl_run(org_schema)
            ):
                try:
                    logger.info(
                        f"Subscription expired for '{org_schema}', "
                        f"disabling pipeline: {pipepline_id}"
                    )
                    disable_task(pipepline_id)
                except Exception as e:
                    logger.warning(
                        f"Failed to disable task: {pipepline_id}. Error: {e}"
                    )
                return
            PipelineProcessor.initialize_pipeline_sync(pipeline_id=pipepline_id)
            PipelineProcessor.update_pipeline(
                pipepline_id, Pipeline.PipelineStatus.INPROGRESS
            )
            execution_response = WorkflowHelper.complete_execution(
                workflow=workflow, pipeline_id=pipepline_id
            )
            execution_response.remove_result_metadata_keys()
            logger.info(f"Execution response: {execution_response}")
        logger.info(f"Execution completed for pipeline: {name}")
    except Exception as e:
        logger.error(
            f"Failed to execute pipeline: {name}. Error: {e}"
            f"\n\n'''{traceback.format_exc()}```"
        )


def execute_pipeline_task_v2(
    organization_id: Any,
    pipeline_id: Any,
    pipeline_name: Any,
) -> None:
    """V2 of execute_pipeline method.

    Args:
        workflow_id (Any): UID of workflow entity
        org_schema (Any): Organization Identifier
        pipeline_id (Any): UID of pipeline entity
        name (Any): pipeline name
    """
    try:
        # Set organization in state store for execution
        UserContext.set_organization_identifier(organization_id)
        pipeline = PipelineProcessor.fetch_pipeline(
            pipeline_id=pipeline_id, check_active=True
        )
        workflow = pipeline.workflow
        logger.info(
            f"Executing pipeline: {pipeline_id}, "
            f"workflow: {workflow}, pipeline name: {pipeline_name}"
        )
        if (
            subscription_loader
            and subscription_loader[0]
            and not validate_etl_run(organization_id)
        ):
            try:
                logger.info(
                    f"Subscription expired for '{organization_id}', "
                    f"disabling pipeline: {pipeline_id}"
                )
                disable_task(pipeline_id)
            except Exception as e:
                logger.warning(f"Failed to disable task: {pipeline_id}. Error: {e}")
            return
        PipelineProcessor.update_pipeline(
            pipeline_id, Pipeline.PipelineStatus.INPROGRESS
        )
        execution_response = WorkflowHelper.complete_execution(
            workflow=workflow, pipeline_id=pipeline_id
        )
        execution_response.remove_result_metadata_keys()
        logger.info(
            f"Execution response for pipeline {pipeline_name} of organization "
            f"{organization_id}: {execution_response}"
        )
        logger.info(
            f"Execution completed for pipeline {pipeline_name} of organization: "
            f"{organization_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to execute pipeline: {pipeline_name}. Error: {e}"
            f"\n\n'''{traceback.format_exc()}```"
        )


def delete_periodic_task(task_name: str) -> None:
    try:
        task = PeriodicTask.objects.get(name=task_name)
        task.delete()

        logger.info(f"Deleted periodic task: {task_name}")
    except PeriodicTask.DoesNotExist:
        logger.error(f"Periodic task does not exist: {task_name}")


def get_periodic_task(task_name: str) -> Optional[PeriodicTask]:
    try:
        return PeriodicTask.objects.get(name=task_name)
    except PeriodicTask.DoesNotExist:
        return None


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
