"""Tests for the backfill_metrics management command.

This command is the documented repair path for the daily tier, and the monthly
tier is now derived from what it writes, so a regression here is not self-healing.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from dashboard_metrics.management.commands.backfill_metrics import Command
from dashboard_metrics.models import Granularity


class TestSkipHourlySkipsTheQueries(TestCase):
    """--skip-hourly must skip the HOUR source queries, not just their upsert.

    The prescribed deploy step passes it over a window measured in weeks. Reading
    the flag only at the upsert would reinstate, once at deploy time, the very
    multi-week scan across the source tables this change exists to remove — while
    the operator believes it was skipped.
    """

    def setUp(self):
        self.requested = []
        self.now = timezone.now()

        def _recording_query(org_id, start, end, granularity=None, **kwargs):
            self.requested.append(granularity)
            return []

        self.configs = [("documents_processed", _recording_query, False)]

    def _collect(self, skip_hourly):
        command = Command()
        with patch.object(Command, "METRIC_CONFIGS", self.configs):
            with patch(
                "dashboard_metrics.management.commands.backfill_metrics."
                "MetricsQueryService.get_llm_metrics_split",
                return_value={},
            ):
                command._collect_metrics(
                    "1",
                    self.now - timedelta(days=3),
                    self.now,
                    skip_hourly=skip_hourly,
                )

    def test_skip_hourly_issues_no_hour_granularity_query(self):
        self._collect(skip_hourly=True)
        assert Granularity.HOUR not in self.requested
        assert Granularity.DAY in self.requested

    def test_without_the_flag_both_granularities_are_queried(self):
        """The control: the flag is what removes them, not the stub."""
        self._collect(skip_hourly=False)
        assert Granularity.HOUR in self.requested
        assert Granularity.DAY in self.requested


class TestLLMSplitHonoursSkipHourly(TestCase):
    """The combined-LLM path is a second query site with the same flag."""

    def setUp(self):
        self.requested = []
        self.now = timezone.now()

    def _collect(self, skip_hourly):
        def _recording_split(org_id, start, end, granularity):
            self.requested.append(granularity)
            return {}

        command = Command()
        with patch.object(Command, "METRIC_CONFIGS", []):
            with patch(
                "dashboard_metrics.management.commands.backfill_metrics."
                "MetricsQueryService.get_llm_metrics_split",
                side_effect=_recording_split,
            ):
                command._collect_metrics(
                    "1",
                    self.now - timedelta(days=3),
                    self.now,
                    skip_hourly=skip_hourly,
                )

    def test_skip_hourly_issues_no_hour_granularity_query(self):
        self._collect(skip_hourly=True)
        assert self.requested == [Granularity.DAY]

    def test_without_the_flag_both_granularities_are_queried(self):
        self._collect(skip_hourly=False)
        assert self.requested == [Granularity.HOUR, Granularity.DAY]
