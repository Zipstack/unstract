"""Mirror non-pipeline Beat periodics into ``pg_periodic_task``, and hand them over.

The Beat-replacement half for everything that is not a scheduled pipeline
(UN-3796): ``dashboard_metrics.*``, log-history, audit, and anything an operator
has added. Pipeline schedules keep their own mirror and their own percentage ramp
(``reconcile_pg_schedules``); this command deliberately skips them.

Two steps, deliberately separate:

* **mirror** (default) — upsert a ``PgPeriodicTask`` row for every non-pipeline
  ``PeriodicTask``. Purely additive and inert: rows land ``pg_owned=False``, so the
  PG scheduler still fires nothing and Beat keeps firing everything.
* **adopt / release** (explicit flags) — the actual hand-over. ``--adopt`` flips
  ``pg_owned=True`` **and** disables the matching Beat ``PeriodicTask``, in one
  transaction. ``--release`` reverses it. Doing both halves atomically is the whole
  point: a row that is ``pg_owned`` while Beat still has it enabled fires **twice**,
  which for ``cleanup_*`` means two concurrent deletes and for ``aggregate_*`` means
  double-counted metrics.

Idempotent and safe to re-run. Mirroring changes no behaviour on its own; only
``--adopt`` does, and only for the rows it names.

Unlike the pipeline ramp there is no percentage: these are a handful of global
singletons, and the acceptance gate (Celery scaled to zero) needs all of them on PG,
so the meaningful states are "all Beat" and "all PG" with a per-name escape hatch.
"""

import json
import logging
from typing import Any, NamedTuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask, PeriodicTasks

from pg_queue.models import PgPeriodicTask

logger = logging.getLogger(__name__)

# Rows per DB round trip. Matches the batch size the repo's other bounded loops use
# (e.g. workflow_v2 migration 0012's "delete in batches to avoid long-running
# transactions"). Overridable with --batch-size.
DEFAULT_BATCH_SIZE = 1000

# Task paths this command must NOT mirror.
#
# Pipeline triggers own a separate mirror (pg_periodic_schedule) and a separate
# percentage ramp; mirroring one here too would give it two owners. BOTH known task
# paths are listed even though ``SchedulerHelper._schedule_task_job`` only writes the
# first today: a real Beat table was found carrying a legacy ``execute_pipeline_task_v2``
# row, and it is only excluded here by luck of being disabled. Matching on the task
# path rather than a name convention keeps that from depending on luck.
#
# ``celery.backend_cleanup`` is Celery's own built-in: it prunes the Celery RESULT
# BACKEND. It is meaningless on PG (nothing there registers it, and the backend it
# cleans stops existing once Celery is off), so it stays with Beat and simply retires
# alongside it.
_EXCLUDED_TASK_PATHS = frozenset(
    {
        "scheduler.tasks.execute_pipeline_task",
        "execute_pipeline_task_v2",
        "celery.backend_cleanup",
    }
)


