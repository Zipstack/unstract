"""Backfill the pg_periodic_schedule mirror + reconcile Beat/PG schedule
ownership (Phase 9, ②c).

Run this:
- **once** after deploying the mirror, to backfill rows for schedules created
  before the mirror existed (the dual-write only covers schedules touched since);
- **after each Flipt ramp change** to ``pg_scheduler_enabled``, to apply the new
  percentage — flipping ``pg_owned`` and the matching Beat ``PeriodicTask`` for
  every schedule (the create/update path only reconciles the schedule it edits).

It is idempotent and safe to run anytime: with the rollout off it leaves every
schedule on Beat. Could later be driven periodically (e.g. by the orchestrator);
kept a command here so the ramp stays an explicit, auditable ops action.
"""

import json
from typing import Any

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from scheduler.ownership import reconcile_ownership_for
from scheduler.tasks import mirror_periodic_schedule_upsert

from pg_queue.models import PgPeriodicSchedule

# Only the pipeline-trigger PeriodicTasks are scheduled pipelines (other periodic
# tasks — metrics, audit — are not mirrored).
_PIPELINE_TASK_PATH = "scheduler.tasks.execute_pipeline_task"


def _cron_from_crontab(crontab: CrontabSchedule | None) -> str:
    """Reconstruct the 5-field cron string from a CrontabSchedule row."""
    if crontab is None:
        return ""
    return (
        f"{crontab.minute} {crontab.hour} {crontab.day_of_month} "
        f"{crontab.month_of_year} {crontab.day_of_week}"
    )


class Command(BaseCommand):
    help = (
        "Backfill pg_periodic_schedule mirrors for pre-existing schedules and "
        "reconcile Beat/PG ownership against the current pg_scheduler_enabled "
        "rollout. Idempotent; with the rollout off, leaves everything on Beat."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]

        # 1. Backfill: every pipeline-trigger PeriodicTask should have a mirror.
        backfilled = 0
        periodic_tasks = PeriodicTask.objects.filter(task=_PIPELINE_TASK_PATH)
        for pt in periodic_tasks:
            pipeline_id = pt.name  # = str(pipeline.pk)
            if PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).exists():
                continue
            task_args = json.loads(pt.args or "[]")
            workflow_id = task_args[0] if len(task_args) > 0 else None
            organization_id = task_args[1] if len(task_args) > 1 else ""
            # args[6] is the synthetic "Pipeline job-<id>" label; the real name
            # self-heals via the dual-write on the next schedule edit.
            pipeline_name = task_args[6] if len(task_args) > 6 else ""
            self.stdout.write(
                f"backfill mirror for pipeline {pipeline_id} " f"(enabled={pt.enabled})"
            )
            if not dry_run:
                mirror_periodic_schedule_upsert(
                    pipeline_id=pipeline_id,
                    organization_id=organization_id or "",
                    workflow_id=workflow_id,
                    pipeline_name=pipeline_name,
                    cron_string=_cron_from_crontab(pt.crontab),
                    enabled=pt.enabled,
                )
            backfilled += 1

        # 2. Reconcile ownership for every mirror row against the current rollout.
        reconciled = pg_owned_count = 0
        for row in PgPeriodicSchedule.objects.all():
            reconciled += 1
            if dry_run:
                continue
            # mirror.enabled tracks pipeline.active (dual-write); use it as the
            # 'active' input so a paused schedule isn't re-enabled by reconcile.
            if reconcile_ownership_for(
                str(row.pipeline_id), row.organization_id, row.enabled
            ):
                pg_owned_count += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}backfilled={backfilled} reconciled={reconciled} "
                f"pg_owned={pg_owned_count}"
            )
        )
