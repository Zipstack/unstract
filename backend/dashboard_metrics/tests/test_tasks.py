"""Unit tests for Dashboard Metrics Celery tasks."""

import json
import time
from datetime import date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from account_v2.models import Organization
from django.apps import apps
from django.core.cache import cache
from django.db import connection
from django.db.utils import DatabaseError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_celery_beat.models import PeriodicTask, PeriodicTasks
from pg_queue.models import PgPeriodicTask
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.internal_views import AggregateMetricsAPIView
from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    Granularity,
    MetricType,
)
from dashboard_metrics.services import MetricsQueryService
from dashboard_metrics.tasks import (
    DASHBOARD_RECONCILE_WINDOW_DAYS,
    DASHBOARD_SOURCE_WINDOW_DAYS,
    AggregationTier,
    _acquire_aggregation_lock,
    _acquire_aggregation_locks,
    _release_aggregation_locks,
    _active_org_ids,
    _aggregation_lock_keys,
    _pairs_the_rollup_would_lower,
    _rollup_monthly_from_daily,
    _run_aggregation,
    truncate_to_day,
    _truncate_to_hour,
    _truncate_to_month,
    _validate_source_window,
    aggregate_metrics_from_sources,
    cleanup_daily_metrics,
    cleanup_hourly_metrics,
)


class TestTimeHelpers(TestCase):
    """Tests for time truncation helper functions."""

    def test_truncate_to_hour_from_timestamp(self):
        """Test truncating a Unix timestamp to the hour."""
        # 2024-01-15 14:35:22 UTC
        timestamp = 1705329322.0
        result = _truncate_to_hour(timestamp)

        assert result.hour == 14
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0
        assert result.tzinfo == timezone.utc

    def test_truncate_to_hour_from_datetime(self):
        """Test truncating a datetime to the hour."""
        dt = datetime(2024, 1, 15, 14, 35, 22, tzinfo=timezone.utc)
        result = _truncate_to_hour(dt)

        assert result.hour == 14
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_truncate_to_hour_naive_datetime(self):
        """Test truncating a naive datetime makes it aware."""
        dt = datetime(2024, 1, 15, 14, 35, 22)
        result = _truncate_to_hour(dt)

        assert result.tzinfo is not None
        assert result.hour == 14
        assert result.minute == 0

    def testtruncate_to_day(self):
        """Test truncating a datetime to midnight."""
        dt = datetime(2024, 1, 15, 14, 35, 22, tzinfo=timezone.utc)
        result = truncate_to_day(dt)

        assert result.day == 15
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_truncate_to_month(self):
        """Test truncating a datetime to first day of month."""
        dt = datetime(2024, 1, 15, 14, 35, 22, tzinfo=timezone.utc)
        result = _truncate_to_month(dt)

        assert result.day == 1
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0


class TestCleanupTasks(TestCase):
    """Tests for cleanup tasks."""

    def setUp(self):
        """Set up test fixtures."""
        # organization FK targets Organization's int PK, not a UUID.
        self.org = Organization.objects.create(
            organization_id="test-org", name="test-org", display_name="Test Org"
        )

    def test_cleanup_hourly_metrics_deletes_old_records(self):
        """Test that cleanup deletes hourly records older than retention."""
        now = timezone.now()
        old_timestamp = now - timedelta(days=35)  # Older than 30 days
        recent_timestamp = now - timedelta(days=5)  # Within retention

        # Create old record
        EventMetricsHourly.objects.create(
            organization=self.org,
            timestamp=old_timestamp,
            metric_name="old_metric",
            metric_type=MetricType.COUNTER,
            metric_value=10,
            metric_count=1,
            project="default",
        )

        # Create recent record
        EventMetricsHourly.objects.create(
            organization=self.org,
            timestamp=recent_timestamp,
            metric_name="recent_metric",
            metric_type=MetricType.COUNTER,
            metric_value=20,
            metric_count=1,
            project="default",
        )

        result = cleanup_hourly_metrics(retention_days=30)

        assert result["success"] is True
        assert result["deleted"] == 1
        assert result["retention_days"] == 30

        # _base_manager bypasses the org-scoped default manager, which filters
        # by UserContext.get_organization() — None here, so .objects sees nothing.
        assert not EventMetricsHourly._base_manager.filter(
            metric_name="old_metric"
        ).exists()
        assert EventMetricsHourly._base_manager.filter(
            metric_name="recent_metric"
        ).exists()

    def test_cleanup_daily_metrics_deletes_old_records(self):
        """Test that cleanup deletes daily records older than retention."""
        now = timezone.now()
        old_date = (now - timedelta(days=400)).date()  # Older than 365 days
        recent_date = (now - timedelta(days=30)).date()  # Within retention

        # Create old record
        EventMetricsDaily.objects.create(
            organization=self.org,
            date=old_date,
            metric_name="old_daily_metric",
            metric_type=MetricType.COUNTER,
            metric_value=100,
            metric_count=10,
            project="default",
        )

        # Create recent record
        EventMetricsDaily.objects.create(
            organization=self.org,
            date=recent_date,
            metric_name="recent_daily_metric",
            metric_type=MetricType.COUNTER,
            metric_value=200,
            metric_count=20,
            project="default",
        )

        result = cleanup_daily_metrics(retention_days=365)

        assert result["success"] is True
        assert result["deleted"] == 1

        # Verify old is deleted, recent remains
        assert not EventMetricsDaily._base_manager.filter(
            metric_name="old_daily_metric"
        ).exists()
        assert EventMetricsDaily._base_manager.filter(
            metric_name="recent_daily_metric"
        ).exists()

    def test_cleanup_hourly_with_custom_retention(self):
        """Test cleanup with custom retention period."""
        now = timezone.now()
        old_timestamp = now - timedelta(days=10)

        EventMetricsHourly.objects.create(
            organization=self.org,
            timestamp=old_timestamp,
            metric_name="custom_retention_metric",
            metric_type=MetricType.COUNTER,
            metric_value=10,
            metric_count=1,
            project="default",
        )

        # With 7-day retention, the 10-day-old record should be deleted
        result = cleanup_hourly_metrics(retention_days=7)

        assert result["success"] is True
        assert result["deleted"] == 1

    def test_cleanup_no_records_to_delete(self):
        """Test cleanup when there are no old records."""
        result = cleanup_hourly_metrics(retention_days=30)

        assert result["success"] is True
        assert result["deleted"] == 0


