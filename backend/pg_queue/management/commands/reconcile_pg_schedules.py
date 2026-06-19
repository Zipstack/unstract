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

from django.core.management.base import BaseCommand, CommandError
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from scheduler.ownership import reconcile_ownership_for, resolve_schedule_owner
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
        backfilled = self._backfill_mirrors(dry_run)
        reconciled, pg_owned, failed = self._reconcile_all(dry_run)

        prefix = "[dry-run] " if dry_run else ""
        summary = (
            f"{prefix}backfilled={backfilled} reconciled={reconciled} "
            f"pg_owned={pg_owned} failed={failed}"
        )
        if failed:
            # Surface failures where the operator looks (and to automation).
            self.stderr.write(self.style.ERROR(summary))
            raise CommandError(f"{failed} schedule(s) failed to reconcile")
        self.stdout.write(self.style.SUCCESS(summary))

    def _mirror_fields_from_args(self, pt: Any, pipeline_id: str) -> dict | None:
        """Extract the mirror fields from PeriodicTask.args, or None (logged) for a
        malformed/non-array row — a bad row must not abort the whole command.
        """
        try:
            # json.JSONDecodeError is a ValueError subclass, so one except covers
            # both the parse error and the non-array guard below.
            task_args = json.loads(pt.args or "[]")
            if not isinstance(task_args, list):
                raise ValueError(f"expected JSON array, got {type(task_args).__name__}")
        except ValueError as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"skipping pipeline {pipeline_id}: bad PeriodicTask.args ({exc})"
                )
            )
            return None
        return {
            "workflow_id": task_args[0] if len(task_args) > 0 else None,
            "organization_id": (task_args[1] if len(task_args) > 1 else "") or "",
            # args[6] is the synthetic "Pipeline job-<id>" label; the real name
            # self-heals via the dual-write on the next schedule edit.
            "pipeline_name": task_args[6] if len(task_args) > 6 else "",
        }

    def _backfill_mirrors(self, dry_run: bool) -> int:
        """Create a mirror row for every pipeline-trigger PeriodicTask lacking one."""
        backfilled = 0
        for pt in PeriodicTask.objects.filter(task=_PIPELINE_TASK_PATH):
            pipeline_id = pt.name  # = str(pipeline.pk)
            if PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).exists():
                continue
            fields = self._mirror_fields_from_args(pt, pipeline_id)
            if fields is None:
                continue
            self.stdout.write(
                f"backfill mirror for pipeline {pipeline_id} (enabled={pt.enabled})"
            )
            if not dry_run:
                mirror_periodic_schedule_upsert(
                    pipeline_id=pipeline_id,
                    cron_string=_cron_from_crontab(pt.crontab),
                    enabled=pt.enabled,
                    **fields,
                )
            backfilled += 1
        return backfilled

    def _reconcile_all(self, dry_run: bool) -> tuple[int, int, int]:
        """Reconcile ownership for every mirror row against the current rollout.
        Returns (reconciled, pg_owned, failed).
        """
        reconciled = pg_owned = failed = 0
        for row in PgPeriodicSchedule.objects.all():
            if dry_run:
                # Preview only — read the would-be owner (no DB write) so an
                # operator can see how many a ramp change would hand to PG.
                reconciled += 1
                if resolve_schedule_owner(str(row.pipeline_id), row.organization_id):
                    pg_owned += 1
                continue
            # mirror.enabled tracks pipeline.active (dual-write); use it as the
            # 'active' input so a paused schedule isn't re-enabled by reconcile.
            result = reconcile_ownership_for(
                str(row.pipeline_id), row.organization_id, active=row.enabled
            )
            if result is None:  # transaction failed (already logged)
                failed += 1
                continue
            reconciled += 1
            if result:
                pg_owned += 1
        return reconciled, pg_owned, failed
