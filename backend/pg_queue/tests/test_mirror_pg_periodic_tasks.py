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
            (2, HOURS, "0 */2 * * *"),
            (3, DAYS, "0 0 */3 * *"),
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
        row = SimpleNamespace(name="h", pg_owned=(flag == "--release"), next_run_at=None)
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