class TestMonthlyRollup(TestCase):
    """Tests for deriving monthly metrics from the daily tier."""

    def setUp(self):
        """Set up test fixtures."""
        self.org = Organization.objects.create(
            organization_id="rollup-org", name="rollup-org", display_name="Rollup Org"
        )

    def _daily(
        self,
        day,
        value,
        count=1,
        metric_type=MetricType.COUNTER,
        metric_name="documents_processed",
        org=None,
    ):
        """Create a daily metric row, defaulting to the fixture org and metric."""
        EventMetricsDaily.objects.create(
            organization=org or self.org,
            date=day,
            metric_name=metric_name,
            metric_type=metric_type,
            metric_value=value,
            metric_count=count,
            project="default",
        )

    def _monthly_rows(self):
        """Read back monthly rows in a stable order."""
        return list(
            EventMetricsMonthly._base_manager.order_by(
                "month", "organization_id", "metric_name"
            )
        )

    def test_sums_daily_rows_into_month_bucket(self):
        """Daily rows within a month sum into a single monthly row."""
        self._daily(date(2024, 3, 5), value=10, count=2)
        self._daily(date(2024, 3, 18), value=32, count=4)

        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 1

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].month == date(2024, 3, 1)
        assert rows[0].metric_value == 42
        assert rows[0].metric_count == 6

    def test_month_boundary_keeps_months_separate(self):
        """Rows spanning the 1st land in two months without bleeding."""
        self._daily(date(2024, 1, 30), value=5)
        self._daily(date(2024, 1, 31), value=7)
        self._daily(date(2024, 2, 1), value=100)
        self._daily(date(2024, 2, 2), value=200)

        assert _rollup_monthly_from_daily(date(2024, 1, 1)) == 2

        rows = self._monthly_rows()
        assert [r.month for r in rows] == [date(2024, 1, 1), date(2024, 2, 1)]
        assert [r.metric_value for r in rows] == [12, 300]

    def test_excludes_months_before_the_window(self):
        """Daily rows older than month_start are not rolled up."""
        self._daily(date(2023, 12, 15), value=999)
        self._daily(date(2024, 1, 15), value=5)

        assert _rollup_monthly_from_daily(date(2024, 1, 1)) == 1

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].month == date(2024, 1, 1)

    def test_rerun_overwrites_instead_of_accumulating(self):
        """A second rollup replaces the monthly total rather than doubling it."""
        self._daily(date(2024, 3, 5), value=10, count=2)
        _rollup_monthly_from_daily(date(2024, 3, 1))

        self._daily(date(2024, 3, 6), value=5, count=1)
        _rollup_monthly_from_daily(date(2024, 3, 1))

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].metric_value == 15
        assert rows[0].metric_count == 3

    def test_mixed_metric_type_within_a_month_yields_one_row(self):
        """metric_type is aggregated, so it cannot split one conflict target."""
        self._daily(date(2024, 3, 5), value=10, metric_type=MetricType.HISTOGRAM)
        self._daily(date(2024, 3, 6), value=5, metric_type=MetricType.COUNTER)

        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 1

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].metric_value == 15

    def test_an_empty_daily_tier_leaves_existing_monthly_rows_alone(self):
        """An empty tier means the source is gone, not that every month is zero.

        Seeding a monthly row first is what makes the failure reachable at all: with
        an empty table an implementation that wipes and one that writes nothing both
        leave an empty table, and the assertion passes either way.
        """
        EventMetricsMonthly._base_manager.create(
            organization=self.org,
            month=date(2024, 3, 1),
            metric_name="documents_processed",
            metric_type=MetricType.COUNTER,
            metric_value=42,
            metric_count=6,
            project="default",
        )

        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 0

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].metric_value == 42

    def test_a_metric_whose_daily_rows_are_gone_keeps_its_last_total(self):
        """Upsert-only, per the design agreed on UN-3973.

        A stale total is recoverable — backfill_metrics rewrites it. A deleted row is
        not, because the daily rows that would rebuild it are exactly what is missing.
        """
        self._daily(date(2024, 3, 5), value=10)
        self._daily(date(2024, 3, 6), value=7, metric_name="pages_processed")
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 2

        EventMetricsDaily._base_manager.filter(metric_name="pages_processed").delete()
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 1

        rows = self._monthly_rows()
        assert [r.metric_name for r in rows] == ["documents_processed", "pages_processed"]

    def test_a_partially_repopulated_month_is_overwritten_not_accumulated(self):
        """The realistic post-downtime shape: the daily tier comes back short.

        The total tracks whatever the daily tier currently holds, so repairing daily
        repairs monthly on the next run — which is what makes upsert-only recoverable.
        """
        self._daily(date(2024, 3, 5), value=10)
        self._daily(date(2024, 3, 6), value=32)
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 1
        assert self._monthly_rows()[0].metric_value == 42

        EventMetricsDaily._base_manager.filter(date=date(2024, 3, 6)).delete()
        _rollup_monthly_from_daily(date(2024, 3, 1))
        assert self._monthly_rows()[0].metric_value == 10

        self._daily(date(2024, 3, 6), value=32)
        _rollup_monthly_from_daily(date(2024, 3, 1))
        assert self._monthly_rows()[0].metric_value == 42

    def test_rows_for_other_organizations_are_never_touched(self):
        """The rollup goes through _base_manager, bypassing the org-scoped default."""
        other = Organization.objects.create(
            organization_id="rollup-org-2", name="rollup-org-2", display_name="Other"
        )
        self._daily(date(2024, 3, 5), value=10)
        self._daily(date(2024, 3, 6), value=20, org=other)
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 2

        EventMetricsDaily._base_manager.filter(organization=other).delete()
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 1

        rows = self._monthly_rows()
        assert [(r.organization_id, r.metric_value) for r in rows] == [
            (self.org.id, 10),
            (other.id, 20),
        ]

    def test_months_before_the_window_are_left_alone(self):
        """A month before month_start is untouched by a later rollup."""
        self._daily(date(2024, 1, 10), value=99)
        _rollup_monthly_from_daily(date(2024, 1, 1))
        EventMetricsDaily._base_manager.all().delete()

        self._daily(date(2024, 3, 5), value=10)
        _rollup_monthly_from_daily(date(2024, 3, 1))

        months = [row.month for row in self._monthly_rows()]
        assert months == [date(2024, 1, 1), date(2024, 3, 1)]


