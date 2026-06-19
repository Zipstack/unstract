import json
import logging
import traceback
from typing import Any

from celery import shared_task
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from pg_queue.models import PgPeriodicSchedule
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from utils.user_context import UserContext
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pg_periodic_schedule mirror (Phase 9, ②a) — INERT.
# Dual-writes the schedule definition into pg_periodic_schedule alongside the
# django_celery_beat PeriodicTask, so a future PG-backed scheduler (folded into
# the reaper/orchestrator loop) can fire due schedules without Celery Beat.
# Nothing reads the table yet. Every write is best-effort: a mirror failure must
# NEVER break the existing Beat scheduling path.
#
# The upsert is driven from SchedulerHelper._schedule_task_job (which holds the
# Pipeline object, so it sources the real pipeline_name + clean ids — no parsing
# of the serialized PeriodicTask args). The enable/disable/delete toggles are
# keyed by pipeline_id only, so they live here next to the functions that mutate
# the PeriodicTask.
# ---------------------------------------------------------------------------


def mirror_periodic_schedule_upsert(
    *,
    pipeline_id: str,
    organization_id: str,
    workflow_id: str | None,
    pipeline_name: str,
    cron_string: str,
    enabled: bool,
) -> None:
    try:
        PgPeriodicSchedule.objects.update_or_create(
            pipeline_id=pipeline_id,
            defaults={
                "organization_id": organization_id or "",
                "workflow_id": workflow_id or None,
                "pipeline_name": pipeline_name or "",
                "cron_string": cron_string,
                "enabled": enabled,
            },
        )
    except Exception:
        logger.exception(
            f"pg_periodic_schedule mirror upsert failed for pipeline {pipeline_id} "
            "(inert mirror — Beat scheduling unaffected)"
        )


def _mirror_periodic_schedule_set_enabled(pipeline_id: str, enabled: bool) -> None:
    try:
        # Bump updated_at explicitly: queryset .update() does NOT trigger the
        # field's auto_now, so without this a pause/resume would change enabled
        # without advancing the "last changed" timestamp.
        matched = PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).update(
            enabled=enabled, updated_at=timezone.now()
        )
        if matched == 0:
            # No mirror row — e.g. a pipeline scheduled before this shipped, or
            # whose upsert was swallowed. .update() can't self-heal (it only
            # touches existing rows); the backfill of such rows lands with the
            # scheduler that reads this table (②b). Log so the gap is visible.
            logger.info(
                f"pg_periodic_schedule mirror enabled={enabled} matched 0 rows for "
                f"pipeline {pipeline_id} (not yet mirrored — backfilled in ②b)"
            )
    except Exception:
        logger.exception(
            f"pg_periodic_schedule mirror enabled={enabled} failed for pipeline "
            f"{pipeline_id} (inert mirror — Beat scheduling unaffected)"
        )


def _mirror_periodic_schedule_delete(pipeline_id: str) -> None:
    try:
        PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).delete()
    except Exception:
        logger.exception(
            f"pg_periodic_schedule mirror delete failed for pipeline {pipeline_id} "
            "(inert mirror — Beat scheduling unaffected)"
        )


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
    # The inert PG mirror upsert is driven by the caller
    # (SchedulerHelper._schedule_task_job), which has the Pipeline object and so
    # sources the real pipeline_name + ids directly (no positional arg parsing).


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
    execute_pipeline_task_v2(
        organization_id=org_schema,
        pipeline_id=pipepline_id,
        pipeline_name=name,
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
        # Check subscription status before ETL run (cloud-specific)
        try:
            from pluggable_apps.subscription_v2.subscription_helper import (
                SubscriptionHelper,
            )

            if not SubscriptionHelper.validate_etl_run(organization_id):
                try:
                    logger.info(
                        f"Subscription expired for '{organization_id}', "
                        f"disabling pipeline: {pipeline_id}"
                    )
                    disable_task(pipeline_id)
                except Exception as e:
                    logger.warning(f"Failed to disable task: {pipeline_id}. Error: {e}")
                return
        except ModuleNotFoundError:
            # Subscription module not available (OSS deployment), skip validation
            pass
        PipelineProcessor.update_pipeline(pipeline_id, Pipeline.PipelineStatus.INPROGRESS)
        # Mark the File in file history to avoid duplicate execution
        # only for ETL and TASK execution
        use_file_history: bool = True
        execution_response = WorkflowHelper.complete_execution(
            workflow=workflow,
            pipeline_id=pipeline_id,
            use_file_history=use_file_history,
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
    # Clean the inert PG mirror regardless of whether the PeriodicTask existed.
    _mirror_periodic_schedule_delete(task_name)


def get_periodic_task(task_name: str) -> PeriodicTask | None:
    try:
        return PeriodicTask.objects.get(name=task_name)
    except PeriodicTask.DoesNotExist:
        return None


def disable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    task.enabled = False
    task.save()
    # Mirror the PeriodicTask.enabled state right after save (before the pipeline
    # status update, so a failure there can't desync the inert mirror).
    _mirror_periodic_schedule_set_enabled(task_name, False)
    PipelineProcessor.update_pipeline(task_name, Pipeline.PipelineStatus.PAUSED, False)


def enable_task(task_name: str) -> None:
    task = PeriodicTask.objects.get(name=task_name)
    # Resume → the schedule is active again, but Beat must fire it ONLY when it's
    # not handed to PG — else a pg_owned schedule would fire from both Beat and PG
    # (the ②c ownership invariant; reconcile sets the same on create/update, but
    # resume takes this path). Default False (not owned) when there's no mirror.
    pg_owned = (
        PgPeriodicSchedule.objects.filter(pipeline_id=task_name)
        .values_list("pg_owned", flat=True)
        .first()
        or False
    )
    task.enabled = not pg_owned
    task.save()
    # mirror.enabled tracks pipeline.active (True on resume) regardless of owner.
    _mirror_periodic_schedule_set_enabled(task_name, True)
    PipelineProcessor.update_pipeline(task_name, Pipeline.PipelineStatus.RESTARTING, True)
