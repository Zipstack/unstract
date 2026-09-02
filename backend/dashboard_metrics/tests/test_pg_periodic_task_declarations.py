"""Drift guard between the Beat and PG declarations of the metrics periodics (UN-3796).

Every schedule in this app is declared twice — once in
``django_celery_beat_periodictask`` for Celery Beat, once in ``pg_periodic_task`` for the
PG scheduler. They are separate rows in separate tables, so nothing stops someone editing
one and forgetting the other. That is the whole failure mode this file exists for: a
schedule changed on Beat but not on PG means the task silently runs on a different cadence
— or not at all — the moment the flag flips.

**Every data migration in the app is replayed**, not a named pair. Naming modules is how
the guard went stale before: a schedule added in a later migration kept comparing the
original three against three and stayed green while the invariant it names was violated.
Migrations are run in order against fake models, so rows a later migration rewrites are
compared in their final state.

DB-free — nothing here touches a database.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.db import migrations

from dashboard_metrics.tasks import (
    aggregate_metrics_from_sources,
    cleanup_daily_metrics,
    cleanup_hourly_metrics,
)

_MIGRATIONS_PKG = "dashboard_metrics.migrations"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Cron equivalent of each schedule, written out rather than derived: an anchor that a
# reviewer reads, and that an edit to both declarations at once still has to touch.
_EXPECTED_CRON = {
    "dashboard_metrics_aggregate_from_sources": "*/15 * * * *",
    "dashboard_metrics_cleanup_hourly": "0 2 * * *",
    "dashboard_metrics_cleanup_daily": "0 3 * * 0",
    "dashboard_metrics_reconcile_source_window": "40 4 * * *",
}


class _Schedule:
    """Stands in for an Interval/CrontabSchedule row, carrying its own cron string."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @property
    def cron_string(self) -> str:
        k = self.kwargs
        if "period" in k:
            every, period = k["every"], k["period"]
            if period == "minutes":
                return f"*/{every} * * * *"
            if period == "hours":
                return f"0 */{every} * * *"
            raise AssertionError(f"unhandled interval period: {period}")
        return " ".join(
            str(k[f])
            for f in ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")
        )


class _Rows:
    """Captures a migration's writes to one model without a database."""

    def __init__(self, factory=None):
        self.rows: dict[str, dict] = {}
        self.writes = 0
        self._factory = factory
        self._selected: list[str] = []

    def get_or_create(self, **kwargs):
        kwargs.pop("defaults", None)
        return (self._factory(**kwargs) if self._factory else kwargs), True

    def update_or_create(self, name=None, defaults=None, **kwargs):
        self.writes += 1
        if name is None:  # e.g. PeriodicTasks(ident=1) — not a schedule row
            return defaults, True
        self.rows.setdefault(name, {}).update(defaults or {})
        return self.rows[name], True

    def filter(self, name=None, name__in=None, **_kwargs):
        self._selected = [name] if name is not None else list(name__in or [])
        return self

    def update(self, **kwargs):
        self.writes += 1
        for name in self._selected:
            self.rows.setdefault(name, {}).update(kwargs)
        return len(self._selected)

    def delete(self):
        self.writes += 1
        for name in self._selected:
            self.rows.pop(name, None)
        return (0, {})


class _Apps:
    def __init__(self):
        self.beat = _Rows()
        self.pg = _Rows()
        self.schedules = _Rows(factory=_Schedule)
        self.tracker = _Rows()
        self.other = _Rows()

    def get_model(self, app_label, model_name):
        target = {
            ("django_celery_beat", "PeriodicTask"): self.beat,
            ("pg_queue", "PgPeriodicTask"): self.pg,
            ("django_celery_beat", "CrontabSchedule"): self.schedules,
            ("django_celery_beat", "IntervalSchedule"): self.schedules,
            ("django_celery_beat", "PeriodicTasks"): self.tracker,
        }.get((app_label, model_name), self.other)
        return type("_M", (), {"objects": target})


def _migration_modules() -> list[str]:
    names = sorted(
        p.stem for p in _MIGRATIONS_DIR.glob("*.py") if re.match(r"^\d{4}_", p.stem)
    )
    assert names, "no migrations discovered — the glob is wrong, not the app"
    return [f"{_MIGRATIONS_PKG}.{name}" for name in names]


@pytest.fixture(scope="module")
def declared() -> SimpleNamespace:
    """Replay every data migration in order and capture what it declares."""
    apps = _Apps()
    for dotted in _migration_modules():
        for op in importlib.import_module(dotted).Migration.operations:
            if isinstance(op, migrations.RunPython):
                op.code(apps, None)
    return SimpleNamespace(beat=apps.beat.rows, pg=apps.pg.rows)