class TestRollupQueryShape(TestCase):
    """The monthly rollup must not read the raw source tables."""

    def test_monthly_rollup_never_touches_source_tables(self):
        """This is the saving: monthly reads the daily tier and nothing else."""
        EventMetricsDaily._base_manager.create(
            organization=Organization.objects.create(
                organization_id="shape-org", name="shape", display_name="Shape"
            ),
            date=date(2024, 3, 5),
            metric_name="documents_processed",
            metric_type=MetricType.COUNTER,
            metric_value=10,
            metric_count=2,
            project="default",
            tag="",
        )

        with CaptureQueriesContext(connection) as captured:
            _rollup_monthly_from_daily(date(2024, 3, 1))

        sql = " ".join(q["sql"] for q in captured.captured_queries).lower()
        assert "event_metrics_daily" in sql
        for source_table in (
            "workflow_file_execution",
            "workflow_execution",
            "page_usage",
        ):
            assert source_table not in sql, f"monthly rollup read {source_table}"


class TestActiveOrgPrefilter(TestCase):
    """The prefilter must never be narrower than the window it is filtering for."""

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="prefilter-org", name="prefilter", display_name="Prefilter"
        )
        workflow = Workflow.objects.create(
            workflow_name="prefilter-wf", organization=self.org
        )
        self.now = timezone.now()
        execution = WorkflowExecution.objects.create(
            workflow_id=workflow.id, status=ExecutionStatus.COMPLETED
        )
        WorkflowExecution.objects.filter(pk=execution.pk).update(
            created_at=self.now - timedelta(days=10)
        )

    def test_an_org_outside_the_default_lookback_is_filtered_out(self):
        """The default lookback is the cheap case and stays exactly as wide as before."""
        window_start = self.now - timedelta(days=DASHBOARD_SOURCE_WINDOW_DAYS)
        assert self.org.id not in _active_org_ids(self.now, window_start)

    def test_a_widened_window_widens_the_prefilter_with_it(self):
        """Otherwise a long-outage repair queries 30 days for orgs active in 7, and
        reports errors: 0 having skipped every org it exists to repair.
        """
        window_start = self.now - timedelta(days=30)
        assert self.org.id in _active_org_ids(self.now, window_start)

    def test_the_floor_keeps_an_org_older_than_the_source_window(self):
        """The only region the DASHBOARD_ACTIVE_ORG_LOOKBACK_DAYS floor governs.

        Between the 2-day source window and the 7-day floor. The two cases above
        bracket it without covering it: at 10 days the org is outside both bounds,
        and the 30-day case pins only the window_start half of the min(). Drop the
        floor and every org whose last execution is 3-7 days old silently leaves the
        run — which is what the floor exists to prevent, since metrics keyed on
        another column (approved_at) still land for them.
        """
        stale_org = Organization.objects.create(
            organization_id="floor-org", name="floor", display_name="Floor"
        )
        workflow = Workflow.objects.create(
            workflow_name="floor-wf", organization=stale_org
        )
        execution = WorkflowExecution.objects.create(
            workflow_id=workflow.id, status=ExecutionStatus.COMPLETED
        )
        WorkflowExecution.objects.filter(pk=execution.pk).update(
            created_at=self.now - timedelta(days=5)
        )

        window_start = self.now - timedelta(days=DASHBOARD_SOURCE_WINDOW_DAYS)
        assert stale_org.id in _active_org_ids(self.now, window_start)


class TestMonthlyRollupFailurePosture(TestCase):
    """The rollup's errors must be counted, so success is False without a retry."""

    def test_a_database_error_is_counted_rather_than_raised(self):
        """Raising bought a retry on one transport and a dropped message on the other.

        On Celery the exception reaches autoretry_for and each attempt re-runs the
        whole aggregation — three more full passes in seconds, against a database
        that just reported it is struggling. On the internal-HTTP path Task.retry
        re-raises under called_directly, so nothing retries and MAX_ATTEMPTS=1 drops
        the message. Counting it sets success: False on both, which is the signal
        the raise was standing in for.
        """
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [1]
            with patch(
                "dashboard_metrics.tasks._rollup_monthly_from_daily",
                side_effect=DatabaseError("lock timeout"),
            ):
                result = _run_aggregation()

        assert result["success"] is False
        assert result["errors"] == 1
        assert result["monthly"]["failed"] is True

    def test_an_unexpected_error_is_counted_but_does_not_abort_the_run(self):
        """Everything outside the retry set stays non-fatal — the hourly and daily
        tiers this run already wrote are kept — but it is not reported as success.
        """
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [1]
            with patch(
                "dashboard_metrics.tasks._rollup_monthly_from_daily",
                side_effect=ValueError("bad row"),
            ):
                result = _run_aggregation()
        assert result["success"] is False
        assert result["errors"] == 1
        assert result["monthly"]["failed"] is True


