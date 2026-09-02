"""The split preserves every figure it used to write (UN-3974, AC-2).

AC-2 is an equivalence claim — "hourly figures unchanged; daily and monthly lag by at
most one hour" — so it is settled by running the real aggregation and diffing what lands
in the metrics tables, not by reasoning about the gating predicates. Those are pinned
separately in test_aggregation_tier.py; this is the outcome they are supposed to produce.

Two properties, and both matter:

- the `hourly` schedule reproduces what the single pre-split run wrote to
  EventMetricsHourly, exactly — that is the "unchanged" half
- `hourly` and `daily_monthly` together reproduce every row the pre-split run wrote to
  any table — that is the "nothing is lost" half, which the AC assumes rather than states

DB-bound, so conftest marks it integration.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from account_v2.models import Organization  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402
from workflow_manager.workflow_v2.models.workflow import Workflow  # noqa: E402

from dashboard_metrics.models import (  # noqa: E402
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
)
from dashboard_metrics.tasks import AggregationTier, _run_aggregation  # noqa: E402

# (model, the column naming its period) — the period field differs per tier.
_TIERS = [
    (EventMetricsHourly, "timestamp"),
    (EventMetricsDaily, "date"),
    (EventMetricsMonthly, "month"),
]
_FIELDS = ["metric_name", "metric_type", "metric_value", "metric_count"]


class TestTheSplitPreservesEveryFigure(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            organization_id="tier-split-org", name="tier-split", display_name="Tier Split"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="tier-split-wf", organization=self.org
        )
        now = timezone.now()
        # One row per window the aggregation reads — last 24h for the hourly tier, last
        # 7 days for daily, inside the previous month for monthly. The two recent ones
        # also make the org visible to the active-org prefilter, without which nothing
        # runs at all.
        windows = [
            now - timedelta(hours=2),
            now - timedelta(hours=5),
            now - timedelta(days=3),
            now - timedelta(days=25),
        ]
        executions = self._add_executions(windows)
        # Both aggregation paths have to be exercised: the per-metric queries go through
        # _aggregate_single_metric and the four LLM metrics through
        # _aggregate_llm_combined, and each gates on the tier separately. A fixture
        # producing only LLM figures leaves half the split unverified.
        self._add_file_executions(executions)
        self._add_llm_usage(windows)

    def _add_executions(self, timestamps: list[Any]) -> list[tuple[Any, Any]]:
        """Raw insert so created_at is ours; the model sets it with auto_now_add."""
        created = []
        with connection.cursor() as cur:
            for ts in timestamps:
                execution_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO workflow_execution (id, created_at, modified_at, "
                    "workflow_id, execution_mode, execution_method, execution_type, "
                    "execution_log_id, status, error_message, attempts, execution_time, "
                    "result_acknowledged, total_files) "
                    "VALUES (%s, %s, %s, %s, 'INSTANT', 'DIRECT', 'COMPLETE', '', "
                    "'COMPLETED', '', 0, 1.0, false, 1)",
                    [execution_id, ts, ts, self.workflow.id],
                )
                created.append((execution_id, ts))
        return created

    def _add_file_executions(self, executions: list[tuple[Any, Any]]) -> None:
        """Feeds documents_processed, which runs through _aggregate_single_metric."""
        with connection.cursor() as cur:
            for execution_id, ts in executions:
                cur.execute(
                    "INSERT INTO workflow_file_execution (id, created_at, modified_at, "
                    "file_name, status, workflow_execution_id) "
                    "VALUES (%s, %s, %s, 'doc.pdf', 'COMPLETED', %s)",
                    [uuid.uuid4(), ts, ts, execution_id],
                )

    def _add_llm_usage(self, timestamps: list[Any]) -> None:
        """LLM metrics need no joins, so they are the cheapest way to put a real figure
        in all three tiers."""
        with connection.cursor() as cur:
            for ts in timestamps:
                cur.execute(
                    "INSERT INTO usage (id, created_at, modified_at, adapter_instance_id, "
                    "usage_type, llm_usage_reason, model_name, embedding_tokens, "
                    "prompt_tokens, completion_tokens, total_tokens, cost_in_dollars, "
                    "organization_id) "
                    "VALUES (%s, %s, %s, 'test-adapter', 'llm', 'extraction', 'test-model', "
                    "0, 100, 50, 150, 0.25, %s)",
                    [uuid.uuid4(), ts, ts, self.org.id],
                )

    def _snapshot(self) -> dict[str, set[tuple[Any, ...]]]:
        return {
            model.__name__: set(
                model._base_manager.values_list("organization_id", period, *_FIELDS)
            )
            for model, period in _TIERS
        }

    def _clear(self) -> None:
        for model, _ in _TIERS:
            model._base_manager.all().delete()

    def _run(self, tier: AggregationTier) -> dict[str, set[tuple[Any, ...]]]:
        self._clear()
        _run_aggregation(tier)
        return self._snapshot()

    def test_the_pre_split_run_writes_all_three_tiers(self) -> None:
        """Guards the tests below from passing vacuously: an equivalence between two
        empty sets proves nothing.
        """
        every_tier = self._run(AggregationTier.ALL)
        for name, rows in every_tier.items():
            assert rows, f"{name} is empty — the fixture produces no metrics to compare"

    def test_the_fixture_exercises_both_aggregation_paths(self) -> None:
        """The other way these tests can go quietly vacuous. The tier is checked
        separately in _aggregate_single_metric and in _aggregate_llm_combined, so a
        fixture yielding only one kind of metric verifies only half the split — which
        is exactly what a mutation test caught here.
        """
        every_tier = self._run(AggregationTier.ALL)
        for table, rows in every_tier.items():
            names = {row[2] for row in rows}
            assert "documents_processed" in names, f"{table}: no per-metric figure"
            assert "llm_calls" in names, f"{table}: no combined-LLM figure"

    def test_hourly_reproduces_the_pre_split_hourly_figures(self) -> None:
        """The "figures unchanged" half of AC-2, row for row rather than in aggregate."""
        before = self._run(AggregationTier.ALL)["EventMetricsHourly"]
        after = self._run(AggregationTier.HOURLY)["EventMetricsHourly"]
        assert after == before

    def test_the_two_schedules_together_lose_nothing(self) -> None:
        """Every row the single pre-split run wrote is still written by one of the two
        schedules, and neither invents one.
        """
        every_tier = self._run(AggregationTier.ALL)
        hourly = self._run(AggregationTier.HOURLY)
        daily_monthly = self._run(AggregationTier.DAILY_MONTHLY)

        for name in every_tier:
            combined = hourly[name] | daily_monthly[name]
            assert combined == every_tier[name], f"{name} differs after the split"

    def test_neither_schedule_writes_the_other_tiers_tables(self) -> None:
        """If they overlapped, the two schedules would duplicate work every hour on the
        hour — harmless thanks to the upserts, but not free.
        """
        hourly = self._run(AggregationTier.HOURLY)
        assert not hourly["EventMetricsDaily"]
        assert not hourly["EventMetricsMonthly"]

        daily_monthly = self._run(AggregationTier.DAILY_MONTHLY)
        assert not daily_monthly["EventMetricsHourly"]
