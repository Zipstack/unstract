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

    def validate(self, attrs):
        """Set defaults and validate date range."""
        now = timezone.now()

        if not attrs.get("end_date"):
            attrs["end_date"] = now

        if not attrs.get("start_date"):
            attrs["start_date"] = now - timedelta(days=30)

        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError(
                {"start_date": "start_date must be before end_date"}
            )

        # Limit query range to 90 days
        max_range = timedelta(days=90)
        if attrs["end_date"] - attrs["start_date"] > max_range:
            raise serializers.ValidationError(
                {"start_date": "Query range cannot exceed 90 days"}
            )

        return attrs


class MetricDataPointSerializer(serializers.Serializer):
    """Serializer for a single metric data point."""

    timestamp = serializers.DateTimeField()
    value = serializers.FloatField()
    count = serializers.IntegerField()


class MetricSeriesSerializer(serializers.Serializer):
    """Serializer for a metric time series."""

    metric_name = serializers.CharField()
    metric_type = serializers.CharField()
    project = serializers.CharField()
    tag = serializers.CharField(allow_null=True)
    data = MetricDataPointSerializer(many=True)
    total_value = serializers.FloatField()
    total_count = serializers.IntegerField()


class MetricsSummarySerializer(serializers.Serializer):
    """Serializer for metrics summary response."""

    metric_name = serializers.CharField()
    total_value = serializers.FloatField()
    total_count = serializers.IntegerField()
    average_value = serializers.FloatField()
    min_value = serializers.FloatField()
    max_value = serializers.FloatField()


class MetricsResponseSerializer(serializers.Serializer):
    """Serializer for the complete metrics API response."""

    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    granularity = serializers.CharField()
    series = MetricSeriesSerializer(many=True)
    summary = MetricsSummarySerializer(many=True)


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
            "labels",
            "project",
            "tag",
            "created_at",
        ]
        read_only_fields = fields