class TestInternalAggregateEndpoint(TestCase):
    """The PG transport reaches the task through this view, not through Celery."""

    def _post(self, data):
        return AggregateMetricsAPIView().post(SimpleNamespace(data=data))

    def test_the_source_window_reaches_the_task(self):
        with patch(
            "dashboard_metrics.internal_views.aggregate_metrics_from_sources",
            return_value={"success": True},
        ) as task:
            self._post({"source_window_days": 7})
        assert task.call_args.kwargs == {"source_window_days": 7}

    def test_omitting_it_leaves_the_task_default_in_charge(self):
        with patch(
            "dashboard_metrics.internal_views.aggregate_metrics_from_sources",
            return_value={"success": True},
        ) as task:
            self._post({})
        assert task.call_args.kwargs == {}

    def test_an_unrecognised_body_key_is_a_400(self):
        """Ignored, it answered 200 having run every tier at the default window.

        `{"teir": ...}` is the realistic shape — a hand-run repair during an
        incident, answered as though it did what was asked.
        """
        with patch(
            "dashboard_metrics.internal_views.aggregate_metrics_from_sources"
        ) as task:
            response = self._post({"teir": "hourly"})
        assert response.status_code == 400
        task.assert_not_called()

    def test_a_window_over_the_maximum_is_a_400(self):
        """The bound this diff added at the boundary.

        Without it the value reaches the task, whose own ValueError is no longer
        mapped to a 400 — so an over-wide window becomes a logged 500, the exact
        inversion moving validation to the boundary was for.
        """
        with patch(
            "dashboard_metrics.internal_views.aggregate_metrics_from_sources"
        ) as task:
            response = self._post({"source_window_days": 365})
        assert response.status_code == 400
        task.assert_not_called()

    def test_a_non_integer_window_is_a_400(self):
        with patch(
            "dashboard_metrics.internal_views.aggregate_metrics_from_sources"
        ) as task:
            response = self._post({"source_window_days": "seven"})
        assert response.status_code == 400
        task.assert_not_called()


class TestMonthlyThroughTheTask(TestCase):
    """The rollup as the task actually runs it, not via the helper directly.

    Every other rollup test calls ``_rollup_monthly_from_daily`` with a hand-chosen
    ``month_start``. Nothing exercised the arithmetic that computes it, nor the sweep
    running against a monthly table that already holds rows from earlier runs — so a
    regression to "first of the current month" would silently drop last month's rows
    with the whole rollup suite still green.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="entry-org", name="entry-org", display_name="Entry Org"
        )
        self.now = timezone.now()
        now = self.now
        self.this_month = _truncate_to_month(now).date()
        self.last_month = _truncate_to_month(
            _truncate_to_month(now) - timedelta(days=1)
        ).date()
        self.before_window = _truncate_to_month(
            _truncate_to_month(now - timedelta(days=1)) - timedelta(days=40)
        ).date()

    def _daily(self, day, value, metric_name="documents_processed"):
        EventMetricsDaily._base_manager.create(
            organization=self.org,
            date=day,
            metric_name=metric_name,
            metric_type=MetricType.COUNTER,
            metric_value=value,
            metric_count=1,
            project="default",
            tag="",
        )

    def _monthly(self, month, value, metric_name="documents_processed"):
        EventMetricsMonthly._base_manager.create(
            organization=self.org,
            month=month,
            metric_name=metric_name,
            metric_type=MetricType.COUNTER,
            metric_value=value,
            metric_count=1,
            project="default",
            tag="",
        )

    def _run(self, **kwargs):
        # setUp derives this_month/last_month from one clock reading; the run must
        # use the same one, or a run straddling a month boundary fails on the 1st.
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            with patch("dashboard_metrics.tasks.timezone.now", return_value=self.now):
                return _run_aggregation(**kwargs)

    def test_the_window_covers_the_previous_month_and_spares_what_precedes_it(self):
        """monthly_start is the first of the *previous* month, and the sweep stops there."""
        self._daily(self.this_month, value=10)
        self._daily(self.last_month, value=20)
        self._monthly(self.before_window, value=999)

        result = self._run()

        assert result["period"]["monthly"]["start"] == self.last_month.isoformat()
        assert result["monthly"]["upserted"] == 2
        assert result["monthly"]["failed"] is False
        # A correct rollup lowers nothing, so it says nothing. The detector fires on
        # a total that actually fell, not on a calendar heuristic that would flag an
        # idle day or a fresh install as damage.
        assert "lowered_months" not in result["monthly"]

        rows = EventMetricsMonthly._base_manager.order_by("month")
        assert [r.month for r in rows] == [
            self.before_window,
            self.last_month,
            self.this_month,
        ]

    def test_a_failed_rollup_is_not_reported_as_nothing_to_do(self):
        """Upserted stays 0 on failure, which is also the legitimate empty value.

        Three states used to collapse into one alongside success: True — failed,
        empty, and no active orgs.
        """
        self._daily(self.this_month, value=10)
        with patch(
            "dashboard_metrics.tasks._rollup_monthly_from_daily",
            side_effect=ValueError("bad row"),
        ):
            result = self._run()

        assert result["monthly"] == {"upserted": 0, "failed": True}
        assert result["success"] is False


class TestMonthlyMatchesTheOldDerivation(TestCase):
    """AC-4: the new monthly figures equal the ones the source queries produced.

    Every other monthly test feeds hand-written daily rows in and checks the sum of
    what it just wrote — self-consistency, not equivalence. This one seeds *source*
    rows, lets the real aggregation populate the daily tier from them, and compares
    the rolled-up monthly against the pre-change derivation computed independently:
    `get_documents_processed` at DAY granularity, bucketed by month in Python.

    The window is deliberately wide enough to cover both months, which is the state
    `backfill_metrics` establishes before this change is deployed.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="golden-org", name="golden-org", display_name="Golden Org"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="golden-wf", organization=self.org
        )
        # Offsets are derived from the month boundary, never fixed day counts: on the
        # 25th of a month a hardcoded "25 days ago" lands in the current month and the
        # cross-boundary coverage silently disappears.
        # One clock reading for setUp, _seed and the run: three separate ones put
        # the seeds and the window in different months across a boundary.
        self.now = timezone.now()
        now = self.now
        first_of_this_month = _truncate_to_month(now)
        self.days_to_last_month_end = (now - first_of_this_month).days + 1
        self.days_to_last_month_start = (
            now - _truncate_to_month(first_of_this_month - timedelta(days=1))
        ).days

    def _seed(self, days_ago: int, count: int) -> None:
        """Seed `count` completed file executions dated `days_ago`."""
        stamp = self.now - timedelta(days=days_ago)
        for n in range(count):
            execution = WorkflowExecution.objects.create(
                workflow=self.workflow, status=ExecutionStatus.COMPLETED
            )
            file_execution = WorkflowFileExecution.objects.create(
                workflow_execution=execution,
                file_name=f"{days_ago}-{n}.pdf",
                status=ExecutionStatus.COMPLETED.value,
            )
            WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
                created_at=stamp
            )
            WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)

    def _written(self) -> dict:
        """Monthly totals as the rollup wrote them."""
        return {
            row.month: row.metric_value
            for row in EventMetricsMonthly._base_manager.filter(
                metric_name="documents_processed"
            )
        }

    def _oracle(self, monthly_start, end_date) -> dict:
        """Monthly totals the way the code derived them before this change."""
        rows = MetricsQueryService.get_documents_processed(
            organization_id=str(self.org.id),  # tasks.py passes the numeric PK
            start_date=monthly_start,
            end_date=end_date,
            granularity=Granularity.DAY,
        )
        totals: dict = {}
        for row in rows:
            month = _truncate_to_month(row["period"]).date()
            totals[month] = totals.get(month, 0) + row["value"]
        return totals

    def test_monthly_equals_the_pre_change_figures_across_a_month_boundary(self):
        self._seed(days_ago=0, count=3)
        self._seed(days_ago=self.days_to_last_month_end, count=2)
        self._seed(days_ago=self.days_to_last_month_start, count=4)

        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            with patch("dashboard_metrics.tasks.timezone.now", return_value=self.now):
                result = _run_aggregation(
                    source_window_days=self.days_to_last_month_start + 1
                )

        monthly_start = date.fromisoformat(result["period"]["monthly"]["start"])
        end_date = datetime.fromisoformat(result["period"]["monthly"]["end"])
        expected = self._oracle(
            datetime.combine(monthly_start, datetime.min.time(), tzinfo=end_date.tzinfo),
            end_date,
        )

        assert len(expected) == 2, f"fixture must straddle a month boundary: {expected}"
        assert self._written() == expected

    def test_the_comparison_can_fail_when_the_daily_tier_is_wrong(self):
        """Guards the test above: an oracle that always matches proves nothing.

        Monthly is the sum of whatever the daily tier holds, so corrupting a day has
        to move the monthly total away from the source-derived figure. Corrupting
        rather than deleting is the point — deleting a day leaves the group in place
        with a smaller sum, so it would move the total too and could not distinguish
        a working oracle from a broken one. (Only an *entirely* absent month leaves
        the previous monthly row untouched; that case is covered by TestMonthlyRollup.)
        """
        self._seed(days_ago=0, count=3)
        self._seed(days_ago=self.days_to_last_month_end, count=2)

        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            with patch("dashboard_metrics.tasks.timezone.now", return_value=self.now):
                result = _run_aggregation(
                    source_window_days=self.days_to_last_month_start + 1
                )

        monthly_start = date.fromisoformat(result["period"]["monthly"]["start"])
        end_date = datetime.fromisoformat(result["period"]["monthly"]["end"])
        expected = self._oracle(
            datetime.combine(monthly_start, datetime.min.time(), tzinfo=end_date.tzinfo),
            end_date,
        )
        assert self._written() == expected

        last_month_day = (
            self.now - timedelta(days=self.days_to_last_month_end)
        ).date()
        corrupted = EventMetricsDaily._base_manager.filter(
            date=last_month_day, metric_name="documents_processed"
        ).update(metric_value=99)
        assert corrupted, "fixture wrote no daily row for the previous month"

        _rollup_monthly_from_daily(monthly_start)
        assert self._written() != expected


