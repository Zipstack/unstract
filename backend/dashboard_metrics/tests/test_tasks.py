"""Unit tests for Dashboard Metrics Celery tasks."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    MetricType,
)
from dashboard_metrics.tasks import (
    _bulk_upsert_daily,
    _bulk_upsert_hourly,
    _bulk_upsert_monthly,
    _truncate_to_day,
    _truncate_to_hour,
    _truncate_to_month,
    cleanup_daily_metrics,
    cleanup_hourly_metrics,
    process_dashboard_metric_events,
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


class TestBatchProcessing(TransactionTestCase):
    """Tests for batch processing task."""

    def setUp(self):
        """Set up test fixtures."""
        self.org_id = str(uuid.uuid4())
        self.base_timestamp = timezone.now().timestamp()

    def test_empty_batch_returns_zero(self):
        """Test that an empty batch returns zero processed."""
        result = process_dashboard_metric_events([])

        assert result == {"processed": 0, "errors": 0}

    def test_single_event_creates_records(self):
        """Test that a single event creates records in all three tables."""
        mock_request = MagicMock()
        mock_request.args = [
            {
                "org_id": self.org_id,
                "metric_name": "test_metric",
                "metric_value": 10,
                "metric_type": MetricType.COUNTER,
                "timestamp": self.base_timestamp,
                "labels": {"source": "test"},
                "project": "default",
                "tag": None,
            }
        ]
        mock_request.kwargs = {}

        result = process_dashboard_metric_events([mock_request])

        assert result["processed"] == 1
        assert result["errors"] == 0

        # Verify hourly record
        hourly = EventMetricsHourly.objects.filter(
            organization_id=self.org_id,
            metric_name="test_metric",
        ).first()
        assert hourly is not None
        assert hourly.metric_value == 10
        assert hourly.metric_count == 1

        # Verify daily record
        daily = EventMetricsDaily.objects.filter(
            organization_id=self.org_id,
            metric_name="test_metric",
        ).first()
        assert daily is not None
        assert daily.metric_value == 10

        # Verify monthly record
        monthly = EventMetricsMonthly.objects.filter(
            organization_id=self.org_id,
            metric_name="test_metric",
        ).first()
        assert monthly is not None
        assert monthly.metric_value == 10

    def test_batch_aggregates_same_hour(self):
        """Test that multiple events in the same hour are aggregated."""
        mock_requests = []
        for i in range(5):
            mock_request = MagicMock()
            mock_request.args = [
                {
                    "org_id": self.org_id,
                    "metric_name": "aggregated_metric",
                    "metric_value": 10,
                    "metric_type": MetricType.COUNTER,
                    "timestamp": self.base_timestamp,  # Same timestamp
                    "labels": {},
                    "project": "default",
                    "tag": None,
                }
            ]
            mock_request.kwargs = {}
            mock_requests.append(mock_request)

        result = process_dashboard_metric_events(mock_requests)

        assert result["processed"] == 5
        assert result["errors"] == 0

        # Should be one hourly record with aggregated values
        hourly_count = EventMetricsHourly.objects.filter(
            organization_id=self.org_id,
            metric_name="aggregated_metric",
        ).count()
        assert hourly_count == 1

        hourly = EventMetricsHourly.objects.get(
            organization_id=self.org_id,
            metric_name="aggregated_metric",
        )
        assert hourly.metric_value == 50  # 5 * 10
        assert hourly.metric_count == 5

    def test_malformed_event_increments_errors(self):
        """Test that events with missing required fields increment errors."""
        mock_request = MagicMock()
        mock_request.args = [
            {
                # Missing org_id
                "metric_name": "test_metric",
                "metric_value": 10,
            }
        ]
        mock_request.kwargs = {}

        result = process_dashboard_metric_events([mock_request])

        assert result["processed"] == 0
        assert result["errors"] == 1

    def test_different_hours_create_separate_records(self):
        """Test that events in different hours create separate records."""
        hour1_ts = self.base_timestamp
        hour2_ts = self.base_timestamp + 3600  # 1 hour later

        mock_requests = []
        for ts in [hour1_ts, hour2_ts]:
            mock_request = MagicMock()
            mock_request.args = [
                {
                    "org_id": self.org_id,
                    "metric_name": "multi_hour_metric",
                    "metric_value": 10,
                    "metric_type": MetricType.COUNTER,
                    "timestamp": ts,
                    "labels": {},
                    "project": "default",
                    "tag": None,
                }
            ]
            mock_request.kwargs = {}
            mock_requests.append(mock_request)

        result = process_dashboard_metric_events(mock_requests)

        assert result["processed"] == 2

        # Should be two hourly records
        hourly_count = EventMetricsHourly.objects.filter(
            organization_id=self.org_id,
            metric_name="multi_hour_metric",
        ).count()
        assert hourly_count == 2

    def test_event_from_kwargs(self):
        """Test that events can be extracted from kwargs."""
        mock_request = MagicMock()
        mock_request.args = []
        mock_request.kwargs = {
            "event": {
                "org_id": self.org_id,
                "metric_name": "kwargs_metric",
                "metric_value": 25,
                "metric_type": MetricType.COUNTER,
                "timestamp": self.base_timestamp,
                "labels": {},
                "project": "default",
                "tag": None,
            }
        }

        result = process_dashboard_metric_events([mock_request])

        assert result["processed"] == 1

        hourly = EventMetricsHourly.objects.get(
            organization_id=self.org_id,
            metric_name="kwargs_metric",
        )
        assert hourly.metric_value == 25


class TestBulkUpsert(TransactionTestCase):
    """Tests for bulk upsert functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.org_id = str(uuid.uuid4())

    def test_bulk_upsert_hourly_creates_new(self):
        """Test that bulk upsert creates new hourly records."""
        hour_ts = timezone.now().replace(minute=0, second=0, microsecond=0)
        aggregations = {
            (self.org_id, hour_ts.isoformat(), "new_metric", "default", None): {
                "metric_type": MetricType.COUNTER,
                "value": 100,
                "count": 5,
                "labels": {"source": "test"},
            }
        }

        created, updated = _bulk_upsert_hourly(aggregations)

        assert created == 1
        assert updated == 0

    def test_bulk_upsert_hourly_updates_existing(self):
        """Test that bulk upsert updates existing hourly records."""
        hour_ts = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Create existing record
        EventMetricsHourly.objects.create(
            organization_id=self.org_id,
            timestamp=hour_ts,
            metric_name="existing_metric",
            metric_type=MetricType.COUNTER,
            metric_value=50,
            metric_count=2,
            labels={},
            project="default",
            tag=None,
        )

        aggregations = {
            (self.org_id, hour_ts.isoformat(), "existing_metric", "default", None): {
                "metric_type": MetricType.COUNTER,
                "value": 30,
                "count": 3,
                "labels": {"new": "label"},
            }
        }

        created, updated = _bulk_upsert_hourly(aggregations)

        assert created == 0
        assert updated == 1

        # Refresh and check values
        record = EventMetricsHourly.objects.get(
            organization_id=self.org_id,
            timestamp=hour_ts,
            metric_name="existing_metric",
        )
        assert record.metric_value == 80  # 50 + 30
        assert record.metric_count == 5  # 2 + 3

    def test_bulk_upsert_daily_creates_new(self):
        """Test that bulk upsert creates new daily records."""
        today = timezone.now().date()
        aggregations = {
            (self.org_id, today.isoformat(), "daily_metric", "default", None): {
                "metric_type": MetricType.COUNTER,
                "value": 200,
                "count": 10,
                "labels": {},
            }
        }

        created, updated = _bulk_upsert_daily(aggregations)

        assert created == 1
        assert updated == 0

    def test_bulk_upsert_monthly_creates_new(self):
        """Test that bulk upsert creates new monthly records."""
        first_of_month = timezone.now().replace(day=1).date()
        aggregations = {
            (self.org_id, first_of_month.isoformat(), "monthly_metric", "default", None): {
                "metric_type": MetricType.COUNTER,
                "value": 500,
                "count": 50,
                "labels": {},
            }
        }

        created, updated = _bulk_upsert_monthly(aggregations)

        assert created == 1
        assert updated == 0


