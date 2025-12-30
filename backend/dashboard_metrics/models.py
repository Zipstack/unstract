"""Django models for Dashboard Metrics."""
import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class MetricType(models.TextChoices):
    """Type of metric - determines aggregation behavior."""

    COUNTER = "counter", "Counter"
    HISTOGRAM = "histogram", "Histogram"


class EventMetricsHourlyManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for EventMetricsHourly with organization filtering."""

    pass


class EventMetricsDailyManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for EventMetricsDaily with organization filtering."""

    pass


class EventMetricsMonthlyManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for EventMetricsMonthly with organization filtering."""

    pass


class EventMetricsHourly(DefaultOrganizationMixin, BaseModel):
    """Hourly aggregated metrics for dashboard display.

    Stores metric events aggregated by hour for efficient querying.
    Uses JSONB for flexible label storage with GIN index for fast lookups.

    Attributes:
        id: UUID primary key
        timestamp: Hour bucket timestamp (truncated to hour)
        metric_name: Name of the metric from MetricName enum
        metric_type: Type of metric (counter or histogram)
        metric_value: Aggregated value (sum for counters, sum for histograms)
        metric_count: Number of events aggregated into this record
        labels: Dimensional labels as JSONB for flexible querying
        project: Project identifier for filtering
        tag: Optional tag for categorization
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Primary key UUID, auto-generated",
    )
    timestamp = models.DateTimeField(
        db_index=True,
        db_comment="Hour bucket timestamp (truncated to hour)",
    )
    metric_name = models.CharField(
        max_length=64,
        db_index=True,
        db_comment="Metric identifier from MetricName enum",
    )
    metric_type = models.CharField(
        max_length=16,
        choices=MetricType.choices,
        default=MetricType.COUNTER,
        db_comment="Type of metric (counter or histogram)",
    )
    metric_value = models.FloatField(
        default=0,
        db_comment="Aggregated value (sum for counters, sum for histograms)",
    )
    metric_count = models.IntegerField(
        default=1,
        db_comment="Number of events aggregated into this record",
    )
    labels = models.JSONField(
        default=dict,
        db_comment="Dimensional labels as JSONB for flexible querying",
    )
    project = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        db_comment="Project identifier for filtering",
    )
    tag = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_comment="Optional tag for categorization",
    )

    # Manager
    objects = EventMetricsHourlyManager()

    def __str__(self) -> str:
        return f"{self.metric_name}@{self.timestamp}: {self.metric_value}"

    class Meta:
        db_table = "event_metrics_hourly"
        verbose_name = "Event Metric (Hourly)"
        verbose_name_plural = "Event Metrics (Hourly)"
        indexes = [
            models.Index(
                fields=["organization", "timestamp"],
                name="idx_metrics_org_ts",
            ),
            models.Index(
                fields=["organization", "metric_name", "timestamp"],
                name="idx_metrics_org_name_ts",
            ),
            models.Index(
                fields=["project", "timestamp"],
                name="idx_metrics_project_ts",
            ),
            GinIndex(
                fields=["labels"],
                name="idx_metrics_labels_gin",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "timestamp",
                    "metric_name",
                    "project",
                    "tag",
                ],
                name="unique_hourly_metric",
            )
        ]