# Same rationale as test_aggregation_tier.py: the lock protocol needs a cache, not a
# server, and cache.clear() on django_redis is a whole-database FLUSHDB.
_LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "aggregation-lock-window-tests",
    }
}


class TestTheLockIsPerSchedule(TestCase):
    """The reconciliation pass must not lose a race it is never retried after.

    Per-granularity exclusion is covered in test_aggregation_tier.py; this is the
    window half — two schedules that both write the daily/monthly tier.
    """

    def setUp(self):
        # Pinned to locmem: cache.clear() is FLUSHDB on django_redis, which would wipe
        # every key in that database — the Celery broker shares db 0 in the test env —
        # and these keys are un-namespaced, so parallel workers would clear each
        # other's. The lock protocol only needs add/get/delete.
        override = override_settings(CACHES=_LOCMEM_CACHE)
        override.enable()
        self.addCleanup(override.disable)
        cache.clear()
        self.addCleanup(cache.clear)

    def _keys(self, window):
        return _aggregation_lock_keys(AggregationTier.ALL, window)

    def test_the_two_schedules_take_different_keys(self):
        assert self._keys(DASHBOARD_SOURCE_WINDOW_DAYS) != self._keys(
            DASHBOARD_RECONCILE_WINDOW_DAYS
        )

    def test_a_held_key_does_not_block_the_other_schedule(self):
        assert _acquire_aggregation_locks(self._keys(DASHBOARD_SOURCE_WINDOW_DAYS))[0]
        # Same schedule: excluded, which is what the lock is for.
        assert not _acquire_aggregation_locks(self._keys(DASHBOARD_SOURCE_WINDOW_DAYS))[0]
        # The reconciliation pass proceeds regardless.
        assert _acquire_aggregation_locks(self._keys(DASHBOARD_RECONCILE_WINDOW_DAYS))[0]