class TestCleanupTasks(TransactionTestCase):
    """Tests for cleanup tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.org_id = str(uuid.uuid4())

    def test_cleanup_hourly_metrics_deletes_old_records(self):
        """Test that cleanup deletes hourly records older than retention."""
        now = timezone.now()
        old_timestamp = now - timedelta(days=35)  # Older than 30 days
        recent_timestamp = now - timedelta(days=5)  # Within retention

        # Create old record
        EventMetricsHourly.objects.create(
            organization_id=self.org_id,
            timestamp=old_timestamp,
            metric_name="old_metric",
            metric_type=MetricType.COUNTER,
            metric_value=10,
            metric_count=1,
            labels={},
            project="default",
        )

        # Create recent record
        EventMetricsHourly.objects.create(
            organization_id=self.org_id,
            timestamp=recent_timestamp,
            metric_name="recent_metric",
            metric_type=MetricType.COUNTER,
            metric_value=20,
            metric_count=1,
            labels={},
            project="default",
        )

        result = cleanup_hourly_metrics(retention_days=30)

        assert result["success"] is True
        assert result["deleted"] == 1
        assert result["retention_days"] == 30

        # Verify old is deleted, recent remains
        assert not EventMetricsHourly.objects.filter(
            metric_name="old_metric"
        ).exists()
        assert EventMetricsHourly.objects.filter(
            metric_name="recent_metric"
        ).exists()

    def test_cleanup_daily_metrics_deletes_old_records(self):
        """Test that cleanup deletes daily records older than retention."""
        now = timezone.now()
        old_date = (now - timedelta(days=400)).date()  # Older than 365 days
        recent_date = (now - timedelta(days=30)).date()  # Within retention

        # Create old record
        EventMetricsDaily.objects.create(
            organization_id=self.org_id,
            date=old_date,
            metric_name="old_daily_metric",
            metric_type=MetricType.COUNTER,
            metric_value=100,
            metric_count=10,
            labels={},
            project="default",
        )

        # Create recent record
        EventMetricsDaily.objects.create(
            organization_id=self.org_id,
            date=recent_date,
            metric_name="recent_daily_metric",
            metric_type=MetricType.COUNTER,
            metric_value=200,
            metric_count=20,
            labels={},
            project="default",
        )

        result = cleanup_daily_metrics(retention_days=365)

        assert result["success"] is True
        assert result["deleted"] == 1

        # Verify old is deleted, recent remains
        assert not EventMetricsDaily.objects.filter(
            metric_name="old_daily_metric"
        ).exists()
        assert EventMetricsDaily.objects.filter(
            metric_name="recent_daily_metric"
        ).exists()

    def test_cleanup_hourly_with_custom_retention(self):
        """Test cleanup with custom retention period."""
        now = timezone.now()
        old_timestamp = now - timedelta(days=10)

        EventMetricsHourly.objects.create(
            organization_id=self.org_id,
            timestamp=old_timestamp,
            metric_name="custom_retention_metric",
            metric_type=MetricType.COUNTER,
            metric_value=10,
            metric_count=1,
            labels={},
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


class TestIntegration(TransactionTestCase):
    """Integration tests for the full processing pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        self.org_id = str(uuid.uuid4())

    def test_full_pipeline_hourly_daily_monthly(self):
        """Test that events flow through to all three aggregation tiers."""
        now = timezone.now()
        base_timestamp = now.timestamp()

        # Create events across 3 different hours
        mock_requests = []
        for hour_offset in range(3):
            for _ in range(10):  # 10 events per hour
                mock_request = MagicMock()
                mock_request.args = [
                    {
                        "org_id": self.org_id,
                        "metric_name": "pipeline_metric",
                        "metric_value": 1,
                        "metric_type": MetricType.COUNTER,
                        "timestamp": base_timestamp + (hour_offset * 3600),
                        "labels": {"hour": str(hour_offset)},
                        "project": "test_project",
                        "tag": "v1",
                    }
                ]
                mock_request.kwargs = {}
                mock_requests.append(mock_request)

        result = process_dashboard_metric_events(mock_requests)

        assert result["processed"] == 30
        assert result["errors"] == 0

        # Verify 3 hourly records (one per hour)
        hourly_count = EventMetricsHourly.objects.filter(
            organization_id=self.org_id,
            metric_name="pipeline_metric",
        ).count()
        assert hourly_count == 3

        # Each hourly record should have aggregated 10 events
        for hourly in EventMetricsHourly.objects.filter(
            organization_id=self.org_id,
            metric_name="pipeline_metric",
        ):
            assert hourly.metric_value == 10
            assert hourly.metric_count == 10

        # Verify 1 daily record (all in same day)
        daily = EventMetricsDaily.objects.filter(
            organization_id=self.org_id,
            metric_name="pipeline_metric",
        )
        assert daily.count() == 1
        assert daily.first().metric_value == 30

        # Verify 1 monthly record
        monthly = EventMetricsMonthly.objects.filter(
            organization_id=self.org_id,
            metric_name="pipeline_metric",
        )
        assert monthly.count() == 1
        assert monthly.first().metric_value == 30
