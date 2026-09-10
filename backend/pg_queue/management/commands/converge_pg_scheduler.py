"""Converge schedule ownership to the state ``PG_SCHEDULER_ENABLED`` declares.

One idempotent entry point, **both directions**:

    PG_SCHEDULER_ENABLED=true   → adopt   (PG fires; Beat rows disabled)
    PG_SCHEDULER_ENABLED=false  → release (Beat fires; pg_owned cleared)

Why one converging command rather than an adopt command and a release command: the
reverse direction is the one that matters under pressure, and a rollback nobody can
run is not a rollback. Splitting it left the reverse as a *procedure* — remember the
command, remember the flags, remember to run it in every environment. Here the env
var declares intent and the deploy makes the database match, so reverting is a values
change like any other, and re-running changes nothing once converged.

**Safe to run unattended**, which is what lets ``entrypoint.sh`` call it on every
start:

* Both directions are idempotent in OUTCOME — ``_set_ownership`` skips periodic rows
  already in the target state. The pipeline path is idempotent but **not** free: it
  rewrites ``pg_periodic_schedule`` and the Beat ``PeriodicTask`` row and bumps
  ``PeriodicTasks.update_changed()`` for every schedule on every call, whether or not
  ownership changed — so a backend start costs 2N row writes and N Beat reloads. Safe
  to repeat, not a no-op; an earlier version of this line claimed the latter.
* Neither direction invents state. Beat's ``PeriodicTask`` rows are only ever
  *disabled* and *re-enabled*, never created or deleted, and the value written on
  release is the one recorded before adoption (``pg_periodic_task.enabled``, and the
  pipeline's own ``active``) — so a schedule an operator had switched off stays off
  through a full adopt→release cycle.
* Adoption is not unilateral: it happens only because someone set the env var.

**What it cannot do, and you must:** converging to Beat restores *ownership*, not
*capacity*. Beat publishes to RabbitMQ, so a released schedule only fires again if
``workerSchedulerV2`` (and ``workerMetrics`` for the periodics) are running. Flip
those back in the SAME change that sets ``PG_SCHEDULER_ENABLED=false`` — otherwise
you have simply moved the outage. The release path logs a warning saying so.

Periodics (``dashboard_metrics.*``) are opt-in via ``--periodics``: pipelines and
metrics are separate rollout decisions, and metrics have their own consumer
(``workerPgMetrics``) that has to be deployed before they can be adopted.
"""

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from scheduler.ownership import pg_scheduler_enabled


class Command(BaseCommand):
    help = (
        "Converge schedule ownership to what PG_SCHEDULER_ENABLED declares: adopt to "
        "the PG scheduler when on, release back to Celery Beat when off. Idempotent "
        "in both directions and safe to run on every deploy."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )
        parser.add_argument(
            "--periodics",
            action="store_true",
            help=(
                "Also converge the non-pipeline periodics (dashboard_metrics.*). "
                "Off by default: adopting them requires workerPgMetrics to be "
                "deployed, so it is a separate rollout decision from pipelines."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        periodics = options["periodics"]
        target_pg = pg_scheduler_enabled()

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Converging schedule ownership → "
                f"{'PG scheduler' if target_pg else 'Celery Beat'} "
                f"(PG_SCHEDULER_ENABLED={'true' if target_pg else 'false'})"
            )
        )

        if target_pg:
            # Mirrors are backfilled first: a pipeline with no mirror row cannot be
            # owned, and reconcile reports it as still-on-Beat rather than adopting it.
            call_command("reconcile_pg_schedules", dry_run=dry_run)
            if periodics:
                # An empty name list means "every mirrored row" (the flag is
                # `nargs="*"`, and the command distinguishes absent from empty).
                # mirror_pg_periodic_tasks always backfills before flipping
                # ownership, so this one call covers both halves.
                call_command("mirror_pg_periodic_tasks", adopt=[], dry_run=dry_run)
        else:
            # --mirror-only keeps the backfill (inert at any flag state) while
            # --release-stale hands back anything still marked pg_owned. Together
            # they are the pipeline rollback.
            call_command(
                "reconcile_pg_schedules",
                mirror_only=True,
                release_stale=True,
                dry_run=dry_run,
            )
            if periodics:
                call_command("mirror_pg_periodic_tasks", release=[], dry_run=dry_run)
            self.stdout.write(
                self.style.WARNING(
                    "Released to Beat. Beat publishes over RabbitMQ — these schedules "
                    "fire again ONLY if workerSchedulerV2 (and workerMetrics, with "
                    "--periodics) are running. Check that before relying on this."
                )
            )

        self.stdout.write(self.style.SUCCESS("Convergence complete."))