class TestSourceWindowValidation(TestCase):
    """The window arrives as JSON from a Beat row editable in the admin."""

    def test_a_sane_window_passes_through(self):
        assert _validate_source_window(7) == 7
        assert _validate_source_window("7") == 7

    def test_a_window_that_would_query_nothing_is_rejected(self):
        # Negative puts daily_start in the future; 0 never refreshes yesterday.
        for bad in (-1, 0):
            with self.assertRaises(ValueError):
                _validate_source_window(bad)

    def test_a_window_that_restores_the_multi_month_scan_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_source_window(365)

    def test_a_non_integer_window_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_source_window("seven")


class TestSourceWindow(TestCase):
    """Tests for the per-run source window and the reconciliation pass."""

    def setUp(self):
        """Set up test fixtures."""
        self.org = Organization.objects.create(
            organization_id="window-org", name="window-org", display_name="Window Org"
        )
        self.now = timezone.now()

    def _run_with_active_org(self, **kwargs):
        """Run aggregation with the active-org prefilter stubbed to the fixture org.

        The clock is frozen to self.now so the run and the test's own expectation
        derive from one reading. Unpinned, a run straddling midnight UTC truncates
        to two different days and the assertion fails on no code change.
        """
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            with patch("dashboard_metrics.tasks.timezone.now", return_value=self.now):
                return _run_aggregation(**kwargs)

    def test_default_window_bounds_the_daily_query(self):
        """The per-run daily window is DASHBOARD_SOURCE_WINDOW_DAYS wide."""
        result = self._run_with_active_org()

        expected = truncate_to_day(
            self.now - timedelta(days=DASHBOARD_SOURCE_WINDOW_DAYS)
        )
        assert result["period"]["daily"]["start"] == expected.isoformat()

    def test_reconciliation_window_widens_the_daily_query(self):
        """The reconciliation pass reaches further back on the same code path."""
        result = self._run_with_active_org(
            source_window_days=DASHBOARD_RECONCILE_WINDOW_DAYS
        )

        expected = truncate_to_day(
            self.now - timedelta(days=DASHBOARD_RECONCILE_WINDOW_DAYS)
        )
        assert result["period"]["daily"]["start"] == expected.isoformat()

    def test_task_passes_the_window_through(self):
        """The scheduled task forwards its kwarg, defaulting to the per-run window.

        The lock is patched out: acquiring it for real takes — and then releases in the
        task's ``finally`` — the shared Redis key a live local aggregation may be
        holding.
        """
        with (
            patch("dashboard_metrics.tasks._acquire_aggregation_lock", return_value=True),
            patch("dashboard_metrics.tasks.cache"),
            patch("dashboard_metrics.tasks._run_aggregation") as mock_run,
        ):
            aggregate_metrics_from_sources()
            mock_run.assert_called_once_with(
                AggregationTier.ALL, DASHBOARD_SOURCE_WINDOW_DAYS
            )

        with (
            patch("dashboard_metrics.tasks._acquire_aggregation_lock", return_value=True),
            patch("dashboard_metrics.tasks.cache"),
            patch("dashboard_metrics.tasks._run_aggregation") as mock_run,
        ):
            aggregate_metrics_from_sources(source_window_days=7)
            mock_run.assert_called_once_with(AggregationTier.ALL, 7)

    def _seed_file(
        self, days_ago: int, status: ExecutionStatus = ExecutionStatus.COMPLETED
    ) -> date:
        """Seed one file execution dated days_ago, return its date."""
        workflow = Workflow.objects.create(
            workflow_name=f"recon-wf-{days_ago}", organization=self.org
        )
        execution = WorkflowExecution.objects.create(
            workflow=workflow, status=ExecutionStatus.COMPLETED
        )
        file_execution = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name="a.pdf",
            status=status.value,
        )

        stamp = timezone.now() - timedelta(days=days_ago)
        # created_at is auto_now_add; a queryset update is what bypasses it
        WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
            created_at=stamp
        )
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=stamp)
        return stamp.date()

    def test_reconciliation_recovers_a_day_the_narrow_window_missed(self):
        """A row outside the per-run window is picked up by the wider pass."""
        day = self._seed_file(days_ago=5)

        _run_aggregation()
        assert not EventMetricsDaily._base_manager.filter(date=day).exists()

        result = _run_aggregation(source_window_days=DASHBOARD_RECONCILE_WINDOW_DAYS)

        row = EventMetricsDaily._base_manager.get(
            date=day, metric_name="documents_processed"
        )
        assert row.metric_value == 1
        assert result["errors"] == 0

    def test_late_terminal_status_does_not_re_enter_the_narrow_window(self):
        """Finishing after the window moved on does not bring a row back."""
        day = self._seed_file(days_ago=3, status=ExecutionStatus.PENDING)

        # Still running: nothing to count yet.
        _run_aggregation()
        assert not EventMetricsDaily._base_manager.filter(date=day).exists()

        # It finishes. status turns terminal; created_at does not move.
        WorkflowFileExecution.objects.update(status=ExecutionStatus.COMPLETED.value)

        # The per-run window no longer reaches its created_at, so it stays missed.
        _run_aggregation()
        assert not EventMetricsDaily._base_manager.filter(date=day).exists()

        # Only the wider pass recovers it.
        _run_aggregation(source_window_days=DASHBOARD_RECONCILE_WINDOW_DAYS)
        assert EventMetricsDaily._base_manager.filter(
            date=day, metric_name="documents_processed"
        ).exists()

    def test_gap_older_than_the_reconcile_window_needs_a_manual_backfill(self):
        """Neither scheduled pass reaches a day beyond the reconcile window."""
        old_day = self._seed_file(days_ago=62)
        recent_day = self._seed_file(days_ago=0)

        _run_aggregation()
        _run_aggregation(source_window_days=DASHBOARD_RECONCILE_WINDOW_DAYS)

        # The run worked — it just cannot reach that far back.
        assert EventMetricsDaily._base_manager.filter(date=recent_day).exists()
        assert not EventMetricsDaily._base_manager.filter(date=old_day).exists()


