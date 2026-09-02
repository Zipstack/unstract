"""Drift guard between the Beat and PG declarations of the metrics periodics (UN-3796).

Two migrations declare the same three schedules — ``0002_setup_periodic_tasks`` for Celery
Beat and ``0004_pg_periodic_tasks`` for the PG scheduler. They are separate rows in
separate tables, so nothing stops someone editing one and forgetting the other. That is
the whole failure mode this file exists for: a schedule changed on Beat but not on PG means
the task silently runs on a different cadence the moment the flag flips.

``0006_split_aggregation_schedule`` (UN-3974) then splits the aggregation into two rows by
tier. It writes both scheduler tables from one spec, so the new row cannot drift by
construction — but it also rewrites an existing row, and *how* it does that is load-bearing.
The last section covers both.

DB-free — the migration modules are imported and their declared specs compared directly,
so this runs in the unit tier rather than needing a migrated database.
"""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

_BEAT_MIGRATION = "dashboard_metrics.migrations.0002_setup_periodic_tasks"
_PG_MIGRATION = "dashboard_metrics.migrations.0004_pg_periodic_tasks"

# Cron equivalent of each Beat schedule, asserted against what the Beat migration builds.
# Written out rather than derived: deriving it from the same code under test would make
# the comparison vacuous.
_EXPECTED_CRON = {
    "dashboard_metrics_aggregate_from_sources": "*/15 * * * *",
    "dashboard_metrics_cleanup_hourly": "0 2 * * *",
    "dashboard_metrics_cleanup_daily": "0 3 * * 0",
}


@pytest.fixture(scope="module")
def pg_specs() -> dict[str, dict]:
    mod = importlib.import_module(_PG_MIGRATION)
    return {spec["name"]: spec for spec in mod.PG_PERIODIC_TASKS}


class _FakeQuerySet:
    """Captures update_or_create calls from the Beat migration without a database."""

    def __init__(self, sink: dict):
        self._sink = sink

    def get_or_create(self, **kwargs):
        # Schedule rows (Interval/Crontab) — return the kwargs so the PeriodicTask
        # call can be inspected for which schedule it was given.
        return kwargs, True

    def update_or_create(self, name=None, defaults=None, **_kw):
        self._sink[name] = defaults or {}
        return defaults, True

    def filter(self, *_a, **_k):
        return self

    def delete(self):
        return (0, {})


@pytest.fixture(scope="module")
def beat_specs() -> dict[str, dict]:
    """Run the Beat migration's forward function against fakes and capture what it declares."""
    mod = importlib.import_module(_BEAT_MIGRATION)
    captured: dict[str, dict] = {}

    class _Apps:
        def get_model(self, _app: str, model: str) -> type:
            if model == "PeriodicTask":
                return type("PT", (), {"objects": _FakeQuerySet(captured)})
            return type("S", (), {"objects": _FakeQuerySet({})})

    mod.create_periodic_tasks(_Apps(), None)
    return captured


class TestDeclarationsAgree:
    def test_same_set_of_schedules(self, beat_specs, pg_specs):
        # A schedule added to Beat but not PG stops firing the moment the flag flips;
        # the reverse fires something Beat never knew about.
        assert set(beat_specs) == set(pg_specs)

    @pytest.mark.parametrize("name", sorted(_EXPECTED_CRON))
    def test_task_path_and_queue_match(self, beat_specs, pg_specs, name):
        assert pg_specs[name]["task_name"] == beat_specs[name]["task"]
        assert pg_specs[name]["queue"] == beat_specs[name]["queue"]

    @pytest.mark.parametrize("name", sorted(_EXPECTED_CRON))
    def test_kwargs_match_once_decoded(self, beat_specs, pg_specs, name):
        # Beat stores kwargs as a JSON *string*; PgPeriodicTask.task_kwargs is a
        # JSONField. A mismatch here means the cleanup runs with the wrong retention.
        beat_kwargs = json.loads(beat_specs[name].get("kwargs") or "{}")
        assert pg_specs[name]["task_kwargs"] == beat_kwargs

    @pytest.mark.parametrize("name,cron", sorted(_EXPECTED_CRON.items()))
    def test_cron_matches_the_beat_cadence(self, pg_specs, name, cron):
        assert pg_specs[name]["cron_string"] == cron


class TestSeededInert:
    """Applying the migration must not cause anything to fire."""

    def test_no_spec_declares_itself_pg_owned(self, pg_specs):
        # pg_owned is set to False in the migration's defaults, never from the spec —
        # this pins that no spec can smuggle ownership in.
        assert not any("pg_owned" in spec for spec in pg_specs.values())

    def test_no_spec_presets_a_run_time(self, pg_specs):
        # A non-NULL next_run_at in the past would read as "overdue" and fire a burst
        # of catch-up runs the moment the flag is enabled.
        for spec in pg_specs.values():
            assert "next_run_at" not in spec
            assert "last_run_at" not in spec


_SPLIT_MIGRATION = "dashboard_metrics.migrations.0006_split_aggregation_schedule"
_NEW_ROW = "dashboard_metrics_aggregate_daily_monthly"
_EXISTING_ROW = "dashboard_metrics_aggregate_from_sources"


class _SplitRecorder:
    """Captures what 0005 does to one scheduler table, keeping creates and updates apart.

    The distinction is the point: creating a row writes every default, updating one writes
    only the named fields. Conflating them is exactly the bug this guards.
    """

    def __init__(self, existing: Any = None) -> None:
        self.created: dict[str, dict[str, Any]] = {}
        self.updated: dict[str, dict[str, Any]] = {}
        self.bumps = 0
        self._existing = existing
        self._filtered_on: str = ""

    def filter(self, name: str = "", **_kw: Any) -> _SplitRecorder:
        self._filtered_on = name
        return self

    def first(self) -> Any:
        return self._existing

    def update(self, **kwargs: Any) -> int:
        self.updated[self._filtered_on] = kwargs
        return 1

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
        return (0, {})


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