class EventMetricsDaily(DefaultOrganizationMixin, BaseModel):
    """Daily aggregated metrics for dashboard display.

    Stores metric events aggregated by day for efficient querying.
    Uses JSONB for flexible label storage with GIN index for fast lookups.

    Attributes:
        id: UUID primary key
        date: Day bucket (date only)
        metric_name: Name of the metric from MetricName enum
        metric_type: Type of metric (counter or histogram)
        metric_value: Aggregated value (sum for counters)
        metric_count: Number of events aggregated into this record
        labels: Dimensional labels as JSONB for flexible querying
        project: Project identifier for filtering
        tag: Optional tag for categorization
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Primary key UUID, auto-generated",
    )
    date = models.DateField(
        db_index=True,
        db_comment="Day bucket (date only)",
    )
    metric_name = models.CharField(
        max_length=64,
        db_index=True,
        db_comment="Metric identifier from MetricName enum",
    )
    metric_type = models.CharField(
        max_length=16,
        choices=MetricType.choices,
        default=MetricType.COUNTER,
        db_comment="Type of metric (counter or histogram)",
    )
    metric_value = models.FloatField(
        default=0,
        db_comment="Aggregated value (sum for counters)",
    )
    metric_count = models.IntegerField(
        default=1,
        db_comment="Number of events aggregated into this record",
    )
    labels = models.JSONField(
        default=dict,
        db_comment="Dimensional labels as JSONB for flexible querying",
    )
    project = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        db_comment="Project identifier for filtering",
    )
    tag = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_comment="Optional tag for categorization",
    )

    # Manager
    objects = EventMetricsDailyManager()

    def __str__(self) -> str:
        return f"{self.metric_name}@{self.date}: {self.metric_value}"

    class Meta:
        db_table = "event_metrics_daily"
        verbose_name = "Event Metric (Daily)"
        verbose_name_plural = "Event Metrics (Daily)"
        indexes = [
            models.Index(
                fields=["organization", "date"],
                name="idx_daily_org_date",
            ),
            models.Index(
                fields=["organization", "metric_name", "date"],
                name="idx_daily_org_name_date",
            ),
            models.Index(
                fields=["project", "date"],
                name="idx_daily_project_date",
            ),
            GinIndex(
                fields=["labels"],
                name="idx_daily_labels_gin",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "date",
                    "metric_name",
                    "project",
                    "tag",
                ],
                name="unique_daily_metric",
            )
        ]


class EventMetricsMonthly(DefaultOrganizationMixin, BaseModel):
    """Monthly aggregated metrics for dashboard display.

    Stores metric events aggregated by month for efficient querying.
    Uses JSONB for flexible label storage with GIN index for fast lookups.

    Attributes:
        id: UUID primary key
        month: First day of month bucket
        metric_name: Name of the metric from MetricName enum
        metric_type: Type of metric (counter or histogram)
        metric_value: Aggregated value (sum for counters)
        metric_count: Number of events aggregated into this record
        labels: Dimensional labels as JSONB for flexible querying
        project: Project identifier for filtering
        tag: Optional tag for categorization
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Primary key UUID, auto-generated",
    )
    month = models.DateField(
        db_index=True,
        db_comment="First day of month bucket",
    )
    metric_name = models.CharField(
        max_length=64,
        db_index=True,
        db_comment="Metric identifier from MetricName enum",
    )
    metric_type = models.CharField(
        max_length=16,
        choices=MetricType.choices,
        default=MetricType.COUNTER,
        db_comment="Type of metric (counter or histogram)",
    )
    metric_value = models.FloatField(
        default=0,
        db_comment="Aggregated value (sum for counters)",
    )
    metric_count = models.IntegerField(
        default=1,
        db_comment="Number of events aggregated into this record",
    )
    labels = models.JSONField(
        default=dict,
        db_comment="Dimensional labels as JSONB for flexible querying",
    )
    project = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        db_comment="Project identifier for filtering",
    )
    tag = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_comment="Optional tag for categorization",
    )

    # Manager
    objects = EventMetricsMonthlyManager()

    def __str__(self) -> str:
        return f"{self.metric_name}@{self.month}: {self.metric_value}"

    class Meta:
        db_table = "event_metrics_monthly"
        verbose_name = "Event Metric (Monthly)"
        verbose_name_plural = "Event Metrics (Monthly)"
        indexes = [
            models.Index(
                fields=["organization", "month"],
                name="idx_monthly_org_month",
            ),
            models.Index(
                fields=["organization", "metric_name", "month"],
                name="idx_monthly_org_name_month",
            ),
            models.Index(
                fields=["project", "month"],
                name="idx_monthly_project_month",
            ),
            GinIndex(
                fields=["labels"],
                name="idx_monthly_labels_gin",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "month",
                    "metric_name",
                    "project",
                    "tag",
                ],
                name="unique_monthly_metric",
            )
        ]
