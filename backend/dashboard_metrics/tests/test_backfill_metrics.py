"""Tests for the backfill_metrics management command.

This command is the documented repair path for the daily tier, and the monthly
tier is now derived from what it writes, so a regression here is not self-healing.
"""

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from account_v2.models import Organization
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.management.commands.backfill_metrics import Command
from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    Granularity,
)
from dashboard_metrics.tasks import truncate_to_day


def _explode(*args, **kwargs):
    """Stand-in for a metric query that fails, e.g. on a statement timeout."""
    raise RuntimeError("metric query exploded")


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

        oldest_day = truncate_to_day(frozen - timedelta(days=2)).date()
        row = EventMetricsDaily._base_manager.get(
            organization=self.org, date=oldest_day, metric_name="documents_processed"
        )
        assert row.metric_value == 2, "the oldest day was written as a partial bucket"


class TestSkipDailyWithoutSkipMonthlyWarns(TestCase):
    """The combination that leaves the daily tier short on purpose.

    The rollup's guard keeps monthly from being lowered, so this freezes the month
    at its stored total rather than under-counting it — but daily stays wrong, and
    the month cannot be updated again until it is repaired.
    """

    def test_the_warning_is_emitted(self):
        out = StringIO()
        call_command("backfill_metrics", days=1, skip_daily=True, stdout=out)
        assert "--skip-daily without --skip-monthly" in out.getvalue()


class TestAWholesaleQueryFailureIsNotReportedAsSuccess(TestCase):
    """The pre-deploy step must not print green when every query failed.

    Each metric query is caught individually inside ``_collect_metrics``, so none
    of them ever reaches the per-organisation handler that owns the error counter.
    The command therefore used to print ``BACKFILL COMPLETE`` and exit 0 with the
    daily tier untouched — and the monthly rollup, which now derives from that
    tier, would then run against it.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="fail-org", name="fail", display_name="Fail"
        )

    def test_a_failing_metric_query_raises_and_exits_non_zero(self):
        out = StringIO()
        with patch.object(
            Command,
            "METRIC_CONFIGS",
            [("documents_processed", _explode, False)],
        ):
            with self.assertRaises(CommandError) as caught:
                call_command(
                    "backfill_metrics",
                    days=1,
                    skip_hourly=True,
                    skip_monthly=True,
                    stdout=out,
                )
        assert "error(s) during backfill" in str(caught.exception)
        assert "BACKFILL FAILED" in out.getvalue()

    def test_a_failing_llm_query_is_counted_too(self):
        """The LLM split is caught in its own arm, separate from METRIC_CONFIGS."""
        out = StringIO()
        with patch.object(Command, "METRIC_CONFIGS", []):
            with patch(
                "dashboard_metrics.management.commands.backfill_metrics."
                "MetricsQueryService.get_llm_metrics_split",
                side_effect=RuntimeError("llm query exploded"),
            ):
                with self.assertRaises(CommandError):
                    call_command(
                        "backfill_metrics", days=1, skip_monthly=True, stdout=out
                    )
        assert "BACKFILL FAILED" in out.getvalue()

    def test_a_clean_run_still_reports_complete(self):
        """The control: without a failure the command stays green and returns."""
        out = StringIO()
        call_command(
            "backfill_metrics", days=1, skip_hourly=True, skip_monthly=True, stdout=out
        )
        assert "BACKFILL COMPLETE" in out.getvalue()


class TestExplicitDateRange(TestCase):
    """--start-date/--end-date repairs a past window that --days cannot reach.

    The source queries are end-inclusive, so a range ending at the next midnight
    would rewrite the day after it with only the rows stamped at exactly 00:00.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="range-org", name="range", display_name="Range"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="range-wf", organization=self.org
        )
        self.day = truncate_to_day(timezone.now() - timedelta(days=200))

    def _seed(self, stamp):
        execution = WorkflowExecution.objects.create(
            workflow=self.workflow, status=ExecutionStatus.COMPLETED
        )
        fe = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name=f"{stamp.isoformat()}.pdf",
            status=ExecutionStatus.COMPLETED.value,
        )
        WorkflowFileExecution.objects.filter(pk=fe.pk).update(created_at=stamp)
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)

    def _daily(self, day):
        return EventMetricsDaily._base_manager.get(
            organization=self.org, date=day.date(), metric_name="documents_processed"
        ).metric_value

    def test_the_range_is_written_whole_and_the_next_day_is_untouched(self):
        next_day = self.day + timedelta(days=1)
        self._seed(self.day + timedelta(hours=1))
        self._seed(self.day + timedelta(hours=23))
        self._seed(next_day)  # exactly midnight: inside an end-inclusive midnight end
        EventMetricsDaily._base_manager.create(
            organization=self.org,
            date=next_day.date(),
            metric_name="documents_processed",
            project="default",
            tag="",
            metric_value=5,
            metric_count=1,
        )

        call_command(
            "backfill_metrics",
            start_date=self.day.date().isoformat(),
            end_date=self.day.date().isoformat(),
            skip_hourly=True,
            skip_monthly=True,
            stdout=StringIO(),
        )

        assert self._daily(self.day) == 2
        assert self._daily(next_day) == 5, "the day after the range was overwritten"

    def test_end_date_without_start_date_is_refused(self):
        with self.assertRaises(CommandError):
            call_command("backfill_metrics", end_date="2026-04-08", stdout=StringIO())


