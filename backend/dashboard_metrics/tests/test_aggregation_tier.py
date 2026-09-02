"""Guard: the tier a schedule row asks for is the tier that gets written.

The split runs one task on two schedules that differ only in their ``tier`` kwarg, so
the gating predicates and the per-tier lock key are the whole mechanism. Each property
here is one way the split fails silently — writing nothing, writing both tiers from one
schedule, or the two schedules starving each other on the lock.

DB-free, so this runs in the unit tier alongside test_pg_periodic_task_declarations.py.
"""

from __future__ import annotations

import inspect
import os
import time

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.cache import cache  # noqa: E402

from dashboard_metrics.tasks import (  # noqa: E402
    AGGREGATION_LOCK_TIMEOUT,
    DASHBOARD_SOURCE_WINDOW_DAYS,
    AggregationTier,
    _acquire_aggregation_lock,
    _acquire_aggregation_locks,
    _aggregation_lock_keys,
    _tiers_written,
    _writes_daily_monthly,
    _writes_hourly,
    aggregate_metrics_from_sources,
)


def _keys(tier, window: int = DASHBOARD_SOURCE_WINDOW_DAYS) -> list[str]:
    return _aggregation_lock_keys(tier, window)


class TestWhichTiersEachRunWrites:
    @pytest.mark.parametrize(
        "tier,hourly,daily_monthly",
        [
            (AggregationTier.HOURLY, True, False),
            (AggregationTier.DAILY_MONTHLY, False, True),
            (AggregationTier.ALL, True, True),
        ],
    )
    def test_the_predicates_partition_the_work(
        self, tier: AggregationTier, hourly: bool, daily_monthly: bool
    ) -> None:
        assert _writes_hourly(tier) is hourly
        assert _writes_daily_monthly(tier) is daily_monthly

    def test_the_two_schedules_together_cover_every_tier(self) -> None:
        """Neither schedule may leave a tier unwritten: hourly and daily_monthly are
        the only two rows, so between them they have to do everything `all` does.
        """
        scheduled = (AggregationTier.HOURLY, AggregationTier.DAILY_MONTHLY)
        assert any(_writes_hourly(t) for t in scheduled)
        assert any(_writes_daily_monthly(t) for t in scheduled)

    def test_no_tier_is_written_by_both_schedules(self) -> None:
        """Overlap would mean duplicate work every hour on the hour. The upserts make
        it harmless, not free.
        """
        assert not _writes_daily_monthly(AggregationTier.HOURLY)
        assert not _writes_hourly(AggregationTier.DAILY_MONTHLY)


class TestTheDefaultIsAll:
    """The property that keeps the deploy window safe, pinned at the signature.

    Between the code deploying and migration 0006 running, the schedule row still
    carries no tier kwarg. Every other test in the suite passes a tier explicitly or
    mocks the task, so none of them can see what the default actually is.
    """

    def test_the_signature_default_is_all(self) -> None:
        """Narrower and daily/monthly stop being written for the whole window; none
        and nothing is written at all. Both look like successful runs.
        """
        default = inspect.signature(aggregate_metrics_from_sources).parameters[
            "tier"
        ].default
        assert default == AggregationTier.ALL

    def test_the_default_writes_everything_rather_than_nothing(self) -> None:
        assert AggregationTier("all") is AggregationTier.ALL
        assert _writes_hourly(AggregationTier.ALL)
        assert _writes_daily_monthly(AggregationTier.ALL)

    def test_an_unrecognised_tier_raises(self) -> None:
        """The internal view turns this into a 400. A silent no-op would look like a
        successful run that wrote nothing.
        """
        with pytest.raises(ValueError):
            AggregationTier("houry")


class TestTheTierTableIsExhaustive:
    """A member with no entry must raise, not write nothing and report success."""

    def test_every_declared_tier_has_an_entry(self) -> None:
        for tier in AggregationTier:
            assert _tiers_written(tier)

    def test_an_unhandled_member_raises_rather_than_writing_nothing(self) -> None:
        # Stands in for a member added to the enum without a _TIER_WRITES entry.
        ghost = type("_Ghost", (), {"value": "weekly"})()
        with pytest.raises(AssertionError, match="Unhandled AggregationTier"):
            _tiers_written(ghost)


class TestTheLockCoversWhatIsWritten:
    """Keyed by granularity written, not by enum member.

    Keying on the label alone gives ALL a third key that excludes nothing, so an ALL
    run and the scheduled hourly run write EventMetricsHourly concurrently. These
    exercise the lock rather than its key string: a version of
    _acquire_aggregation_lock that ignored its argument would pass a key-shape test.
    """

    @pytest.fixture(autouse=True)
    def _clear(self):
        cache.clear()
        yield
        cache.clear()

    def test_the_two_scheduled_tiers_never_block_each_other(self) -> None:
        assert _acquire_aggregation_locks(_keys(AggregationTier.HOURLY))
        assert _acquire_aggregation_locks(_keys(AggregationTier.DAILY_MONTHLY))

    def test_a_tier_blocks_itself(self) -> None:
        assert _acquire_aggregation_locks(_keys(AggregationTier.HOURLY))
        assert not _acquire_aggregation_locks(_keys(AggregationTier.HOURLY))

    def test_all_is_blocked_by_either_half(self) -> None:
        """The exclusion a per-member key silently dropped."""
        assert _acquire_aggregation_locks(_keys(AggregationTier.HOURLY))
        assert not _acquire_aggregation_locks(_keys(AggregationTier.ALL))

    def test_a_blocked_run_releases_whatever_it_took(self) -> None:
        """ALL takes hourly first; failing on daily_monthly must not strand hourly."""
        assert _acquire_aggregation_locks(_keys(AggregationTier.DAILY_MONTHLY))
        assert not _acquire_aggregation_locks(_keys(AggregationTier.ALL))
        assert _acquire_aggregation_locks(_keys(AggregationTier.HOURLY))

    def test_a_wider_window_is_a_different_job(self) -> None:
        """The reconciliation pass is never retried, so it must not be starved by the
        15-minute schedule it races against."""
        assert _acquire_aggregation_locks(_keys(AggregationTier.HOURLY, 2))
        assert _acquire_aggregation_locks(_keys(AggregationTier.ALL, 7))


class TestTheLockSelfHeals:
    """Both reclaim branches, neither of which was executed by any test."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        cache.clear()
        yield
        cache.clear()

    def test_a_lock_older_than_the_timeout_is_reclaimed(self) -> None:
        key = _keys(AggregationTier.HOURLY)[0]
        cache.set(key, str(time.time() - AGGREGATION_LOCK_TIMEOUT - 1), 3600)
        assert _acquire_aggregation_lock(key)

    def test_a_fresh_lock_is_not_reclaimed(self) -> None:
        key = _keys(AggregationTier.HOURLY)[0]
        cache.set(key, str(time.time()), 3600)
        assert not _acquire_aggregation_lock(key)

    def test_a_corrupted_lock_value_is_reclaimed(self) -> None:
        key = _keys(AggregationTier.HOURLY)[0]
        cache.set(key, "running", 3600)
        assert _acquire_aggregation_lock(key)
