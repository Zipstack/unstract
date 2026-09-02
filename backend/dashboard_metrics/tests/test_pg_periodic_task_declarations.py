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

``0006_split_aggregation_schedule`` then splits the aggregation into two rows by tier.
It writes both scheduler tables from one spec, so the new row cannot drift by
construction — but it also rewrites an existing row, and *how* it does that is
load-bearing. The last sections cover that, the ownership it inherits, and the rollback.

DB-free — nothing here touches a database.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.db import migrations  # noqa: E402

from dashboard_metrics.tasks import (  # noqa: E402
    AggregationTier,
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
    # Added by 0006; off the */15 grid so it never starts alongside the hourly tier.
    "dashboard_metrics_aggregate_daily_monthly": "20 * * * *",
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

    def first(self):
        """The row a migration reads back, e.g. to inherit scheduler ownership."""
        name = self._selected[0] if self._selected else None
        if name not in self.rows:
            return None
        return SimpleNamespace(**{"enabled": True, "pg_owned": False, **self.rows[name]})

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


_SPLIT_MIGRATION = "dashboard_metrics.migrations.0006_split_aggregation_schedule"
_NEW_ROW = "dashboard_metrics_aggregate_daily_monthly"
_EXISTING_ROW = "dashboard_metrics_aggregate_from_sources"


class _SplitRecorder:
    """Captures what 0006 does to one scheduler table, keeping creates and updates apart.

    The distinction is the point: creating a row writes every default, updating one writes
    only the named fields. Conflating them is exactly the bug this guards.
    """

    def __init__(self, existing: Any = None) -> None:
        self.created: dict[str, dict[str, Any]] = {}
        self.updated: dict[str, dict[str, Any]] = {}
        self.deleted: list[str] = []
        self.bumps = 0
        # How many rows a filtered update matches. 0 models the row being absent,
        # which is the case the migration now refuses to report as success.
        self.rows_present: int | None = None
        self._existing = existing
        self._filtered_on: str = ""
        self._filtered_in: list[str] = []

    def filter(
        self, name: str = "", name__in: list[str] | None = None, **_kw: Any
    ) -> _SplitRecorder:
        self._filtered_on = name
        self._filtered_in = list(name__in or [])
        return self

    def first(self) -> Any:
        return self._existing

    def update(self, **kwargs: Any) -> int:
        self.updated[self._filtered_on] = kwargs
        return 1 if self.rows_present is None else self.rows_present

    def update_or_create(
        self, name: str = "", defaults: dict[str, Any] | None = None, **_kw: Any
    ) -> tuple[dict[str, Any], bool]:
        if not name:  # PeriodicTasks(ident=1) — the Beat reload tracker
            self.bumps += 1
            return defaults or {}, True
        self.created[name] = defaults or {}
        return self.created[name], True

    def get_or_create(self, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        return kwargs, True

    def delete(self) -> tuple[int, dict[str, Any]]:
        self.deleted.extend(self._filtered_in or [self._filtered_on])
        return (len(self.deleted), {})


def _run_split(beat_row: Any = None, pg_row: Any = None) -> dict[str, _SplitRecorder]:
    """Run 0006's forward function against fakes and capture every table it writes."""
    mod = importlib.import_module(_SPLIT_MIGRATION)
    beat = _SplitRecorder(existing=beat_row)
    pg = _SplitRecorder(existing=pg_row)
    crontab, tracker = _SplitRecorder(), _SplitRecorder()

    class _Apps:
        def get_model(self, _app: str, model: str) -> type:
            table = {
                "PeriodicTask": beat,
                "PgPeriodicTask": pg,
                "PeriodicTasks": tracker,
            }.get(model, crontab)
            return type("M", (), {"objects": table})

    mod.split_schedules(_Apps(), None)
    return {"beat": beat, "pg": pg, "tracker": tracker}


@pytest.fixture(scope="module")
def split() -> dict[str, _SplitRecorder]:
    """The default case: a Beat-owned row, as every environment ships today."""
    return _run_split(
        beat_row=SimpleNamespace(enabled=True),
        pg_row=SimpleNamespace(enabled=True, pg_owned=False),
    )


class TestTheSplitAddsOneRowAndRewritesOne:
    def test_only_the_daily_monthly_row_is_created(self, split: dict[str, _SplitRecorder]) -> None:
        for table in ("beat", "pg"):
            assert set(split[table].created) == {_NEW_ROW}

    def test_only_the_existing_aggregate_row_is_updated(self, split: dict[str, _SplitRecorder]) -> None:
        for table in ("beat", "pg"):
            assert set(split[table].updated) == {_EXISTING_ROW}

    def test_the_new_row_is_declared_the_same_on_both_tables(self, split: dict[str, _SplitRecorder]) -> None:
        beat, pg = split["beat"].created[_NEW_ROW], split["pg"].created[_NEW_ROW]
        assert pg["task_name"] == beat["task"]
        assert pg["queue"] == beat["queue"]
        assert pg["task_kwargs"] == json.loads(beat["kwargs"])

    def test_the_new_row_runs_hourly_on_both_tables(self, split: dict[str, _SplitRecorder]) -> None:
        assert split["pg"].created[_NEW_ROW]["cron_string"] == "20 * * * *"
        crontab = split["beat"].created[_NEW_ROW]["crontab"]
        assert (crontab["minute"], crontab["hour"]) == ("20", "*")

    def test_the_two_rows_never_start_together(self, split: dict[str, _SplitRecorder]) -> None:
        """The per-tier locks are built so the two runs cannot block each other, so a
        shared minute is two full prefilter scans and two per-org loops at once — on a
        change whose object is flattening cron load.
        """
        fires_at = {0, 15, 30, 45}  # the existing row's */15
        minute = int(split["beat"].created[_NEW_ROW]["crontab"]["minute"])
        assert minute not in fires_at

    def test_the_new_row_is_seeded_inert_on_the_pg_side(self, split: dict[str, _SplitRecorder]) -> None:
        """Same reason as 0004's rows: a PG row that is pg_owned before the scheduler
        has adopted it would fire alongside its Beat twin.
        """
        assert split["pg"].created[_NEW_ROW]["pg_owned"] is False

    def test_the_rewritten_row_carries_the_same_kwargs_on_both_tables(
        self, split: dict[str, _SplitRecorder]
    ) -> None:
        """The row firing the hourly tier every 15 minutes in production.

        Beat's ``kwargs`` is a TextField it parses with ``json.loads``; writing the
        mapping rather than its JSON encoding stores a Python repr, ``ModelEntry``
        raises, and the hourly aggregation silently stops firing.
        """
        beat = split["beat"].updated[_EXISTING_ROW]
        assert json.loads(beat["kwargs"]) == split["pg"].updated[_EXISTING_ROW][
            "task_kwargs"
        ]

    def test_the_two_rows_ask_for_different_tiers(self, split: dict[str, _SplitRecorder]) -> None:
        new = split["pg"].created[_NEW_ROW]["task_kwargs"]["tier"]
        existing = split["pg"].updated[_EXISTING_ROW]["task_kwargs"]["tier"]
        assert new != existing


class TestTheNewRowInheritsWhoeverFiresTheRowItSplitsFrom:
    """Hardcoding Beat leaves the daily/monthly tier with no firer in a PG-adopted
    environment: the adopted row's Beat twin is disabled and Beat may be scaled to
    zero, so the sole writer of those figures never runs and the hourly run still
    reports success.
    """

    def test_a_pg_adopted_row_hands_its_new_half_to_the_pg_scheduler(self) -> None:
        split = _run_split(
            beat_row=SimpleNamespace(enabled=False),
            pg_row=SimpleNamespace(enabled=True, pg_owned=True),
        )
        assert split["pg"].created[_NEW_ROW]["pg_owned"] is True
        assert split["pg"].created[_NEW_ROW]["enabled"] is True
        assert split["beat"].created[_NEW_ROW]["enabled"] is False

    def test_a_disabled_row_does_not_come_back_as_an_enabled_half(self) -> None:
        split = _run_split(
            beat_row=SimpleNamespace(enabled=False),
            pg_row=SimpleNamespace(enabled=False, pg_owned=False),
        )
        assert split["beat"].created[_NEW_ROW]["enabled"] is False
        assert split["pg"].created[_NEW_ROW]["enabled"] is False

    def test_a_missing_row_falls_back_to_beat(self) -> None:
        """A fresh install applies 0002/0004 first, so this is defensive only."""
        split = _run_split(beat_row=None, pg_row=None)
        assert split["beat"].created[_NEW_ROW]["enabled"] is True
        assert split["pg"].created[_NEW_ROW]["pg_owned"] is False


class TestARunningBeatIsToldToReload:
    """Historical models fire no post_save, so DatabaseScheduler never reloads.

    Without an explicit bump the existing row keeps firing with no tier and the new
    row never fires at all — no error, nothing logged, and the whole saving silently
    does not happen.
    """

    def test_the_forward_direction_bumps_the_change_tracker(self, split) -> None:
        assert split["tracker"].bumps == 1

    def test_the_reverse_direction_bumps_it_too(self) -> None:
        mod = importlib.import_module(_SPLIT_MIGRATION)
        tracker, other = _SplitRecorder(), _SplitRecorder()

        class _Apps:
            def get_model(self, _app: str, model: str) -> type:
                table = tracker if model == "PeriodicTasks" else other
                return type("M", (), {"objects": table})

        mod.merge_schedules(_Apps(), None)
        assert tracker.bumps == 1


class TestTheFrozenLiteralsMatchTheEnumToday:
    """These are wire values, so a rename has to fail loudly rather than pass.

    The migration cannot import the enum, and it never re-runs — so renaming an
    AggregationTier value and "keeping this in step" leaves live rows carrying the old
    string while every test goes green. Comparing the two here turns that into a
    failure at the moment of the rename.
    """

    def test_the_declared_tiers_are_exactly_the_schedulable_ones(self) -> None:
        mod = importlib.import_module(_SPLIT_MIGRATION)
        declared = {spec["tier"] for spec in mod.AGGREGATION_SCHEDULES}
        # ALL is the signature default and the pre-migration row's meaning; no
        # schedule row ever carries it.
        schedulable = {t.value for t in AggregationTier} - {AggregationTier.ALL.value}
        assert declared == schedulable


class TestTheRollbackRestoresOneRow:
    """merge_schedules is this PR's stated safety story and had no coverage at all."""

    def _run_merge(self, rows_present: int | None = None):
        mod = importlib.import_module(_SPLIT_MIGRATION)
        beat, pg, tracker = _SplitRecorder(), _SplitRecorder(), _SplitRecorder()
        beat.rows_present = rows_present
        pg.rows_present = rows_present

        class _Apps:
            def get_model(self, _app: str, model: str) -> type:
                table = {
                    "PeriodicTask": beat,
                    "PgPeriodicTask": pg,
                    "PeriodicTasks": tracker,
                }.get(model, _SplitRecorder())
                return type("M", (), {"objects": table})

        mod.merge_schedules(_Apps(), None)
        return {"beat": beat, "pg": pg, "tracker": tracker}

    def test_the_added_row_is_deleted_from_both_tables(self) -> None:
        merged = self._run_merge()
        for table in ("beat", "pg"):
            assert _NEW_ROW in merged[table].deleted

    def test_the_existing_row_gets_its_pre_split_payload_back(self) -> None:
        merged = self._run_merge()
        assert merged["beat"].updated[_EXISTING_ROW]["kwargs"] == "{}"
        assert merged["pg"].updated[_EXISTING_ROW]["task_kwargs"] == {}

    def test_the_rollback_leaves_ownership_alone_like_the_forward_direction(self) -> None:
        merged = self._run_merge()
        assert "enabled" not in merged["beat"].updated[_EXISTING_ROW]
        assert set(merged["pg"].updated[_EXISTING_ROW]) == {"task_kwargs"}

    def test_a_rollback_that_restores_nothing_raises(self) -> None:
        """A bulk update matching no row would otherwise report a clean rollback while
        leaving the daily and monthly tiers with no schedule at all."""
        with pytest.raises(RuntimeError, match=_EXISTING_ROW):
            self._run_merge(rows_present=0)


class TestTheRewriteLeavesSchedulerOwnershipAlone:
    """The existing row may already be owned by the PG scheduler, with its Beat twin
    disabled by converge_pg_scheduler. Rewriting `pg_owned` or `enabled` here would
    hand it back — and since the Beat twin stays disabled, the aggregation would be
    left with no firer at all. Only the payload may change.
    """

    def test_the_pg_update_touches_only_the_kwargs(self, split: dict[str, _SplitRecorder]) -> None:
        assert set(split["pg"].updated[_EXISTING_ROW]) == {"task_kwargs"}

    def test_the_beat_update_does_not_re_enable_the_row(self, split: dict[str, _SplitRecorder]) -> None:
        assert "enabled" not in split["beat"].updated[_EXISTING_ROW]

    def test_the_existing_row_keeps_its_cadence(self, split: dict[str, _SplitRecorder]) -> None:
        """Only the daily/monthly half moves to hourly; the hourly tier stays at 15
        minutes, which is the first half of the ticket's acceptance criteria.
        """
        for table in ("beat", "pg"):
            update = split[table].updated[_EXISTING_ROW]
            assert not {"crontab", "interval", "cron_string"} & set(update)
