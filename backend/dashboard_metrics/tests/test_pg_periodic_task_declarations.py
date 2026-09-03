"""Drift guard between the Beat and PG declarations of the metrics periodics (UN-3796).

Two migrations declare the same three schedules — ``0002_setup_periodic_tasks`` for Celery
Beat and ``0004_pg_periodic_tasks`` for the PG scheduler. They are separate rows in
separate tables, so nothing stops someone editing one and forgetting the other. That is
the whole failure mode this file exists for: a schedule changed on Beat but not on PG means
the task silently runs on a different cadence the moment the flag flips.

DB-free — both migration modules are imported and their declared specs compared directly,
so this runs in the unit tier rather than needing a migrated database.
"""

from __future__ import annotations

import importlib
import json

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
        def get_model(self, _app, model):
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
