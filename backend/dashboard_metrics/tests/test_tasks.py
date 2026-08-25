"""Unit tests for Dashboard Metrics Celery tasks."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from account_v2.models import Organization
from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    MetricType,
)
from dashboard_metrics.tasks import (
    DASHBOARD_RECONCILE_WINDOW_DAYS,
    DASHBOARD_SOURCE_WINDOW_DAYS,
    _rollup_monthly_from_daily,
    _run_aggregation,
    _truncate_to_day,
    _truncate_to_hour,
    _truncate_to_month,
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

    def test_truncate_to_day(self):
        """Test truncating a datetime to midnight."""

        dt = datetime(2024, 1, 15, 14, 35, 22, tzinfo=timezone.utc)
        result = _truncate_to_day(dt)

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
        assert not EventMetricsHourly._base_manager.filter(metric_name="old_metric").exists()
        assert EventMetricsHourly._base_manager.filter(metric_name="recent_metric").exists()

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

    def _daily(self, day, value, count=1, metric_type=MetricType.COUNTER):
        """Create a daily metric row for the fixture org."""
        EventMetricsDaily.objects.create(
            organization=self.org,
            date=day,
            metric_name="documents_processed",
            metric_type=metric_type,
            metric_value=value,
            metric_count=count,
            project="default",
        )

    def _monthly_rows(self):
        """Read back monthly rows ordered by month."""
        return list(EventMetricsMonthly._base_manager.order_by("month"))

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

    def test_no_daily_rows_upserts_nothing(self):
        """An empty daily tier is a no-op, not an error."""
        assert _rollup_monthly_from_daily(date(2024, 3, 1)) == 0
        assert not self._monthly_rows()

    def test_monthly_row_is_dropped_once_its_daily_rows_are_gone(self):
        """A month whose daily rows were deleted must not keep a stale total."""
        self._daily(date(2024, 3, 5), value=10)
        self._daily(date(2024, 4, 5), value=7)
        _rollup_monthly_from_daily(date(2024, 3, 1))
        assert len(self._monthly_rows()) == 2

        EventMetricsDaily._base_manager.filter(date=date(2024, 3, 5)).delete()
        _rollup_monthly_from_daily(date(2024, 3, 1))

        rows = self._monthly_rows()
        assert len(rows) == 1
        assert rows[0].month == date(2024, 4, 1)

    def test_months_before_the_window_are_left_alone(self):
        """Orphan cleanup must not reach outside the rebuilt window."""
        self._daily(date(2024, 1, 10), value=99)
        _rollup_monthly_from_daily(date(2024, 1, 1))
        EventMetricsDaily._base_manager.all().delete()

        self._daily(date(2024, 3, 5), value=10)
        _rollup_monthly_from_daily(date(2024, 3, 1))

        months = [row.month for row in self._monthly_rows()]
        assert months == [date(2024, 1, 1), date(2024, 3, 1)]


class TestSourceWindow(TestCase):
    """Tests for the per-run source window and the reconciliation pass."""

    def setUp(self):
        """Set up test fixtures."""
        self.org = Organization.objects.create(
            organization_id="window-org", name="window-org", display_name="Window Org"
        )

    def _run_with_active_org(self, **kwargs):
        """Run aggregation with the active-org prefilter stubbed to the fixture org."""
        with patch("dashboard_metrics.tasks.WorkflowExecution") as mock_execution:
            prefilter = mock_execution.objects.filter.return_value
            prefilter.values_list.return_value.distinct.return_value = [self.org.id]
            return _run_aggregation(**kwargs)

    def test_default_window_bounds_the_daily_query(self):
        """The per-run daily window is DASHBOARD_SOURCE_WINDOW_DAYS wide."""
        result = self._run_with_active_org()

        expected = _truncate_to_day(
            timezone.now() - timedelta(days=DASHBOARD_SOURCE_WINDOW_DAYS)
        )
        assert result["period"]["daily"]["start"] == expected.isoformat()

    def test_reconciliation_window_widens_the_daily_query(self):
        """The reconciliation pass reaches further back on the same code path."""
        result = self._run_with_active_org(
            source_window_days=DASHBOARD_RECONCILE_WINDOW_DAYS
        )

        expected = _truncate_to_day(
            timezone.now() - timedelta(days=DASHBOARD_RECONCILE_WINDOW_DAYS)
        )
        assert result["period"]["daily"]["start"] == expected.isoformat()

    def test_task_passes_the_window_through(self):
        """The scheduled task forwards its kwarg, defaulting to the per-run window."""
        with patch("dashboard_metrics.tasks._run_aggregation") as mock_run:
            aggregate_metrics_from_sources()
            mock_run.assert_called_once_with(DASHBOARD_SOURCE_WINDOW_DAYS)

        with patch("dashboard_metrics.tasks._run_aggregation") as mock_run:
            aggregate_metrics_from_sources(source_window_days=7)
            mock_run.assert_called_once_with(7)
