"""Guard: the tier a schedule row asks for is the tier that gets written.

The split runs one task on two schedules that differ only in their ``tier`` kwarg, so
the gating predicates and the per-tier lock key are the whole mechanism. Each property
here is one way the split fails silently — writing nothing, writing both tiers from one
schedule, or the two schedules starving each other on the lock.

DB-free, so this runs in the unit tier alongside test_pg_periodic_task_declarations.py.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from dashboard_metrics.tasks import (  # noqa: E402
    AggregationTier,
    _aggregation_lock_key,
    _writes_daily_monthly,
    _writes_hourly,
)


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
    def test_omitting_the_tier_writes_everything_rather_than_nothing(self) -> None:
        """Between the code deploying and migration 0005 running, the schedule row
        still carries no tier kwarg. Defaulting to anything narrower would stop writing
        tiers during that window; defaulting to none would stop writing entirely.
        """
        assert AggregationTier("all") is AggregationTier.ALL
        assert _writes_hourly(AggregationTier.ALL)
        assert _writes_daily_monthly(AggregationTier.ALL)

    def test_an_unrecognised_tier_raises(self) -> None:
        """The internal view turns this into a 400. A silent no-op would look like a
        successful run that wrote nothing.
        """
        with pytest.raises(ValueError):
            AggregationTier("houry")


class TestTheLockIsPerTier:
    def test_every_tier_gets_its_own_key(self) -> None:
        """The two schedules collide at the top of every hour. One global key and
        whichever fired first would hold it while the other returned lock_held —
        so the slower tier could be starved indefinitely.
        """
        keys = {_aggregation_lock_key(t) for t in AggregationTier}
        assert len(keys) == len(list(AggregationTier))

    def test_the_key_names_the_tier(self) -> None:
        for tier in AggregationTier:
            assert _aggregation_lock_key(tier).endswith(tier.value)
