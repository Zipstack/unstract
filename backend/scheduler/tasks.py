import json
import logging
import traceback
from datetime import datetime
from typing import Any

from celery import shared_task
from croniter import croniter
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask, PeriodicTasks
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


# Sentinel: leave the ``next_run_at`` column alone entirely. Distinct from the
# value ``None``, which is a deliberate instruction to WRITE NULL — the PG tick
# reads NULL as "record a baseline next pass, don't fire this one". Conflating
# the two is what let a stale next_run_at survive a resume.
_LEAVE_NEXT_RUN_AT = object()


def _next_run_at_for_upsert(
    pipeline_id: str, cron_string: str, enabled: bool
) -> datetime | None | object:
    """What the mirror upsert should do with ``next_run_at``. Three outcomes:

    * :data:`_LEAVE_NEXT_RUN_AT` — don't touch the column. A brand-new row, a
      not-yet-baselined one (``next_run_at`` NULL), or an unchanged cron on a
      row that was already enabled. The PG tick's no-burst baseline owns it.
    * ``None`` — write NULL, i.e. "baseline on the next tick, don't fire". A
      RESUME: the mirror row was ``enabled=False`` and the incoming state is
      ``True``.
    * a ``datetime`` — a cron EDIT on an already-baselined row: retarget to the
      new cron's next match for Beat parity (UN-3690), else the scheduler fires
      once more at the stale old-cron time.

    **Why resume needs the explicit NULL, and why it is checked first.** While a
    schedule is paused its ``next_run_at`` keeps drifting into the past, so the
    instant ``enabled`` flips back the tick's
    ``WHERE pg_owned AND enabled AND (next_run_at IS NULL OR <= now())`` matches
    and the pipeline runs immediately — days late, on top of whatever the
    operator triggered by hand. ``enable_task`` already baselines for exactly
    this reason (see ``_mirror_periodic_schedule_set_enabled``), but the UI
    resume does not take that path: it re-saves the pipeline, which reaches
    ``SchedulerHelper._schedule_task_job`` → here and ``reconcile_ownership_for``
    — and that one deliberately baselines only on a Beat→PG hand-over
    (``pg_owned and not was_pg_owned``), so an already-``pg_owned`` row keeps its
    stale value and nothing clears it. Observed on integration 2026-08-12, -14
    and -20: three enables of ``gallh_load_test``, three spurious runs 2-3s
    later, each settling back onto the cron afterwards. Exactly one extra run per
    enable — bounded, but it costs a full LLM pass over the source.

    Resume is checked BEFORE the cron comparison because a resume that also
    edited the cron must still baseline; ordering it the other way would let the
    ``cron_string == existing`` early-out swallow the resume case, which is the
    common one (a plain pause/resume does not change the cron).

    Scoped to the TRANSITION, not to every call — the same discipline
    ``reconcile_ownership_for`` uses. This runs on every pipeline save, so
    clearing unconditionally would re-baseline mid-cycle: a save at 12:07:59
    against a 12:08 ``next_run_at`` would skip that fire entirely.

    Fully guarded on purpose: this is an OPTIONAL enhancement over the mandatory
    ``cron_string``/``enabled`` mirror write, so a read failure, a ``None``/invalid
    cron (normally rejected upstream by ``PipelineSerializer.validate_cron_string``
    in ``pipeline_v2``), or a croniter error must degrade to leaving the column
    alone — never take the base mirror write down with it.
    """
    try:
        existing = (
            PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id)
            .values("cron_string", "next_run_at", "enabled")
            .first()
        )
        if existing is None or existing["next_run_at"] is None:
            return _LEAVE_NEXT_RUN_AT
        if enabled and not existing["enabled"]:
            return None
        if existing["cron_string"] == cron_string:
            return _LEAVE_NEXT_RUN_AT
        return croniter(cron_string, timezone.now()).get_next(datetime)
    except Exception as exc:
        # Log the ACTUAL cause (bad read; cron=None → AttributeError;
        # CroniterBadCronError / CroniterBadDateError; a croniter API change) — a
        # generic "could not recompute" is a dead end when debugging a stale fire.
        logger.warning(
            "pg_periodic_schedule: could not resolve next_run_at for pipeline %s "
            "(cron %r): %s",
            pipeline_id,
            cron_string,
            exc,
            exc_info=True,
        )
        return _LEAVE_NEXT_RUN_AT


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
        defaults: dict[str, Any] = {
            "organization_id": organization_id or "",
            "workflow_id": workflow_id or None,
            "pipeline_name": pipeline_name or "",
            "cron_string": cron_string,
            "enabled": enabled,
        }
        # next_run_at is owned by the PG tick, with two exceptions this path must
        # honour: a cron EDIT retargets it (Beat parity, UN-3690) and a RESUME
        # clears it to NULL so a value that went stale during the pause can't fire
        # a catch-up run the moment the schedule is re-enabled. The helper decides
        # which — including "leave it alone", which is NOT the same as writing NULL
        # — and is fully guarded so it can never take down the mandatory
        # cron_string/enabled mirror write below.
        next_run_at = _next_run_at_for_upsert(pipeline_id, cron_string, enabled)
        if next_run_at is not _LEAVE_NEXT_RUN_AT:
            defaults["next_run_at"] = next_run_at
        PgPeriodicSchedule.objects.update_or_create(
            pipeline_id=pipeline_id,
            defaults=defaults,
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
        updates: dict = {"enabled": enabled, "updated_at": timezone.now()}
        if enabled:
            # Resume → baseline instead of firing a stale next_run_at. While the
            # schedule was paused its next_run_at kept drifting into the past, so the
            # PG tick's `next_run_at <= now()` matches on the very next pass and the
            # pipeline runs IMMEDIATELY on resume — the longer the pause, the more
            # certain. NULL means "record a baseline next tick, don't fire this cycle"
            # (pg_queue/models.py:366), which resumes at the next cron match instead.
            #
            # Observed on integration 2026-08-14: gallh_load_test fired ~2s after
            # being re-enabled, against a next_run_at two days old.
            #
            # CORRECTION (2026-08-24): this used to add "Beat parity, not a new rule:
            # DatabaseScheduler ... recomputes due-ness from the crontab each tick, so
            # re-enabling never produced a catch-up run there." That was WRONG.
            # DatabaseScheduler recomputes from PeriodicTask.last_run_at, which is
            # exactly what makes it catch up too — releasing 23 schedules back to Beat
            # fired 4 pipelines and 3 periodics within 30 ms. Beat needs the same
            # baseline on its own clock; see scheduler/ownership.py. So this is a
            # shared hazard of both schedulers, not a PG-only regression.
            #
            # Safe to do unconditionally here: this helper is reached only from
            # enable_task/disable_task (an explicit pause/resume), never from the
            # per-save path — so it cannot re-baseline mid-cycle and skip a fire.
            updates["next_run_at"] = None
        matched = PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).update(
            **updates
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
    PeriodicTask.objects.get(name=task_name)  # preserve DoesNotExist on a bad name
    # Resume → the schedule is active again, but Beat must fire it ONLY when it's
    # not handed to PG — else a pg_owned schedule would fire from both Beat and PG
    # (the ②c ownership invariant; reconcile sets the same on create/update, but
    # resume takes this path). Lock the mirror row + write only the `enabled`
    # column (not a full task.save() of stale state) so a concurrent
    # reconcile_ownership_for can't be clobbered into a double-fire.
    with transaction.atomic():
        pg_owned = (
            PgPeriodicSchedule.objects.select_for_update()
            .filter(pipeline_id=task_name)
            .values_list("pg_owned", flat=True)
            .first()
            or False
        )
        PeriodicTask.objects.filter(name=task_name).update(enabled=not pg_owned)
        # Bulk .update() bypasses django-celery-beat's post_save signal, so
        # PeriodicTasks.last_update never bumps and DatabaseScheduler never reloads
        # — the resumed pipeline would stay disabled in Beat's in-memory schedule
        # and silently never fire (disable_task uses .save() and doesn't have this
        # gap). Bump last_update explicitly so Beat reloads on the next tick.
        PeriodicTasks.update_changed()
    # mirror.enabled tracks pipeline.active (True on resume) regardless of owner.
    _mirror_periodic_schedule_set_enabled(task_name, True)
    PipelineProcessor.update_pipeline(task_name, Pipeline.PipelineStatus.RESTARTING, True)
