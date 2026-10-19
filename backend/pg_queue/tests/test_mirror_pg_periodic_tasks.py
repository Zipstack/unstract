"""Unit tests for the non-pipeline Beat mirror (UN-3796).

DB-free by construction: every decision lives in ``plan_mirror`` /
``cron_from_periodic_task``, which take anything shaped like a ``PeriodicTask``.
That matters here — no backend DB-bound test currently runs in this repo (the
multi-tenant schema isn't created for the test database, and pytest is not wired
into CI for backend at all), so a test written against the ORM would look like
coverage while never executing.

What's worth pinning is the exclusions (what must NOT be mirrored, and why) and the
cron conversion (where a wrong answer silently changes how often a job runs).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from pg_queue.management.commands.mirror_pg_periodic_tasks import (
    cron_from_periodic_task,
    plan_mirror,
)

# django_celery_beat's IntervalSchedule period values are plain strings.
SECONDS, MINUTES, HOURS, DAYS = "seconds", "minutes", "hours", "days"


def _crontab(minute="0", hour="2", dom="*", moy="*", dow="*"):
    return SimpleNamespace(
        minute=minute, hour=hour, day_of_month=dom, month_of_year=moy, day_of_week=dow
    )


# Sentinel so an explicit `crontab=None` (a solar/clocked periodic) is
# distinguishable from "caller didn't say", which defaults to a plain crontab.
_UNSET = object()


def _task(
    name="t",
    task="some.task",
    queue="q",
    args="[]",
    kwargs="{}",
    enabled=True,
    crontab=_UNSET,
    interval=None,
):
    if crontab is _UNSET:
        crontab = None if interval else _crontab()
    return SimpleNamespace(
        name=name,
        task=task,
        queue=queue,
        args=args,
        kwargs=kwargs,
        enabled=enabled,
        crontab=crontab,
        interval=interval,
    )


def _interval(every, period):
    return SimpleNamespace(every=every, period=period)


class TestCronConversion:
    def test_crontab_is_reconstructed_field_for_field(self):
        assert cron_from_periodic_task(_task(crontab=_crontab("30", "4"))) == "30 4 * * *"

    @pytest.mark.parametrize(
        "every,period,expected",
        [
            (15, MINUTES, "*/15 * * * *"),  # dashboard_metrics.aggregate_from_sources
            (1, MINUTES, "*/1 * * * *"),
            (30, MINUTES, "*/30 * * * *"),
            (2, HOURS, "0 */2 * * *"),
            (12, HOURS, "0 */12 * * *"),
            # every==1 day is the ONLY expressible day interval; emitted as a plain
            # daily rather than `*/1` so the stored cron says what it means.
            (1, DAYS, "0 0 * * *"),
        ],
    )
    def test_interval_maps_to_an_exact_step_cron(self, every, period, expected):
        assert cron_from_periodic_task(_task(interval=_interval(every, period))) == expected

    def test_second_resolution_interval_is_refused_not_approximated(self):
        # The important negative: cron has no sub-minute field. Rounding a
        # 30-second periodic up to a minute would silently halve how often it runs,
        # so it must be refused. This is the real `workflow_log_history_v2` shape.
        assert cron_from_periodic_task(_task(interval=_interval(30, SECONDS))) == ""

    @pytest.mark.parametrize(
        "every,period", [(90, MINUTES), (36, HOURS), (40, DAYS), (0, MINUTES)]
    )
    def test_step_too_large_for_one_field_is_refused(self, every, period):
        # `*/90` in a 0-59 minute field does not mean "every 90 minutes".
        assert cron_from_periodic_task(_task(interval=_interval(every, period))) == ""

    @pytest.mark.parametrize(
        "every,period,fires_instead",
        [
            (7, MINUTES, ":00 :07 … :56 then :00 — a 4-minute gap, not 7"),
            (45, MINUTES, ":00 :45 then :00 — roughly twice as often"),
            (8, MINUTES, ":00 :08 … :56 then :00 — a 4-minute gap"),
            (25, MINUTES, ":00 :25 :50 then :00 — a 10-minute gap"),
            (5, HOURS, "0 5 10 15 20 then 0 — a 4-hour gap, not 5"),
            (7, HOURS, "0 7 14 21 then 0 — a 3-hour gap"),
            (9, HOURS, "0 9 18 then 0 — a 6-hour gap"),
        ],
    )
    def test_an_interval_that_does_not_divide_its_field_is_refused(
        self, every, period, fires_instead
    ):
        """`*/N` restarts at each field boundary, so it is only "every N" when N
        divides the range. The old code range-checked (`every < 60` / `< 24`) while
        the docstring claimed exactness, so these mirrored to a cron that fires at
        the wrong rate — silently, and only at the boundary.

        Refusing sends them down plan_mirror's skip-and-explain path, which is what
        already happens for second-resolution intervals: they stay on Beat, visibly,
        instead of being adopted at a frequency nobody chose.
        """
        assert cron_from_periodic_task(_task(interval=_interval(every, period))) == "", (
            f"every {every} {period} must be refused — `*/{every}` fires {fires_instead}"
        )

    @pytest.mark.parametrize("every", [2, 3, 7, 15, 31])
    def test_multi_day_intervals_are_refused_because_months_vary(self, every):
        """`0 0 */N * *` restarts every month and months are 28-31 days, so the
        boundary gap depends on the month and the year. `0 0 */7 * *` fires on the
        1st, 8th, 15th, 22nd, 29th, then the 1st again — 2 to 4 days later. There is
        no correct cron for "every N days" at N > 1, so only every==1 is expressible.
        """
        assert cron_from_periodic_task(_task(interval=_interval(every, DAYS))) == ""

    def test_no_schedule_at_all_is_refused(self):
        # solar/clocked periodics have neither crontab nor interval.
        assert cron_from_periodic_task(_task(crontab=None, interval=None)) == ""


class TestPlanMirror:
    def test_mirrors_with_its_own_queue_and_decoded_kwargs(self):
        plan = plan_mirror(
            _task(
                name="dashboard_metrics_cleanup_hourly",
                task="dashboard_metrics.cleanup_hourly_data",
                queue="dashboard_metric_events",
                kwargs=json.dumps({"retention_days": 30}),
            )
        )
        assert plan.should_mirror
        # Each periodic carries its OWN target queue — the whole reason this can't
        # reuse the pipeline scheduler, which enqueues onto one fixed queue.
        assert plan.fields["queue"] == "dashboard_metric_events"
        assert plan.fields["task_kwargs"] == {"retention_days": 30}
        assert plan.fields["cron_string"] == "0 2 * * *"

    @pytest.mark.parametrize(
        "task_path",
        [
            "scheduler.tasks.execute_pipeline_task",
            # A real Beat table was found carrying this legacy path; excluding by
            # name convention alone would have let it through into a second owner.
            "execute_pipeline_task_v2",
            # Celery's own result-backend housekeeping — nothing registers it on PG,
            # and what it cleans stops existing once Celery is off.
            "celery.backend_cleanup",
        ],
    )
    def test_excluded_task_paths_are_never_mirrored(self, task_path):
        plan = plan_mirror(_task(task=task_path))
        assert not plan.should_mirror
        assert "owned elsewhere" in plan.skip_reason

    def test_uncronnable_schedule_is_skipped_with_a_reason(self):
        plan = plan_mirror(_task(interval=_interval(30, SECONDS)))
        assert not plan.should_mirror
        assert "no cron equivalent" in plan.skip_reason

    def test_malformed_args_is_skipped_rather_than_mirrored_empty(self):
        # Beat stores args as JSON text, but a hand-edited row can hold a Python
        # repr (a real one was found). Defaulting to [] would fire the task with the
        # wrong arguments — silently, forever.
        plan = plan_mirror(_task(args="['not', 'json']"))
        assert not plan.should_mirror
        assert "malformed" in plan.skip_reason

    def test_missing_queue_falls_back_the_way_beat_does(self):
        assert plan_mirror(_task(queue=None)).fields["queue"] == "celery"

    def test_empty_args_and_kwargs_decode_to_empty_containers(self):
        fields = plan_mirror(_task(args="", kwargs=None)).fields
        assert fields["task_args"] == [] and fields["task_kwargs"] == {}

    def test_disabled_state_is_carried_across(self):
        # A row disabled in Beat must mirror as disabled, or adopting it would start
        # running something an operator had deliberately turned off.
        assert plan_mirror(_task(enabled=False)).fields["enabled"] is False


class TestBeatReloadSignal:
    """A hand-over must tell Beat to reload, or the atomicity is worthless.

    `PeriodicTask.objects.filter(...).update(...)` is a bulk update: it bypasses
    django-celery-beat's post_save signal, so `PeriodicTasks.last_update` never bumps
    and `DatabaseScheduler` keeps running from its stale in-memory copy. The DB would
    say "disabled" while Beat carried on firing — a double fire alongside the PG
    scheduler, which is the exact failure doing both halves in one transaction exists
    to prevent. `--release` fails the mirror way: Beat never resumes.

    Pinned here because the symptom is invisible in the DB — you only see it in
    duplicated side effects.
    """

    _CMD = "pg_queue.management.commands.mirror_pg_periodic_tasks"

    def _run(self, flag):
        # `enabled` mirrors Beat's value and is what --release restores; a real
        # PgPeriodicTask always has it, so the stand-in must too.
        row = SimpleNamespace(
            name="h", pg_owned=(flag == "--release"), next_run_at=None, enabled=True
        )
        with (
            patch(f"{self._CMD}.PgPeriodicTask") as Model,
            patch(f"{self._CMD}.PeriodicTask") as Beat,
            patch(f"{self._CMD}.PeriodicTasks") as BeatSignal,
            patch(f"{self._CMD}.transaction.atomic"),
        ):
            qs = MagicMock()
            qs.iterator.return_value = [row]
            qs.values_list.return_value = ["h"]
            qs.filter.return_value = qs
            Model.objects.all.return_value.order_by.return_value = qs
            # No Beat rows to mirror; we only exercise the ownership flip.
            Beat.objects.exclude.return_value.select_related.return_value.order_by.return_value.iterator.return_value = []
            row.save = MagicMock()
            call_command("mirror_pg_periodic_tasks", flag)
            return Beat, BeatSignal

    @pytest.mark.parametrize("flag", ["--adopt", "--release"])
    def test_ownership_flip_bumps_the_beat_reload_signal(self, flag):
        Beat, BeatSignal = self._run(flag)
        Beat.objects.filter.return_value.update.assert_called_once()
        BeatSignal.update_changed.assert_called_once()


class TestReleaseRestoresRatherThanResurrects:
    """A rollback restores the previous state; it must not invent a new one.

    `--release` wrote `enabled=True` unconditionally, so a periodic an operator had
    deliberately switched OFF in Beat before the migration came back **on** after a
    rollback — silently re-arming a job someone had stopped on purpose. The
    pre-migration value is already recorded: `plan_mirror` copies `task.enabled` into
    the mirror row, so `row.enabled` is Beat's own value.
    """

    _CMD = "pg_queue.management.commands.mirror_pg_periodic_tasks"

    def _flip(self, flag: str, mirrored_enabled: bool = True):
        row = SimpleNamespace(
            name="h",
            pg_owned=(flag == "--release"),
            next_run_at=None,
            enabled=mirrored_enabled,
        )
        with (
            patch(f"{self._CMD}.PgPeriodicTask") as Model,
            patch(f"{self._CMD}.PeriodicTask") as Beat,
            patch(f"{self._CMD}.PeriodicTasks"),
            patch(f"{self._CMD}.transaction.atomic"),
        ):
            qs = MagicMock()
            qs.iterator.return_value = [row]
            qs.values_list.return_value = ["h"]
            qs.filter.return_value = qs
            Model.objects.all.return_value.order_by.return_value = qs
            Beat.objects.exclude.return_value.select_related.return_value.order_by.return_value.iterator.return_value = []
            row.save = MagicMock()
            call_command("mirror_pg_periodic_tasks", flag)
            return Beat.objects.filter.return_value.update.call_args.kwargs

    def _release(self, mirrored_enabled: bool):
        return self._flip("--release", mirrored_enabled)

    def test_a_row_that_was_enabled_is_restored_enabled(self):
        assert self._release(mirrored_enabled=True)["enabled"] is True

    def test_a_row_that_was_DISABLED_stays_disabled(self):
        # The regression: blanket `enabled=True` re-armed a job someone stopped.
        assert self._release(mirrored_enabled=False)["enabled"] is False


class TestReleaseBaselinesBeatsClock:
    """Release must reset Beat's clock, or Beat replays every missed interval.

    DatabaseScheduler keeps no next_run_at — it derives due-ness from
    ``PeriodicTask.last_run_at`` against the crontab. A periodic that spent days
    PG-owned still carries the last_run_at from before the hand-over, so the moment
    ``enabled`` flips back it is overdue by every interval it missed and Beat fires
    them all at once.

    Observed on integration 2026-08-24: releasing the fleet fired all three
    ``dashboard_metrics.*`` plus four pipelines within 30 ms of "Released to Beat".
    This is the exact mirror of the next_run_at baseline on the adopt side
    (``scheduler/ownership.py``, OSS 2088d6962) — that half was fixed, this one was
    not, and a comment there wrongly claimed Beat does not catch up.

    These assertions previously read ``== {"enabled": ...}`` on the whole kwargs dict.
    Changed deliberately, not loosened: the write now carries a second key, and the
    per-key assertions below plus the two new cases pin strictly more than the exact
    dict did.
    """

    _CMD = "pg_queue.management.commands.mirror_pg_periodic_tasks"

    def _flip(self, flag: str):
        return TestReleaseRestoresRatherThanResurrects()._flip(flag)

    def test_release_stamps_last_run_at(self):
        kwargs = self._flip("--release")
        assert "last_run_at" in kwargs, (
            "release must baseline Beat's clock; without it DatabaseScheduler sees "
            "every missed interval as overdue and replays them"
        )
        assert kwargs["last_run_at"] is not None

    def test_adopt_does_NOT_touch_last_run_at(self):
        """On adopt Beat is being switched OFF, so its clock is irrelevant — and
        overwriting it would destroy the value a later release needs to restore."""
        assert "last_run_at" not in self._flip("--adopt")


class TestMirrorDoesNotClobberAnAdoptedRow:
    """Re-mirroring after adoption must not strand the row with no firer.

    `enabled` is the one mirrored field that stops tracking Beat once PG owns the row:
    after `--adopt`, Beat's copy is False *by definition*. Copying that back leaves
    `pg_owned=True, enabled=False`, which matches NEITHER firer — the PG tick selects
    `WHERE pg_owned AND enabled`, and Beat's row is disabled. The periodic stops
    silently, and the value needed to release it correctly is gone.
    """

    _CMD = "pg_queue.management.commands.mirror_pg_periodic_tasks"

    def _mirror_with(self, already_adopted: bool):
        beat_row = _task(name="h", enabled=False, crontab=_crontab())
        with (
            patch(f"{self._CMD}.PgPeriodicTask") as Model,
            patch(f"{self._CMD}.PeriodicTask") as Beat,
            patch(f"{self._CMD}.PeriodicTasks"),
        ):
            Beat.objects.exclude.return_value.select_related.return_value.order_by.return_value.iterator.return_value = [
                beat_row
            ]
            Model.objects.filter.return_value.exists.return_value = already_adopted
            call_command("mirror_pg_periodic_tasks")
            return Model.objects.update_or_create.call_args.kwargs["defaults"]

    def test_an_adopted_row_keeps_its_own_enabled(self):
        assert "enabled" not in self._mirror_with(already_adopted=True)

    def test_a_beat_owned_row_still_tracks_beat(self):
        # The normal path must keep mirroring enabled, or a pause in Beat is missed.
        assert self._mirror_with(already_adopted=False)["enabled"] is False

    def test_cron_still_tracks_beat_even_when_adopted(self):
        # Only `enabled` diverges — a schedule edit made while PG owns it must land.
        assert "cron_string" in self._mirror_with(already_adopted=True)