def cron_from_periodic_task(task: PeriodicTask) -> str:
    """Best-effort 5-field cron for a Beat periodic, or "" if not expressible.

    Beat schedules a task by ``crontab``, ``interval``, ``solar`` or ``clocked``.
    Only the first two are in use here, and only they map onto cron:

    * ``crontab`` — a direct field-for-field reconstruction.
    * ``interval`` — expressed as a step cron ONLY where one exists exactly.

    Returns ``""`` for anything else — notably **second**-resolution intervals,
    which have no cron expression at all. Coarsening one to a minute would silently
    change how often it runs, so the caller skips those and says so rather than
    guessing.

    **``*/N`` is not "every N".** A step cron restarts at each field boundary, so it
    is faithful only when N divides the field's range exactly. Otherwise the last
    step of one period runs into the first of the next and the task fires early —
    silently, and only at the boundary, which is the hardest kind of drift to spot:

    * ``*/7`` minutes → :00 :07 … :56, then **:00** — a 4-minute gap, not 7.
    * ``*/45`` minutes → :00 :45, then **:00** — fires roughly twice as often.
    * ``0 */5`` hours → 0 5 10 15 20, then **0** — a 4-hour gap, not 5.

    So minutes need ``60 % every == 0`` and hours ``24 % every == 0``, not merely a
    range check.

    **Days are worse and are refused beyond 1.** ``*/N`` on day-of-month restarts
    every month, and months are 28-31 days, so the gap at the boundary varies by
    month and even by year: ``0 0 */7 * *`` fires on the 1st, 8th, 15th, 22nd, 29th
    and then the 1st again — 2 to 4 days later depending on the month. There is no
    correct cron for "every N days" at N > 1, so only ``every == 1`` maps (to a
    plain daily), and the rest fall through to the caller's skip-and-explain path.

    An earlier version range-checked (``every < 60`` / ``< 24`` / ``< 32``) while
    the docstring claimed exactness, so an "every 45 minutes" periodic mirrored to
    something that fires twice as often. Nothing in integration hit it (15 divides
    60), but Beat schedules are per-environment DB rows that exist in no source
    file, so staging or production can carry one.
    """
    if task.crontab is not None:
        c = task.crontab
        return f"{c.minute} {c.hour} {c.day_of_month} {c.month_of_year} {c.day_of_week}"
    interval = task.interval
    if interval is None:
        return ""
    every = interval.every
    if every < 1:
        return ""
    if interval.period == IntervalSchedule.MINUTES and every < 60 and 60 % every == 0:
        return f"*/{every} * * * *"
    if interval.period == IntervalSchedule.HOURS and every < 24 and 24 % every == 0:
        return f"0 */{every} * * *"
    if interval.period == IntervalSchedule.DAYS and every == 1:
        return "0 0 * * *"
    # SECONDS, a step that does not divide its field, or anything else.
    return ""


def _decode(raw: str | None, fallback: Any) -> Any:
    """Beat stores args/kwargs as JSON text; decode once here so a malformed value
    fails at mirror time (visible, fixable) instead of at fire time (a periodic
    that silently stops running).
    """
    if not raw:
        return fallback
    return json.loads(raw)


class MirrorPlan(NamedTuple):
    """What to do with one Beat periodic: mirror it, or skip it and say why.

    Every decision this command makes lives here rather than inside the loop that
    talks to the database, so the rules can be tested against plain stand-ins
    instead of a live multi-tenant schema. The command becomes glue: plan, then
    apply.
    """

    name: str
    fields: dict[str, Any] | None  # None => skip
    skip_reason: str | None = None

    @property
    def should_mirror(self) -> bool:
        return self.fields is not None


def plan_mirror(task: Any) -> MirrorPlan:
    """Decide whether one Beat periodic can be mirrored, and with what fields.

    Accepts anything exposing the ``PeriodicTask`` attributes used here, so the
    rules are testable without the ORM.
    """
    if task.task in _EXCLUDED_TASK_PATHS:
        return MirrorPlan(
            task.name,
            None,
            f"{task.task} is owned elsewhere (pipeline mirror or Celery-internal)",
        )
    cron = cron_from_periodic_task(task)
    if not cron:
        return MirrorPlan(
            task.name,
            None,
            "schedule has no cron equivalent (second-resolution interval, solar "
            "or clocked) — it must stay on Beat or move to a different mechanism",
        )
    try:
        task_args = _decode(task.args, [])
        task_kwargs = _decode(task.kwargs, {})
    except ValueError as exc:
        return MirrorPlan(task.name, None, f"malformed args/kwargs JSON ({exc})")
    return MirrorPlan(
        task.name,
        {
            "task_name": task.task,
            # Beat falls back to the default queue when unset; mirror the same
            # fallback so the row targets where Beat would have.
            "queue": task.queue or "celery",
            "task_args": task_args,
            "task_kwargs": task_kwargs,
            "cron_string": cron,
            "enabled": task.enabled,
        },
    )