class TestReconciliationSchedule(TestCase):
    """Migration 0005 schedules the once-daily reconciliation pass on both transports.

    The suite runs with --no-migrations, so the migration's function is called
    directly rather than relying on it having been applied.
    """

    def setUp(self):
        """Load the data migration module."""
        self.migration = import_module(
            "dashboard_metrics.migrations.0005_add_reconciliation_task"
        )

    def _task(self):
        return PeriodicTask.objects.get(name=self.migration.RECONCILE_TASK_NAME)

    def test_migration_schedules_the_pass_at_0440_with_a_7_day_window(self):
        """The beat row lands enabled, at 04:40 UTC, carrying the wider window."""
        self.migration.create_reconciliation_task(apps, None)

        task = self._task()
        assert task.task == "dashboard_metrics.aggregate_from_sources"
        assert task.enabled
        assert task.queue == "dashboard_metric_events"
        # The tier is part of the row: without it the pass runs ALL, and its hourly
        # half both duplicates the */15 run's work and is the only thing writing
        # event_metrics_hourly concurrently with it.
        assert json.loads(task.kwargs) == {
            "source_window_days": DASHBOARD_RECONCILE_WINDOW_DAYS,
            "tier": "daily_monthly",
        }
        assert (task.crontab.hour, task.crontab.minute) == ("4", "40")

    def test_the_pg_twin_lands_with_the_same_cadence_and_kwargs(self):
        """A Beat-only row stops firing the moment the PG scheduler takes over."""
        self.migration.create_reconciliation_task(apps, None)

        row = PgPeriodicTask.objects.get(name=self.migration.RECONCILE_TASK_NAME)
        assert row.task_name == "dashboard_metrics.aggregate_from_sources"
        assert row.queue == "dashboard_metric_events"
        assert row.cron_string == "40 4 * * *"
        assert row.task_kwargs == {
            "source_window_days": DASHBOARD_RECONCILE_WINDOW_DAYS,
            "tier": "daily_monthly",
        }
        assert row.enabled
        # Inert until the rollout flag decides otherwise.
        assert not row.pg_owned
        assert row.next_run_at is None

    def test_a_running_beat_is_told_to_reload(self):
        """Historical models fire no post_save, so the tracker has to be bumped by hand.

        Without it a live Beat never adopts the new schedule and the reconciliation
        pass simply never runs — no error, nothing logged.
        """
        before = timezone.now()
        self.migration.create_reconciliation_task(apps, None)

        tracker = PeriodicTasks.objects.get(ident=1)
        assert tracker.last_update >= before

    def test_migration_is_idempotent_and_reversible(self):
        """Re-running leaves one row; the reverse function removes it."""
        self.migration.create_reconciliation_task(apps, None)
        self.migration.create_reconciliation_task(apps, None)

        assert (
            PeriodicTask.objects.filter(name=self.migration.RECONCILE_TASK_NAME).count()
            == 1
        )

        self.migration.remove_reconciliation_task(apps, None)
        assert not PeriodicTask.objects.filter(
            name=self.migration.RECONCILE_TASK_NAME
        ).exists()
        assert not PgPeriodicTask.objects.filter(
            name=self.migration.RECONCILE_TASK_NAME
        ).exists()


class TestALoweredTotalIsReported(TestCase):
    """The damage is per-tenant, so the detector has to be.

    A fleet-wide date count cannot see this: one org covers every date while
    another loses one, so no date is globally missing and nothing fires — while
    the second org's monthly total is rewritten downward and served to its
    dashboard. `_collect_org_metrics` catches a failing metric per organization
    and continues, so a query fault on one tenant produces exactly this shape,
    and the 2-day source window makes it permanent two days later.
    """

    def setUp(self):
        self.covered = Organization.objects.create(
            organization_id="covered-org", name="covered", display_name="Covered"
        )
        self.short = Organization.objects.create(
            organization_id="short-org", name="short", display_name="Short"
        )
        self.month = _truncate_to_month(timezone.now()).date()

    def _daily(self, org, day, value):
        EventMetricsDaily._base_manager.create(
            organization=org,
            date=day,
            metric_name="documents_processed",
            metric_type=MetricType.COUNTER,
            metric_value=value,
            metric_count=1,
            project="default",
            tag="",
        )

    def _monthly(self, org, value):
        EventMetricsMonthly._base_manager.create(
            organization=org,
            month=self.month,
            metric_name="documents_processed",
            metric_type=MetricType.COUNTER,
            metric_value=value,
            metric_count=2,
            project="default",
            tag="",
        )

    def test_one_tenant_losing_a_day_is_named_while_the_other_is_not(self):
        # Both orgs previously totalled 80. Only `short` lost a day of daily rows.
        self._monthly(self.covered, value=80)
        self._monthly(self.short, value=80)
        self._daily(self.covered, self.month, value=40)
        self._daily(self.covered, self.month + timedelta(days=1), value=40)
        self._daily(self.short, self.month, value=70)

        lowered = _pairs_the_rollup_would_lower(self.month)
        _rollup_monthly_from_daily(self.month, skip=set(lowered))

        assert lowered == [(self.short.id, self.month)]

        short_row = EventMetricsMonthly._base_manager.get(organization=self.short)
        covered_row = EventMetricsMonthly._base_manager.get(organization=self.covered)
        # Kept, not overwritten: writing 70 would replace a correct figure with a
        # known-short one just because the daily tier has not been repaired yet.
        assert short_row.metric_value == 80
        assert covered_row.metric_value == 80

    def test_a_tier_that_covers_everything_reports_nothing(self):
        """The control: no total fell, so no warning — however few days are seeded."""
        self._monthly(self.covered, value=40)
        self._daily(self.covered, self.month, value=40)

        assert _pairs_the_rollup_would_lower(self.month) == []
        _rollup_monthly_from_daily(self.month)


