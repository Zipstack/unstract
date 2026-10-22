"""Serializers for Dashboard Metrics API."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.workflow_v2.enums import ExecutionStatus

from .models import ActivitySurface, EventMetricsHourly


def _default_date_range(attrs: dict) -> dict:
    """Default the range to the last 30 days and cap it at 365 days."""
    now = timezone.now()

    if not attrs.get("end_date"):
        attrs["end_date"] = now

    if not attrs.get("start_date"):
        attrs["start_date"] = now - timedelta(days=30)

    if attrs["start_date"] > attrs["end_date"]:
        raise serializers.ValidationError(
            {"start_date": "Start date must be before end date"}
        )

    # Limit query range to 365 days (1 year) for monthly data
    max_range = timedelta(days=365)
    if attrs["end_date"] - attrs["start_date"] > max_range:
        raise serializers.ValidationError(
            {"start_date": "Query range cannot exceed 365 days"}
        )

    return attrs


class MetricsQuerySerializer(serializers.Serializer):
    """Serializer for metrics query parameters."""

    start_date = serializers.DateTimeField(
        required=False,
        help_text="Start of date range (ISO 8601). Defaults to 30 days ago.",
    )
    end_date = serializers.DateTimeField(
        required=False,
        help_text="End of date range (ISO 8601). Defaults to now.",
    )
    metric_name = serializers.CharField(
        required=False,
        help_text="Filter by specific metric name.",
    )
    project = serializers.CharField(
        required=False,
        help_text="Filter by project identifier.",
    )
    tag = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Filter by tag.",
    )
    granularity = serializers.ChoiceField(
        choices=["hour", "day", "week"],
        default="day",
        help_text="Time granularity for aggregation.",
    )
    source = serializers.ChoiceField(
        choices=["auto", "hourly", "daily", "monthly"],
        default="auto",
        required=False,
        help_text=(
            "Data source table. 'auto' selects based on date range: "
            "≤7 days=hourly, ≤90 days=daily, >90 days=monthly."
        ),
    )

    def validate(self, attrs):
        """Set defaults and validate date range."""
        return _default_date_range(attrs)


class DeploymentUsageQuerySerializer(MetricsQuerySerializer):
    """Serializer for deployment usage query parameters."""

    DEPLOYMENT_TYPE_CHOICES = [(e.value, e.name) for e in ExecutionEntity]

    deployment_type = serializers.ChoiceField(
        choices=DEPLOYMENT_TYPE_CHOICES,
        default=ExecutionEntity.API.value,
        help_text="Deployment type filter: API, ETL, TASK, or WF.",
    )

    def validate(self, attrs):
        """Validate and enforce 30-day max range for deployment queries."""
        attrs = super().validate(attrs)

        # Enforce 30-day max range for deployment usage queries
        max_range = timedelta(days=30)
        if attrs["end_date"] - attrs["start_date"] > max_range:
            attrs["start_date"] = attrs["end_date"] - max_range
            attrs["range_truncated"] = True
        else:
            attrs["range_truncated"] = False

        # Normalize deployment_type to uppercase
        attrs["deployment_type"] = attrs["deployment_type"].upper()

        return attrs


class _CommaSeparatedChoicesField(serializers.CharField):
    """A comma-separated list of choices, e.g. ``COMPLETED,ERROR``.

    One comma-separated value rather than a repeated parameter, because the
    response cache keys on the last value of each parameter only.
    """

    def __init__(self, *, choices: list[str], upper: bool, **kwargs):
        self.choices = choices
        self.upper = upper
        super().__init__(**kwargs)

    def to_internal_value(self, data) -> list[str]:
        raw = super().to_internal_value(data)
        values = [
            v.strip().upper() if self.upper else v.strip().lower()
            for v in raw.split(",")
            if v.strip()
        ]
        unknown = sorted(set(values) - set(self.choices))
        if not values or unknown:
            raise serializers.ValidationError(
                f"Use one or more of {', '.join(self.choices)}, comma-separated."
            )
        # Keep the caller's order, without repeats.
        return list(dict.fromkeys(values))


class RecentActivityQuerySerializer(serializers.Serializer):
    """Query parameters for the paged form of ``recent-activity/`` (DG-02).

    Passing any of these switches the endpoint to the paged response. Without
    them, the endpoint answers exactly as before, from ``limit`` alone.
    """

    PAGED_PARAMS = frozenset(
        {"start_date", "end_date", "status", "surface", "page", "page_size"}
    )
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    start_date = serializers.DateTimeField(
        required=False,
        help_text="Start of date range (ISO 8601), inclusive. Defaults to 30 days ago.",
    )
    end_date = serializers.DateTimeField(
        required=False,
        help_text="End of date range (ISO 8601), inclusive. Defaults to now.",
    )
    status = _CommaSeparatedChoicesField(
        required=False,
        choices=[s.value for s in ExecutionStatus],
        upper=True,
        help_text="File execution statuses, comma-separated, e.g. COMPLETED,ERROR.",
    )
    surface = _CommaSeparatedChoicesField(
        required=False,
        choices=[s.value for s in ActivitySurface],
        upper=False,
        help_text="Surfaces, comma-separated: api, etl, task, workflow.",
    )
    page = serializers.IntegerField(
        required=False, default=1, min_value=1, help_text="1-based page."
    )
    page_size = serializers.IntegerField(
        required=False,
        default=DEFAULT_PAGE_SIZE,
        min_value=1,
        max_value=MAX_PAGE_SIZE,
        help_text=f"Rows per page, default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}.",
    )

    def validate(self, attrs):
        return _default_date_range(attrs)


class EventMetricsHourlySerializer(serializers.ModelSerializer):
    """Model serializer for EventMetricsHourly records."""

    class Meta:
        model = EventMetricsHourly
        fields = [
            "id",
            "timestamp",
            "metric_name",
            "metric_type",
            "metric_value",
            "metric_count",
            "project",
            "tag",
            "created_at",
        ]
        read_only_fields = fields