class Command(BaseCommand):
    help = (
        "Mirror non-pipeline Beat periodics into pg_periodic_task. Additive and "
        "inert by default; --adopt hands rows over to PG (and disables them in "
        "Beat) atomically, --release reverses it."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )
        parser.add_argument(
            "--adopt",
            nargs="*",
            metavar="NAME",
            help=(
                "Hand rows over to PG: set pg_owned=True and DISABLE the matching "
                "Beat PeriodicTask, atomically. Pass names to adopt those only, or "
                "no names to adopt every mirrored row."
            ),
        )
        parser.add_argument(
            "--release",
            nargs="*",
            metavar="NAME",
            help="Reverse of --adopt: pg_owned=False and re-enable the Beat task.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            metavar="N",
            help=(
                f"Rows fetched per DB round trip (default {DEFAULT_BATCH_SIZE}). "
                "Bounds memory on a large Beat table."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            metavar="N",
            help=(
                "Stop after mirroring N rows (0 = no limit). A safety valve for a "
                "first cautious run, NOT a resume cursor: the scan always starts "
                "from the beginning, so re-running with --limit re-visits the same "
                "rows. Drop it to mirror everything."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["adopt"] is not None and options["release"] is not None:
            raise CommandError("--adopt and --release are mutually exclusive")
        if options["batch_size"] < 1:
            raise CommandError("--batch-size must be >= 1")
        if options["limit"] < 0:
            raise CommandError("--limit must be >= 0")
        dry_run = options["dry_run"]
        mirrored, skipped = self._mirror(
            dry_run, batch_size=options["batch_size"], limit=options["limit"]
        )

        moved = 0
        if options["adopt"] is not None:
            moved = self._set_ownership(
                options["adopt"],
                to_pg=True,
                dry_run=dry_run,
                batch_size=options["batch_size"],
            )
        elif options["release"] is not None:
            moved = self._set_ownership(
                options["release"],
                to_pg=False,
                dry_run=dry_run,
                batch_size=options["batch_size"],
            )

        prefix = "[dry-run] " if dry_run else ""
        summary = (
            f"{prefix}mirrored={mirrored} skipped={skipped} ownership_changed={moved}"
        )
        if skipped:
            # Not fatal, but it means Beat is still the only firer for those — which
            # blocks scaling Beat to zero. Surface it where the operator looks.
            self.stderr.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _mirror(self, dry_run: bool, *, batch_size: int, limit: int) -> tuple[int, int]:
        """Apply :func:`plan_mirror` to every Beat periodic. Never changes ownership.

        Deliberately thin: every rule lives in ``plan_mirror``; this only reports and
        writes. A skip is loud because it means Beat remains the sole firer for that
        row, which is what blocks scaling Beat to zero.

        Scale: the excluded task paths are filtered **in SQL**, not in Python. There is
        one ``PeriodicTask`` row per scheduled pipeline, so matching them in Python
        would drag the entire pipeline population through memory only to discard it.
        ``.iterator()`` then bounds what is held at once. ``--limit`` caps a single
        run for a cautious first pass; it is not a resume cursor, since the upsert is
        idempotent and the scan always restarts from the beginning.
        """
        mirrored = skipped = 0
        # order_by(pk) makes the scan deterministic, so a --limit run and its
        # follow-ups walk the table in a stable order rather than re-treading rows.
        queryset = (
            PeriodicTask.objects.exclude(task__in=_EXCLUDED_TASK_PATHS)
            .select_related("crontab", "interval")
            .order_by("pk")
        )
        for task in queryset.iterator(chunk_size=batch_size):
            if limit and mirrored >= limit:
                self.stdout.write(
                    f"--limit {limit} reached; {queryset.count() - mirrored} row(s) "
                    "not visited. Re-run WITHOUT --limit to mirror everything "
                    "(the scan restarts from the beginning either way)."
                )
                break
            plan = plan_mirror(task)
            if not plan.should_mirror:
                # Excluded paths never reach here (filtered in SQL above), so every
                # skip is something an operator must resolve before Beat can go away.
                skipped += 1
                self.stderr.write(
                    self.style.WARNING(f"skipping {plan.name!r}: {plan.skip_reason}")
                )
                continue
            self.stdout.write(
                f"mirror {plan.name!r} task={plan.fields['task_name']} "
                f"queue={plan.fields['queue']!r} cron={plan.fields['cron_string']!r} "
                f"enabled={plan.fields['enabled']}"
            )
            if not dry_run:
                fields = dict(plan.fields)
                # `enabled` is the ONE mirrored field that stops tracking Beat once a
                # row is adopted: after --adopt Beat's copy is False by definition, so
                # re-mirroring would copy that back and leave pg_owned=True with
                # enabled=False — matching NEITHER firer (the PG tick selects
                # `WHERE pg_owned AND enabled`, Beat's row is disabled). The periodic
                # would stop silently, and the pre-migration value needed to release it
                # would be gone. Cron/args/queue still track Beat, so a schedule edit
                # made while PG owns the row is still picked up.
                if PgPeriodicTask.objects.filter(name=plan.name, pg_owned=True).exists():
                    fields.pop("enabled", None)
                PgPeriodicTask.objects.update_or_create(name=plan.name, defaults=fields)
            mirrored += 1
        return mirrored, skipped

    def _set_ownership(
        self, names: list[str], *, to_pg: bool, dry_run: bool, batch_size: int
    ) -> int:
        """Flip pg_owned and the matching Beat task's enabled flag together.

        One transaction per row: the two halves must not be separable, since the
        window between them is exactly the double-fire (or no-fire) window.
        """
        rows = PgPeriodicTask.objects.all().order_by("pk")
        if names:
            rows = rows.filter(name__in=names)
            missing = set(names) - set(rows.values_list("name", flat=True))
            if missing:
                raise CommandError(
                    f"no mirror row for: {', '.join(sorted(missing))} "
                    f"(run without --adopt/--release first to mirror them)"
                )
        changed = 0
        # Deliberately NOT limited by --limit: an ownership flip is the operator's
        # explicit, named intent, and stopping half way would leave some rows on PG
        # and some on Beat with no record of where the boundary fell. It is chunked
        # only to bound memory. In practice this table holds a handful of rows.
        for row in rows.iterator(chunk_size=batch_size):
            if row.pg_owned == to_pg:
                continue
            # RESTORE, don't blanket-enable. On release this used to write
            # `enabled=True` unconditionally, which RESURRECTS a periodic an operator
            # had deliberately switched off in Beat before the migration — a rollback
            # is supposed to restore the previous state, not invent a new one.
            # `row.enabled` is Beat's own value, captured by the mirror (plan_mirror
            # copies task.enabled), so a row that was off mirrors off, is adopted off,
            # and is released off. On adopt the answer is always False: PG owns it.
            beat_enabled = False if to_pg else row.enabled
            verb = "adopt" if to_pg else "release"
            self.stdout.write(f"{verb} {row.name!r} (beat enabled -> {beat_enabled})")
            if not dry_run:
                with transaction.atomic():
                    row.pg_owned = to_pg
                    # Clear the baseline on release so a later re-adopt records a
                    # fresh next_run_at instead of firing immediately for a
                    # next_run_at that went stale while Beat owned the schedule.
                    if not to_pg:
                        row.next_run_at = None
                    row.save(update_fields=["pg_owned", "next_run_at", "updated_at"])
                    beat_updates: dict = {"enabled": beat_enabled}
                    # Baseline Beat's clock on release, the mirror of clearing
                    # next_run_at above. DatabaseScheduler derives due-ness from
                    # PeriodicTask.last_run_at against the crontab, so a periodic that
                    # spent days PG-owned is overdue by every interval it missed and
                    # Beat replays them the moment `enabled` flips back. Seen on
                    # integration 2026-08-24: all three dashboard_metrics.* fired
                    # inside 30 ms of the release, alongside four pipelines.
                    #
                    # Release-only: on adopt Beat is being switched OFF, so its clock
                    # is irrelevant, and touching it would corrupt the value a later
                    # release needs to restore.
                    if not to_pg:
                        beat_updates["last_run_at"] = timezone.now()
                    matched = PeriodicTask.objects.filter(name=row.name).update(
                        **beat_updates
                    )
                    if not matched and not to_pg:
                        # Release only. A bulk .update() returning 0 is indistinguishable
                        # from success, and on release it means a periodic PG has let go
                        # of that Beat cannot pick up — no firer at all, on the rollback
                        # path. On ADOPT a missing Beat row just means there was nothing
                        # to disable, which is benign; warning on both is how the real
                        # one gets ignored.
                        self.stderr.write(
                            f"WARNING: no Beat PeriodicTask named {row.name!r} to "
                            f"release to — it may now have no firer"
                        )
                    # Bulk .update() bypasses django-celery-beat's post_save signal,
                    # so PeriodicTasks.last_update never bumps and DatabaseScheduler
                    # never reloads. Without this, --adopt would set pg_owned=True and
                    # flip the DB row to disabled while Beat kept firing it from its
                    # stale in-memory copy — a DOUBLE FIRE, precisely what doing both
                    # halves in one transaction exists to prevent. --release has the
                    # mirror failure: Beat would never resume. Same fix and same
                    # reason as scheduler/ownership.py:132 on the pipeline path.
                    PeriodicTasks.update_changed()
            changed += 1
        return changed