class TestTheUnderCountCheckIsBounded(TestCase):
    """The check must not scale with tenant x metric x project x tag.

    An earlier version snapshotted every monthly row into a dict before the rollup
    and read them all again afterwards — comparing the right thing on the axis the
    streaming rollup exists to keep off the heap. This pins the replacement: one
    statement, evaluated in the database, returning only offending pairs.
    """

    def setUp(self):
        self.month = _truncate_to_month(timezone.now()).date()
        for n in range(12):
            org = Organization.objects.create(
                organization_id=f"bounded-{n}", name=f"b{n}", display_name=f"B{n}"
            )
            for metric in ("documents_processed", "pages_processed", "llm_calls"):
                EventMetricsDaily._base_manager.create(
                    organization=org,
                    date=self.month,
                    metric_name=metric,
                    metric_type=MetricType.COUNTER,
                    metric_value=5,
                    metric_count=1,
                    project="default",
                    tag="",
                )
                EventMetricsMonthly._base_manager.create(
                    organization=org,
                    month=self.month,
                    metric_name=metric,
                    metric_type=MetricType.COUNTER,
                    metric_value=5,
                    metric_count=1,
                    project="default",
                    tag="",
                )

    def test_it_costs_one_query_regardless_of_tenant_count(self):
        with CaptureQueriesContext(connection) as captured:
            assert _pairs_the_rollup_would_lower(self.month) == []
        assert len(captured.captured_queries) == 1, (
            "the under-count check should be a single database-side comparison, "
            f"got {len(captured.captured_queries)}:\n"
            + "\n\n".join(q["sql"] for q in captured.captured_queries)
        )

    def test_it_does_not_select_every_monthly_row(self):
        """36 rows exist; the check must return only what is wrong, which is none."""
        with CaptureQueriesContext(connection) as captured:
            _pairs_the_rollup_would_lower(self.month)
        sql = captured.captured_queries[0]["sql"]
        assert "metric_value" in sql and "<" in sql, (
            "the comparison is not happening in the database:\n" + sql
        )


class TestTheDiagnosticCannotBlockTheRollup(TestCase):
    """The under-count check is a diagnostic; the rollup is the job.

    This regressed once already. It was fixed by giving the diagnostic its own
    try, then reintroduced while making the check a single database query — with
    no test to catch it. Hence this one.
    """

    def _run(self, **patches):
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [1]
            with patch(
                "dashboard_metrics.tasks._pairs_the_rollup_would_lower",
                side_effect=DatabaseError("diagnostic exploded"),
            ):
                return _run_aggregation(**patches)

    def test_a_failing_diagnostic_still_lets_the_rollup_run(self):
        with patch(
            "dashboard_metrics.tasks._rollup_monthly_from_daily", return_value=7
        ) as rollup:
            result = self._run()

        rollup.assert_called_once()
        assert result["monthly"]["upserted"] == 7

    def test_a_failing_diagnostic_is_not_reported_as_a_failed_rollup(self):
        """Otherwise the run contradicts itself: upserted 7, failed True."""
        with patch("dashboard_metrics.tasks._rollup_monthly_from_daily", return_value=7):
            result = self._run()

        assert result["monthly"]["failed"] is False
        assert result["errors"] == 0
        assert result["success"] is True


class TestTheLockIsReleasedOnlyByItsOwner(TestCase):
    """The ownership check had no test; deleting it left the suite green.

    Without it a run whose lock had already expired deletes whichever run took the
    key next, so two runs write the same tier and a third is free to enter.
    """

    def setUp(self):
        override = override_settings(CACHES=_LOCMEM_CACHE)
        override.enable()
        self.addCleanup(override.disable)
        cache.clear()
        self.addCleanup(cache.clear)
        self.key = _aggregation_lock_keys(AggregationTier.HOURLY, 2)[0]

    def test_a_stale_owner_does_not_release_the_current_holder(self):
        cache.set(self.key, f"newer-run:{time.time()}", 3600)

        _release_aggregation_locks([self.key], "older-run")

        assert cache.get(self.key) is not None, (
            "a run that no longer owns the key deleted the current holder's lock"
        )

    def test_the_owner_does_release_its_own_key(self):
        """The control: ownership gates the delete, it does not disable it."""
        assert _acquire_aggregation_lock(self.key, "mine")
        _release_aggregation_locks([self.key], "mine")
        assert cache.get(self.key) is None


class TestTheRunSurfacesWhatTheDiagnosticFound(TestCase):
    """The leg between the diagnostic and the result dict was untested on both sides.

    One test called the helper directly; another asserted against a hand-built
    payload. Neither observed the assignment, so dropping it left the suite green.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            organization_id="surface-org", name="surface", display_name="Surface"
        )
        self.month = _truncate_to_month(timezone.now()).date()

    def _run(self, **kwargs):
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            return _run_aggregation(**kwargs)

    def test_a_lowered_total_reaches_the_result_dict(self):
        EventMetricsMonthly._base_manager.create(
            organization=self.org, month=self.month,
            metric_name="documents_processed", metric_type=MetricType.COUNTER,
            metric_value=999, metric_count=1, project="default", tag="",
        )
        EventMetricsDaily._base_manager.create(
            organization=self.org, date=self.month,
            metric_name="documents_processed", metric_type=MetricType.COUNTER,
            metric_value=1, metric_count=1, project="default", tag="",
        )

        result = self._run(tier=AggregationTier.DAILY_MONTHLY)

        assert result["monthly"]["lowered_months"], (
            "the rollup lowered a total and the result dict did not say so"
        )

    def test_a_failed_check_is_reported_as_unavailable_not_as_clean(self):
        """`[]` alone would read as 'checked, nothing lowered'."""
        with patch(
            "dashboard_metrics.tasks._pairs_the_rollup_would_lower",
            side_effect=DatabaseError("diagnostic exploded"),
        ):
            result = self._run(tier=AggregationTier.DAILY_MONTHLY)

        assert result["monthly"]["lowered_check"] == "unavailable"
        assert "lowered_months" not in result["monthly"]
