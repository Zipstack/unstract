"""Backfill the pg_periodic_schedule mirror + reconcile Beat/PG schedule
ownership.

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
from scheduler.ownership import (
    pg_scheduler_enabled,
    reconcile_ownership_for,
    resolve_schedule_owner,
)
from scheduler.tasks import mirror_periodic_schedule_upsert

from pg_queue.models import PgPeriodicSchedule

# Rows per DB round trip; mirrors mirror_pg_periodic_tasks.DEFAULT_BATCH_SIZE and the
# batch size used by the repo's other bounded loops (workflow_v2 migration 0012).
DEFAULT_BATCH_SIZE = 1000

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
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            metavar="N",
            help=(
                f"Rows fetched per DB round trip (default {DEFAULT_BATCH_SIZE}). "
                "There is one row per scheduled pipeline, so this bounds memory on "
                "a large installation."
            ),
        )
        parser.add_argument(
            "--mirror-only",
            action="store_true",
            help=(
                "Backfill missing mirror rows and skip the ownership reconcile. "
                "Purely additive: touches only pg_periodic_schedule, never a Beat "
                "PeriodicTask. This is the mode automation runs ONLY on the release path (converge_pg_scheduler with PG_SCHEDULER_ENABLED=false); the adopt path runs the full reconcile — see handle()."
            ),
        )
        parser.add_argument(
            "--release-stale",
            action="store_true",
            help=(
                "Release schedules marked pg_owned while PG_SCHEDULER_ENABLED is "
                "off, handing them back to Beat. Safe for unattended automation at "
                "any flag state: with the gate ON it is a no-op, and with it off it "
                "only ever moves a schedule TO Beat — the fail-safe direction. "
                "Composes with --mirror-only."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        mirror_only = options["mirror_only"]
        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1")
        backfilled = self._backfill_mirrors(dry_run, batch_size)

        # --mirror-only exists because it is safe to run at ANY flag state: backfilling
        # is inert, while the reconcile below — fail-closed when the rollout is off —
        # flips ownership *and disables the matching Beat PeriodicTask* when it is on.
        #
        # It is NO LONGER what the deploy-time automation runs. entrypoint.sh invokes
        # converge_pg_scheduler on every backend start, without --mirror-only, so
        # ownership hand-over IS an unattended action now; the env var is the operator's
        # consent, given once, rather than a command typed per environment. That is
        # deliberate — it is what makes rollback a values change — but it means this
        # path's caller is no longer the only way ownership moves. A previous version of
        # this comment ended "ownership stays an operator action", which stopped being
        # true when the entrypoint switched commands.
        if mirror_only:
            reconciled, pg_owned, failed = 0, 0, 0
        else:
            reconciled, pg_owned, failed = self._reconcile_all(dry_run, batch_size)

        released = 0
        if options["release_stale"]:
            released, release_failed = self._release_stale(dry_run, batch_size)
            failed += release_failed

        prefix = "[dry-run] " if dry_run else ""
        summary = (
            f"{prefix}backfilled={backfilled} reconciled={reconciled} "
            f"pg_owned={pg_owned} released={released} failed={failed}"
        )
        if mirror_only:
            summary = f"{summary} (mirror-only: ownership reconcile skipped)"
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

    def _backfill_mirrors(self, dry_run: bool, batch_size: int) -> int:
        """Create a mirror row for every pipeline-trigger PeriodicTask lacking one.

        Both reads are bounded: the already-mirrored ids stream in via ``iterator``
        rather than materialising the whole table as a Python set, and the
        PeriodicTask scan is chunked. There is one row per scheduled pipeline, so on
        a large installation the unbounded version held the entire pipeline
        population in memory twice.
        """
        # Still one query, still an id set (the membership test below needs it), but
        # streamed and values-only — flat ids, never model instances.
        mirrored = {
            str(pk)
            for pk in PgPeriodicSchedule.objects.values_list(
                "pipeline_id", flat=True
            ).iterator(chunk_size=batch_size)
        }
        backfilled = 0
        periodic_tasks = (
            PeriodicTask.objects.filter(task=_PIPELINE_TASK_PATH)
            .select_related("crontab")
            .order_by("pk")
        )
        for pt in periodic_tasks.iterator(chunk_size=batch_size):
            pipeline_id = pt.name  # = str(pipeline.pk)
            if pipeline_id in mirrored:
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

    def _release_stale(self, dry_run: bool, batch_size: int) -> tuple[int, int]:
        """Hand every stale pg_owned row back to Beat. Returns (released, failed).

        Scoped to ``pg_owned=True`` rows so a clean installation does no work at all,
        and gated on the env switch being OFF: with the ramp ON, a pg_owned row is
        legitimate and releasing it would silently undo the rollout.

        Unlike :meth:`_reconcile_all` this IS safe to run unattended, because its only
        possible effect is moving a schedule to Beat — the same direction the system
        already fails to. That is what lets the deploy run it; see entrypoint.sh.
        """
        if pg_scheduler_enabled():
            self.stdout.write(
                "--release-stale: PG_SCHEDULER_ENABLED is on; pg_owned rows are "
                "legitimate here, nothing released."
            )
            return 0, 0

        released = failed = 0
        for row in (
            PgPeriodicSchedule.objects.filter(pg_owned=True)
            .order_by("pk")
            .iterator(chunk_size=batch_size)
        ):
            if dry_run:
                released += 1
                self.stdout.write(
                    f"[dry-run] would release pipeline {row.pipeline_id} "
                    f"({row.pipeline_name or 'unnamed'}) back to Beat"
                )
                continue
            # Routes through the same transaction the gate-off repair path uses, so
            # Beat's PeriodicTask is re-enabled and next_run_at cleared in step.
            result = reconcile_ownership_for(
                str(row.pipeline_id), row.organization_id, active=row.enabled
            )
            if result is None:  # transaction failed (already logged)
                failed += 1
                continue
            released += 1
        return released, failed

    def _reconcile_all(self, dry_run: bool, batch_size: int) -> tuple[int, int, int]:
        """Reconcile ownership for every mirror row against the current rollout.
        Returns (reconciled, pg_owned, failed).

        Chunked: this loads full model instances, one per scheduled pipeline, and
        each iteration does a Flipt evaluation plus a write — so it is the longest
        loop in the command and the one worth bounding.
        """
        reconciled = pg_owned = failed = 0
        for row in PgPeriodicSchedule.objects.order_by("pk").iterator(
            chunk_size=batch_size
        ):
            if dry_run:
                # Preview only — read the would-be owner (no DB write) so an
                # operator can see how many a ramp change would hand to PG.
                reconciled += 1
                if resolve_schedule_owner():
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
