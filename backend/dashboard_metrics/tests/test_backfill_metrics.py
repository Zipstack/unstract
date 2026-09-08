"""Tests for the backfill_metrics management command.

This command is the documented repair path for the daily tier, and the monthly
tier is now derived from what it writes, so a regression here is not self-healing.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from account_v2.models import Organization
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.management.commands.backfill_metrics import Command
from dashboard_metrics.models import EventMetricsDaily, Granularity
from dashboard_metrics.tasks import _truncate_to_day


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


class TestTheOldestBackfilledDayIsWhole(TestCase):
    """The window boundary this PR changed, which had no exerciser.

    An untruncated start writes the oldest day as a partial bucket, and the monthly
    rollup now sums the persisted daily tier rather than recomputing that day from
    source — so the partial value becomes permanent once it ages past the reconcile
    window. This is the mandatory pre-deploy step, so a regression here corrupts the
    state everything else assumes.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="trunc-org", name="trunc", display_name="Trunc"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="trunc-wf", organization=self.org
        )
        self.now = timezone.now()

    def _seed(self, days_ago, hour):
        stamp = (self.now - timedelta(days=days_ago)).replace(hour=hour, minute=30)
        execution = WorkflowExecution.objects.create(
            workflow=self.workflow, status=ExecutionStatus.COMPLETED
        )
        fe = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name=f"{days_ago}-{hour}.pdf",
            status=ExecutionStatus.COMPLETED.value,
        )
        WorkflowFileExecution.objects.filter(pk=fe.pk).update(created_at=stamp)
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)

    def _frozen(self):
        """Mid-afternoon, so the untruncated boundary really does exclude hour 1.

        Read from the real clock this test passed with the bug present whenever CI
        ran before 01:30 UTC — the boundary was already earlier than the seeded row.
        """
        return self.now.replace(hour=15, minute=0, second=0, microsecond=0)

    def test_the_oldest_covered_day_counts_its_whole_day(self):
        """Two rows on the boundary day, one before the run's hour and one after.

        Untruncated, the earlier row falls outside the window and the oldest day is
        written short.
        """
        frozen = self._frozen()
        with patch("django.utils.timezone.now", return_value=frozen):
            self.now = frozen
            self._seed(days_ago=2, hour=1)
            self._seed(days_ago=2, hour=23)
            call_command("backfill_metrics", days=2, skip_hourly=True, skip_monthly=True)

        oldest_day = _truncate_to_day(frozen - timedelta(days=2)).date()
        row = EventMetricsDaily._base_manager.get(
            organization=self.org, date=oldest_day, metric_name="documents_processed"
        )
        assert row.metric_value == 2, "the oldest day was written as a partial bucket"


class TestSkipDailyWithoutSkipMonthlyWarns(TestCase):
    """The combination that produces an under-count rather than a no-op."""

    def test_the_warning_is_emitted(self):
        out = StringIO()
        call_command("backfill_metrics", days=1, skip_daily=True, stdout=out)
        assert "--skip-daily without --skip-monthly" in out.getvalue()
