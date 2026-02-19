"""Serializers for Dashboard Metrics API."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import EventMetricsHourly


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