class TestAPartialMonthRangeKeepsTheMonthlyTotal(TestCase):
    """A range covering part of a month must not replace that month's total.

    The monthly row would be rewritten with only the days in the range, and a
    month outside the cron's current-and-previous window is never rederived.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="month-org", name="month", display_name="Month"
        )
        EventMetricsMonthly._base_manager.create(
            organization=self.org,
            month=date(2026, 3, 1),
            metric_name="documents_processed",
            project="default",
            tag="",
            metric_value=1000,
            metric_count=31,
        )

    def _monthly(self):
        return EventMetricsMonthly._base_manager.get(
            organization=self.org,
            month=date(2026, 3, 1),
            metric_name="documents_processed",
        ).metric_value

    def test_a_partial_month_without_skip_monthly_is_refused(self):
        """A partial first month, and a partial last month."""
        for start, end in (("2026-03-12", "2026-04-08"), ("2026-03-01", "2026-03-20")):
            with self.subTest(start=start, end=end):
                with self.assertRaises(CommandError) as caught:
                    call_command(
                        "backfill_metrics",
                        start_date=start,
                        end_date=end,
                        skip_hourly=True,
                        stdout=StringIO(),
                    )
                assert "--skip-monthly" in str(caught.exception)
                assert self._monthly() == 1000

    def test_whole_months_may_raise_the_monthly_total(self):
        """The control: a range of whole months is a complete source for them."""
        EventMetricsMonthly._base_manager.filter(organization=self.org).update(
            metric_value=0
        )
        workflow = Workflow.objects.create(
            workflow_name="month-wf", organization=self.org
        )
        execution = WorkflowExecution.objects.create(
            workflow=workflow, status=ExecutionStatus.COMPLETED
        )
        fe = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name="march.pdf",
            status=ExecutionStatus.COMPLETED.value,
        )
        stamp = timezone.make_aware(timezone.datetime(2026, 3, 15, 12))
        WorkflowFileExecution.objects.filter(pk=fe.pk).update(created_at=stamp)
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)

        call_command(
            "backfill_metrics",
            start_date="2026-03-01",
            end_date="2026-03-31",
            skip_hourly=True,
            stdout=StringIO(),
        )
        assert self._monthly() == 1


class TestTheRebuildNeverLowersAStoredValue(TestCase):
    """A recount below the stored value is history the sources lost, not an over-count.

    HITL TTL cleanup moves approved reviews to EXPIRED, and deleting a workflow
    cascades to its executions, so the sources shrink after they were aggregated.
    Overwriting would lower history that nothing else holds, and a month older than
    the previous one is never rederived to put it back.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="lower-org", name="lower", display_name="Lower"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="lower-wf", organization=self.org
        )
        self.day = truncate_to_day(timezone.now() - timedelta(days=200))
        execution = WorkflowExecution.objects.create(
            workflow=self.workflow, status=ExecutionStatus.COMPLETED
        )
        stamp = self.day + timedelta(hours=10)
        for name in ("a.pdf", "b.pdf"):
            fe = WorkflowFileExecution.objects.create(
                workflow_execution=execution,
                file_name=name,
                status=ExecutionStatus.COMPLETED.value,
            )
            WorkflowFileExecution.objects.filter(pk=fe.pk).update(created_at=stamp)
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)
        self.hour = stamp.replace(minute=0, second=0, microsecond=0)

    def _store(self, model, period, value, **period_field):
        model._base_manager.create(
            organization=self.org,
            metric_name="documents_processed",
            project="default",
            tag="",
            metric_value=value,
            metric_count=1,
            **{period_field.popitem()[0]: period},
        )

    def _value(self, model, **period):
        return model._base_manager.get(
            organization=self.org, metric_name="documents_processed", **period
        ).metric_value

    def _run(self, **flags):
        out = StringIO()
        call_command(
            "backfill_metrics",
            start_date=self.day.date().isoformat(),
            end_date=self.day.date().isoformat(),
            skip_monthly=True,
            stdout=out,
            **flags,
        )
        return out.getvalue()

    def test_the_check_is_part_of_the_write(self):
        """One conditional upsert, with no read of the stored value before it.

        A separate read goes stale when the aggregator writes in between, and a lock
        taken for it can join a cycle with the monthly rollup.
        """
        self._store(EventMetricsDaily, self.day.date(), 1, date=None)
        with CaptureQueriesContext(connection) as queries:
            self._run(skip_hourly=True)
        daily = [
            q["sql"]
            for q in queries.captured_queries
            if "event_metrics_daily" in q["sql"]
        ]
        assert len(daily) == 1
        assert "WHERE EXCLUDED" in daily[0]
        assert "metric_value" in daily[0].split("WHERE EXCLUDED")[1]

    def test_a_higher_stored_daily_value_is_kept_and_reported(self):
        self._store(EventMetricsDaily, self.day.date(), 5, date=None)
        out = self._run(skip_hourly=True)
        assert self._value(EventMetricsDaily, date=self.day.date()) == 5
        assert "kept 1" in out

    def test_an_equal_recount_is_written(self):
        """Only a lower recount is kept back; an equal one still writes."""
        self._store(EventMetricsDaily, self.day.date(), 2, date=None)
        out = self._run(skip_hourly=True)
        assert "kept" not in out

    def test_a_lower_stored_daily_value_is_raised(self):
        """The control: the repair still fills a hole."""
        self._store(EventMetricsDaily, self.day.date(), 1, date=None)
        self._run(skip_hourly=True)
        assert self._value(EventMetricsDaily, date=self.day.date()) == 2

    def test_a_higher_stored_hourly_value_is_kept(self):
        """Hourly keys are datetimes, the easiest to mismatch and so lower silently."""
        self._store(EventMetricsHourly, self.hour, 5, timestamp=None)
        self._run()
        assert self._value(EventMetricsHourly, timestamp=self.hour) == 5

    def test_a_higher_stored_monthly_value_is_kept(self):
        month = self.day.date().replace(day=1)
        EventMetricsMonthly._base_manager.create(
            organization=self.org,
            month=month,
            metric_name="documents_processed",
            project="default",
            tag="",
            metric_value=1000,
            metric_count=31,
        )
        call_command(
            "backfill_metrics",
            start_date=month.isoformat(),
            end_date=(
                (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            ).isoformat(),
            skip_hourly=True,
            stdout=StringIO(),
        )
        assert self._value(EventMetricsMonthly, month=month) == 1000


class TestMonthlyIsSummedFromTheGuardedDays(TestCase):
    """A month whose days were partly kept and partly filled sums to its days.

    Summing the raw recount instead puts the month below its own daily rows, and a
    month older than the previous one is never rederived to fix it.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="mixed-org", name="mixed", display_name="Mixed"
        )
        workflow = Workflow.objects.create(
            workflow_name="mixed-wf", organization=self.org
        )
        for day, files in ((1, 7), (2, 5)):
            stamp = timezone.make_aware(timezone.datetime(2026, 3, day, 12))
            execution = WorkflowExecution.objects.create(
                workflow=workflow, status=ExecutionStatus.COMPLETED
            )
            WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)
            for n in range(files):
                fe = WorkflowFileExecution.objects.create(
                    workflow_execution=execution,
                    file_name=f"{day}-{n}.pdf",
                    status=ExecutionStatus.COMPLETED.value,
                )
                WorkflowFileExecution.objects.filter(pk=fe.pk).update(created_at=stamp)
        stored = {"organization": self.org, "metric_name": "documents_processed"}
        EventMetricsDaily._base_manager.create(
            date=date(2026, 3, 1), metric_value=10, metric_count=1, **stored
        )
        EventMetricsMonthly._base_manager.create(
            month=date(2026, 3, 1), metric_value=10, metric_count=1, **stored
        )

    def test_monthly_equals_the_sum_of_its_daily_rows(self):
        call_command(
            "backfill_metrics",
            start_date="2026-03-01",
            end_date="2026-03-31",
            skip_hourly=True,
            stdout=StringIO(),
        )
        rows = {"organization": self.org, "metric_name": "documents_processed"}
        days = EventMetricsDaily._base_manager.filter(**rows).order_by("date")
        assert [d.metric_value for d in days] == [10, 5]
        month = EventMetricsMonthly._base_manager.get(month=date(2026, 3, 1), **rows)
        assert month.metric_value == 15