def _beat_cron(row: dict) -> str:
    schedule = row.get("crontab") or row.get("interval")
    assert schedule is not None, "Beat row declares neither a crontab nor an interval"
    return schedule.cron_string


class TestDeclarationsAgree:
    def test_same_set_of_schedules(self, declared):
        # A schedule added to Beat but not PG stops firing the moment the flag flips;
        # the reverse fires something Beat never knew about.
        assert set(declared.beat) == set(declared.pg)

    def test_every_known_schedule_is_declared(self, declared):
        # Guards the guard: a replay that silently captured nothing would pass the
        # set comparison above with two empty sets.
        assert set(declared.beat) == set(_EXPECTED_CRON)

    def test_task_path_and_queue_match(self, declared):
        for name, beat in declared.beat.items():
            assert declared.pg[name]["task_name"] == beat["task"], name
            assert declared.pg[name]["queue"] == beat["queue"], name

    def test_kwargs_match_once_decoded(self, declared):
        # Beat stores kwargs as a JSON *string*; PgPeriodicTask.task_kwargs is a
        # JSONField. A mismatch means the task runs with the wrong arguments.
        for name, beat in declared.beat.items():
            assert declared.pg[name]["task_kwargs"] == json.loads(
                beat.get("kwargs") or "{}"
            ), name

    def test_cadence_matches_across_transports(self, declared):
        # Derived from the Beat schedule row rather than from a table, so a cadence
        # changed on one transport only fails here whatever its name.
        for name, beat in declared.beat.items():
            assert declared.pg[name]["cron_string"] == _beat_cron(beat), name

    def test_cadence_matches_the_written_anchor(self, declared):
        for name, cron in _EXPECTED_CRON.items():
            assert declared.pg[name]["cron_string"] == cron


# 0002 seeds at install time, when Beat has never started and has nothing stale to
# reload. Every migration after it rewrites a schedule a running Beat already holds.
_INSTALL_MIGRATION = "0002_setup_periodic_tasks"


class TestRunningBeatIsToldToReload:
    """Historical models fire no post_save, so DatabaseScheduler never reloads.

    Without an explicit ``PeriodicTasks.last_update`` bump a live Beat keeps firing its
    in-memory copy: rows this migration adds never fire, rows it rewrites keep their old
    arguments. Nothing errors, and the whole change silently does not happen.
    """

    def test_every_post_install_beat_write_bumps_the_change_tracker(self):
        checked = 0
        for dotted in _migration_modules():
            if dotted.endswith(_INSTALL_MIGRATION):
                continue
            for op in importlib.import_module(dotted).Migration.operations:
                if not isinstance(op, migrations.RunPython):
                    continue
                for direction in (op.code, op.reverse_code):
                    if direction is None:
                        continue
                    apps = _Apps()
                    direction(apps, None)
                    if not apps.beat.writes:
                        continue
                    checked += 1
                    assert apps.tracker.writes, f"{dotted}.{direction.__name__}"
        assert checked, "no post-install Beat writes found — the discovery is broken"


class TestDeclaredKwargsAreCallable:
    """A schedule row carrying a kwarg its task cannot bind raises TypeError per tick.

    TypeError is not in ``autoretry_for``, and the PG leg drops the message at
    MAX_ATTEMPTS=1 — so the schedule silently never runs. Enumerating every declared
    row rather than one migration's own spec is the point: the rows are added by
    different migrations, and each new one is exactly the case that escapes a guard
    scoped to a single module.
    """

    _TASKS = {
        task.name: task
        for task in (
            aggregate_metrics_from_sources,
            cleanup_hourly_metrics,
            cleanup_daily_metrics,
        )
    }

    def test_every_declared_kwarg_set_binds_to_the_task_signature(self, declared):
        for name, row in declared.pg.items():
            task = self._TASKS.get(row["task_name"])
            assert task is not None, f"{name} schedules an unknown task"
            inspect.signature(task).bind(**row["task_kwargs"])


class TestSeededInert:
    """Applying the migrations must not cause anything to fire."""

    def test_nothing_is_declared_pg_owned(self, declared):
        # pg_owned=True would hand the row to the PG scheduler before the rollout
        # flag decides, and disable its Beat twin.
        assert not any(row.get("pg_owned") for row in declared.pg.values())

    def test_no_row_presets_a_run_time(self, declared):
        # A non-NULL next_run_at in the past reads as "overdue" and fires a burst of
        # catch-up runs the moment the flag is enabled.
        for row in declared.pg.values():
            assert "next_run_at" not in row
            assert "last_run_at" not in row
