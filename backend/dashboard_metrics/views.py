"""API views for Dashboard Metrics."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db.models import Avg, Max, Min, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncWeek
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from permissions.permission import IsOrganizationMember
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from utils.user_context import UserContext

from .cache import (
    cache_metrics_response,
    mget_metrics_buckets,
    mset_metrics_buckets,
)
from .models import EventMetricsDaily, EventMetricsHourly, EventMetricsMonthly
from .serializers import (
    EventMetricsHourlySerializer,
    MetricsQuerySerializer,
)
from .services import MetricsQueryService

logger = logging.getLogger(__name__)

# Enable bucket caching for better cache reuse across overlapping queries
BUCKET_CACHE_ENABLED = True

# Thresholds for automatic source selection (in days)
HOURLY_MAX_DAYS = 7  # Use hourly for ≤7 days
DAILY_MAX_DAYS = 90  # Use daily for ≤90 days, monthly for >90 days


class MetricsRateThrottle(UserRateThrottle):
    """Rate throttle for metrics endpoints."""

    rate = "1000/hour"


class DashboardMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for dashboard metrics API.

    Provides read-only access to aggregated metrics data with
    time series and summary endpoints. Automatically selects the
    optimal data source (hourly/daily/monthly) based on date range.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    throttle_classes = [MetricsRateThrottle]
    serializer_class = EventMetricsHourlySerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["timestamp", "metric_name", "metric_value"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        """Return queryset filtered by user's organization.

        The model manager (DefaultOrganizationManagerMixin) automatically
        filters by UserContext.get_organization(). We call _get_organization()
        here only as a guard to return 403 instead of empty results when
        there's no org context.
        """
        self._get_organization()
        return EventMetricsHourly.objects.all()

    def _get_organization(self):
        """Get the current organization or raise PermissionDenied."""
        organization = UserContext.get_organization()
        if not organization:
            raise PermissionDenied("No organization context")
        return organization

    def _select_source(self, params: dict) -> str:
        """Select the optimal data source based on date range or explicit source.

        Args:
            params: Validated query parameters containing start_date, end_date, source

        Returns:
            Source name: 'hourly', 'daily', or 'monthly'
        """
        source = params.get("source", "auto")
        if source != "auto":
            return source

        # Auto-select based on date range
        days = (params["end_date"] - params["start_date"]).days

        if days <= HOURLY_MAX_DAYS:
            return "hourly"
        elif days <= DAILY_MAX_DAYS:
            return "daily"
        else:
            return "monthly"

    def _get_source_queryset(self, source: str):
        """Get the queryset for the specified source table.

        Organization filtering is handled automatically by the model manager
        (DefaultOrganizationManagerMixin).

        Args:
            source: One of 'hourly', 'daily', 'monthly'

        Returns:
            QuerySet for the appropriate table
        """
        if source == "daily":
            return EventMetricsDaily.objects.all()
        elif source == "monthly":
            return EventMetricsMonthly.objects.all()
        return EventMetricsHourly.objects.all()

    def _get_timestamp_field(self, source: str) -> str:
        """Get the timestamp field name for the source table."""
        if source == "hourly":
            return "timestamp"
        elif source == "daily":
            return "date"
        elif source == "monthly":
            return "month"
        return "timestamp"

    def _apply_source_filters(self, queryset, params: dict, source: str):
        """Apply filters based on the source table structure."""
        ts_field = self._get_timestamp_field(source)

        queryset = queryset.filter(
            **{
                f"{ts_field}__gte": params["start_date"]
                if source == "hourly"
                else params["start_date"].date(),
                f"{ts_field}__lte": params["end_date"]
                if source == "hourly"
                else params["end_date"].date(),
            }
        )

        if params.get("metric_name"):
            queryset = queryset.filter(metric_name=params["metric_name"])

        if params.get("project"):
            queryset = queryset.filter(project=params["project"])

        if "tag" in params and params["tag"] is not None:
            queryset = queryset.filter(tag=params["tag"])

        return queryset

    def _fetch_hourly_with_bucket_cache(
        self,
        org_id: str,
        params: dict,
        metric_name: str | None = None,
    ) -> list[dict]:
        """Fetch hourly metrics using bucket-based caching.

        Splits the time range into hourly buckets, fetches from cache,
        queries DB for missing buckets, and saves to cache.

        Organization filtering is handled automatically by the model manager.

        Args:
            org_id: Organization ID string
            params: Query parameters with start_date, end_date
            metric_name: Optional metric name filter

        Returns:
            List of metric records from EventMetricsHourly
        """
        start_date = params["start_date"]
        end_date = params["end_date"]

        # Try to get from bucket cache
        cached_data, missing_buckets = mget_metrics_buckets(
            org_id, start_date, end_date, "hourly", metric_name
        )

        # If we have missing buckets, query them from DB
        db_data_by_bucket = {}
        if missing_buckets:
            for bucket_ts in missing_buckets:
                # Query this specific hour
                bucket_end = bucket_ts + timedelta(hours=1)
                bucket_qs = EventMetricsHourly.objects.filter(
                    timestamp__gte=bucket_ts,
                    timestamp__lt=bucket_end,
                )

                if metric_name:
                    bucket_qs = bucket_qs.filter(metric_name=metric_name)

                if params.get("project"):
                    bucket_qs = bucket_qs.filter(project=params["project"])

                if "tag" in params and params["tag"] is not None:
                    bucket_qs = bucket_qs.filter(tag=params["tag"])

                # Convert to list of dicts for caching
                bucket_records = list(
                    bucket_qs.values(
                        "metric_name",
                        "metric_type",
                        "metric_value",
                        "metric_count",
                        "project",
                        "tag",
                        "timestamp",
                    )
                )
                db_data_by_bucket[bucket_ts] = bucket_records

            # Save to cache
            if db_data_by_bucket:
                mset_metrics_buckets(org_id, db_data_by_bucket, "hourly", metric_name)

        # Combine cached and fresh data
        all_records = []
        for bucket_ts, records in cached_data.items():
            all_records.extend(records)
        for bucket_ts, records in db_data_by_bucket.items():
            all_records.extend(records)

        return all_records

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request: Request) -> Response:
        """Get summary statistics for all metrics.

        Automatically selects the optimal data source (hourly/daily/monthly)
        based on the date range, or use ?source= to override.

        Uses bucket-based caching for hourly data to maximize cache reuse
        across overlapping queries.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            metric_name: Filter by specific metric name
            project: Filter by project identifier
            source: Data source (auto, hourly, daily, monthly). Default: auto

        Returns:
            Summary statistics for each metric including totals,
            averages, min, and max values.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        organization = self._get_organization()
        org_id = str(organization.id)
        source = self._select_source(params)

        # Use bucket caching for hourly source (best cache reuse)
        if source == "hourly" and BUCKET_CACHE_ENABLED:
            records = self._fetch_hourly_with_bucket_cache(
                org_id, params, params.get("metric_name")
            )

            # Aggregate the records manually
            summary_dict = defaultdict(
                lambda: {
                    "total_value": 0,
                    "total_count": 0,
                    "values": [],
                    "metric_type": "counter",
                }
            )
            for record in records:
                name = record["metric_name"]
                value = record.get("metric_value") or 0
                count = record.get("metric_count") or 0
                summary_dict[name]["total_value"] += value
                summary_dict[name]["total_count"] += count
                summary_dict[name]["values"].append(value)
                summary_dict[name]["metric_type"] = record.get("metric_type", "counter")

            summary_list = []
            for name, agg in summary_dict.items():
                values = agg["values"]
                summary_list.append(
                    {
                        "metric_name": name,
                        "metric_type": agg["metric_type"],
                        "total_value": agg["total_value"],
                        "total_count": agg["total_count"],
                        "average_value": agg["total_value"] / len(values)
                        if values
                        else 0,
                        "min_value": min(values) if values else 0,
                        "max_value": max(values) if values else 0,
                    }
                )
            summary_list.sort(key=lambda x: x["metric_name"])

        else:
            # Use standard queryset for daily/monthly (existing behavior)
            queryset = self._get_source_queryset(source)
            queryset = self._apply_source_filters(queryset, params, source)

            # Aggregate by metric name
            summary = (
                queryset.values("metric_name")
                .annotate(
                    total_value=Sum("metric_value"),
                    total_count=Sum("metric_count"),
                    average_value=Avg("metric_value"),
                    min_value=Min("metric_value"),
                    max_value=Max("metric_value"),
                )
                .order_by("metric_name")
            )

            # Add metric_type from the first record of each metric
            summary_list = []
            for row in summary:
                metric_type_record = (
                    queryset.filter(metric_name=row["metric_name"])
                    .values("metric_type")
                    .first()
                )
                row["metric_type"] = (
                    metric_type_record["metric_type"] if metric_type_record else "counter"
                )
                summary_list.append(row)

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "source": source,
                "summary": summary_list,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="series")
    def series(self, request: Request) -> Response:
        """Get time series data for metrics.

        Automatically selects the optimal data source (hourly/daily/monthly)
        based on the date range, or use ?source= to override.

        Uses bucket-based caching for hourly data to maximize cache reuse
        across overlapping queries.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            granularity: Time granularity (hour, day, week)
            metric_name: Filter by specific metric name
            project: Filter by project identifier
            source: Data source (auto, hourly, daily, monthly). Default: auto

        Returns:
            Time series data grouped by the specified granularity.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        organization = self._get_organization()
        org_id = str(organization.id)
        source = self._select_source(params)
        granularity = params.get("granularity", "day")

        # Use bucket caching for hourly source (best cache reuse)
        if source == "hourly" and BUCKET_CACHE_ENABLED:
            records = self._fetch_hourly_with_bucket_cache(
                org_id, params, params.get("metric_name")
            )

            # Apply granularity-based grouping to cached records
            from datetime import datetime

            trunc_funcs = {
                "hour": lambda ts: ts.replace(minute=0, second=0, microsecond=0),
                "day": lambda ts: ts.replace(hour=0, minute=0, second=0, microsecond=0),
                "week": lambda ts: (ts - timedelta(days=ts.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ),
            }
            trunc_fn = trunc_funcs.get(granularity, trunc_funcs["day"])

            # Group records by (period, metric_name, project, tag)
            grouped = defaultdict(
                lambda: {"value": 0, "count": 0, "metric_type": "counter"}
            )
            for record in records:
                ts = record.get("timestamp")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                period = trunc_fn(ts)
                key = (
                    period,
                    record["metric_name"],
                    record.get("project", ""),
                    record.get("tag"),
                )
                grouped[key]["value"] += record.get("metric_value") or 0
                grouped[key]["count"] += record.get("metric_count") or 0
                grouped[key]["metric_type"] = record.get("metric_type", "counter")

            # Convert to series_data format
            series_data = [
                {
                    "period": key[0],
                    "metric_name": key[1],
                    "project": key[2],
                    "tag": key[3],
                    "value": data["value"],
                    "count": data["count"],
                    "metric_type": data["metric_type"],
                }
                for key, data in grouped.items()
            ]
            series_data.sort(key=lambda x: (x["period"], x["metric_name"]))

        else:
            # Use standard queryset for daily/monthly (existing behavior)
            queryset = self._get_source_queryset(source)
            queryset = self._apply_source_filters(queryset, params, source)
            ts_field = self._get_timestamp_field(source)

            # For daily/monthly tables, data is already at that granularity
            # For hourly, we can truncate to day/week if requested
            if source == "hourly":
                trunc_func = {
                    "hour": TruncHour,
                    "day": TruncDay,
                    "week": TruncWeek,
                }.get(granularity, TruncDay)
                series_data = (
                    queryset.annotate(period=trunc_func(ts_field))
                    .values("period", "metric_name", "metric_type", "project", "tag")
                    .annotate(
                        value=Sum("metric_value"),
                        count=Sum("metric_count"),
                    )
                    .order_by("period", "metric_name")
                )
            elif source == "daily":
                # Daily data - use date directly or truncate to week
                if granularity == "week":
                    series_data = (
                        queryset.annotate(period=TruncWeek(ts_field))
                        .values("period", "metric_name", "metric_type", "project", "tag")
                        .annotate(
                            value=Sum("metric_value"),
                            count=Sum("metric_count"),
                        )
                        .order_by("period", "metric_name")
                    )
                else:
                    # Return daily data as-is
                    series_data = (
                        queryset.values(
                            "metric_name",
                            "metric_type",
                            "project",
                            "tag",
                            "metric_value",
                            "metric_count",
                        )
                        .annotate(period=TruncDay(ts_field))
                        .order_by("period", "metric_name")
                    )
                    series_data = [
                        {
                            "period": row["period"],
                            "metric_name": row["metric_name"],
                            "metric_type": row["metric_type"],
                            "project": row["project"],
                            "tag": row["tag"],
                            "value": row["metric_value"],
                            "count": row["metric_count"],
                        }
                        for row in series_data
                    ]
            else:  # monthly
                # Monthly data - return as-is
                series_data = (
                    queryset.values(
                        "metric_name",
                        "metric_type",
                        "project",
                        "tag",
                        "metric_value",
                        "metric_count",
                    )
                    .annotate(period=TruncDay(ts_field))
                    .order_by("period", "metric_name")
                )
                series_data = [
                    {
                        "period": row["period"],
                        "metric_name": row["metric_name"],
                        "metric_type": row["metric_type"],
                        "project": row["project"],
                        "tag": row["tag"],
                        "value": row["metric_value"],
                        "count": row["metric_count"],
                    }
                    for row in series_data
                ]

        # Group by metric
        series_by_metric = defaultdict(
            lambda: {
                "metric_name": "",
                "metric_type": "",
                "project": "",
                "tag": None,
                "data": [],
                "total_value": 0,
                "total_count": 0,
            }
        )

        for row in series_data:
            key = (row["metric_name"], row["project"], row["tag"])
            series = series_by_metric[key]
            series["metric_name"] = row["metric_name"]
            series["metric_type"] = row["metric_type"]
            series["project"] = row["project"]
            series["tag"] = row["tag"]
            period = row["period"]
            series["data"].append(
                {
                    "timestamp": period.isoformat()
                    if hasattr(period, "isoformat")
                    else str(period),
                    "value": row["value"],
                    "count": row["count"],
                }
            )
            series["total_value"] += row["value"] or 0
            series["total_count"] += row["count"] or 0

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "granularity": granularity,
                "source": source,
                "series": list(series_by_metric.values()),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="overview")
    @cache_metrics_response(endpoint="overview")
    def overview(self, request: Request) -> Response:
        """Get a quick overview of recent metrics.

        Query Parameters:
            start_date: Start of date range (ISO 8601, optional)
            end_date: End of date range (ISO 8601, optional)

        If dates are not provided, defaults to last 7 days.
        """
        # Parse optional date parameters (default to last 7 days)
        end_date_str = request.query_params.get("end_date")
        start_date_str = request.query_params.get("start_date")

        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if timezone.is_naive(end_date):
                    end_date = timezone.make_aware(end_date)
            except ValueError:
                end_date = timezone.now()
        else:
            end_date = timezone.now()

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                if timezone.is_naive(start_date):
                    start_date = timezone.make_aware(start_date)
            except ValueError:
                start_date = end_date - timedelta(days=7)
        else:
            start_date = end_date - timedelta(days=7)

        # Calculate days in range for response
        days = (end_date - start_date).days

        # Auto-select source based on date range
        organization = self._get_organization()
        source = self._select_source({"start_date": start_date, "end_date": end_date})
        ts_field = self._get_timestamp_field(source)
        queryset = self._get_source_queryset(source).filter(
            **{
                f"{ts_field}__gte": start_date
                if source == "hourly"
                else start_date.date(),
                f"{ts_field}__lte": end_date if source == "hourly" else end_date.date(),
            }
        )

        # Get totals per metric
        totals = (
            queryset.values("metric_name")
            .annotate(
                total_value=Sum("metric_value"),
                total_count=Sum("metric_count"),
            )
            .order_by("metric_name")
        )

        # Get daily trend per metric for the period
        trunc_func = TruncDay(ts_field)
        daily_trend_query = (
            queryset.annotate(day=trunc_func)
            .values("day", "metric_name")
            .annotate(
                total_value=Sum("metric_value"),
                total_count=Sum("metric_count"),
            )
            .order_by("day", "metric_name")
        )

        # Restructure to nested format: {date: {metrics: {name: value}}}
        daily_trend_map = {}
        for row in daily_trend_query:
            date_str = row["day"].isoformat()
            if date_str not in daily_trend_map:
                daily_trend_map[date_str] = {"date": date_str, "metrics": {}}
            daily_trend_map[date_str]["metrics"][row["metric_name"]] = row["total_value"]

        # Sort by date
        daily_trend = sorted(daily_trend_map.values(), key=lambda x: x["date"])

        return Response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
                },
                "totals": list(totals),
                "daily_trend": daily_trend,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="live-summary")
    @cache_metrics_response(endpoint="live_summary")
    def live_summary(self, request: Request) -> Response:
        """Get summary from existing source tables (live data).

        This endpoint queries metrics directly from source tables
        (usage, page_usage, workflow_execution, etc.) instead of
        the aggregated event_metrics_hourly table.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)

        Returns:
            Summary totals for all 9 metrics from live data.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        organization = self._get_organization()
        org_id = str(organization.id)

        summary = MetricsQueryService.get_all_metrics_summary(
            org_id,
            params["start_date"],
            params["end_date"],
        )

        # Format response to match /summary/ endpoint format for frontend compatibility
        # MetricsTable expects: summary[] with metric_name, metric_type, total_value, etc.
        summary_list = [
            {
                "metric_name": name,
                "metric_type": "histogram" if name == "llm_usage" else "counter",
                "total_value": value,
                "total_count": 1,  # Not available from live queries
                "average_value": value,  # Same as total for live data
                "min_value": value,
                "max_value": value,
            }
            for name, value in summary.items()
        ]

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "source": "live",
                "summary": summary_list,  # Changed from "metrics" to "summary"
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="live-series")
    @cache_metrics_response(endpoint="live_series")
    def live_series(self, request: Request) -> Response:
        """Get time series from existing source tables (live data).

        This endpoint queries metrics directly from source tables
        with time-based aggregation (hourly, daily, weekly).

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            granularity: Time granularity (hour, day, week)
            metric_name: Filter by specific metric name (optional)

        Returns:
            Time series data for all metrics grouped by granularity.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        organization = self._get_organization()
        org_id = str(organization.id)
        granularity = params.get("granularity", "day")

        # Define metric query mapping
        metric_queries = {
            "documents_processed": MetricsQueryService.get_documents_processed,
            "pages_processed": MetricsQueryService.get_pages_processed,
            "llm_calls": MetricsQueryService.get_llm_calls,
            "challenges": MetricsQueryService.get_challenges,
            "summarization_calls": MetricsQueryService.get_summarization_calls,
            "deployed_api_requests": MetricsQueryService.get_deployed_api_requests,
            "etl_pipeline_executions": MetricsQueryService.get_etl_pipeline_executions,
            "llm_usage": MetricsQueryService.get_llm_usage_cost,
            "prompt_executions": MetricsQueryService.get_prompt_executions,
        }

        # Filter by specific metric if requested
        if params.get("metric_name"):
            metric_queries = {
                k: v for k, v in metric_queries.items() if k == params["metric_name"]
            }

        series = []
        errors = []
        for metric_name, query_fn in metric_queries.items():
            try:
                data = query_fn(
                    org_id,
                    params["start_date"],
                    params["end_date"],
                    granularity,
                )
                series.append(
                    {
                        "metric_name": metric_name,
                        "metric_type": "histogram"
                        if metric_name == "llm_usage"
                        else "counter",
                        "data": [
                            {
                                "timestamp": r["period"].isoformat(),
                                "value": r["value"] or 0,
                            }
                            for r in data
                        ],
                        "total_value": sum(r["value"] or 0 for r in data),
                    }
                )
            except Exception:
                logger.exception("Failed to fetch metric %s", metric_name)
                errors.append(metric_name)
                series.append(
                    {
                        "metric_name": metric_name,
                        "error": "unavailable",
                        "data": [],
                        "total_value": 0,
                    }
                )

        response_data = {
            "start_date": params["start_date"].isoformat(),
            "end_date": params["end_date"].isoformat(),
            "granularity": granularity,
            "source": "live",
            "series": series,
        }

        if errors:
            response_data["partial_errors"] = errors

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="recent-activity")
    @cache_metrics_response(endpoint="recent_activity")
    def recent_activity(self, request: Request) -> Response:
        """Get recent processing activity differentiated by type.

        Returns recent file executions with type classification:
        - etl: ETL pipeline executions
        - api: API deployment requests
        - workflow: Manual workflow/prompt studio executions

        Query Parameters:
            limit: Maximum records to return (default 10, max 50)

        Returns:
            200: List of recent activity items
            500: Error occurred
        """
        organization = self._get_organization()
        org_id = str(organization.id)
        try:
            limit = min(int(request.query_params.get("limit", 10)), 50)
        except (ValueError, TypeError):
            limit = 10

        try:
            data = MetricsQueryService.get_recent_activity(org_id, limit)
            return Response({"activity": data})
        except Exception as e:
            logger.exception("Error fetching recent activity")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="workflow-token-usage")
    @cache_metrics_response(endpoint="workflow_token_usage")
    def workflow_token_usage(self, request: Request) -> Response:
        """Get per-workflow LLM token usage breakdown.

        Returns token usage and cost aggregated per workflow for the
        given date range. Cached for 1 hour; pass ?refresh=true to
        bypass cache.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            refresh: If "true", bypass cache and fetch fresh data

        Returns:
            200: List of workflows with token usage
            500: Error occurred
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        organization = self._get_organization()
        org_id = str(organization.id)

        try:
            data = MetricsQueryService.get_workflow_token_usage(
                org_id,
                params["start_date"],
                params["end_date"],
            )
            return Response(
                {
                    "start_date": params["start_date"].isoformat(),
                    "end_date": params["end_date"].isoformat(),
                    "workflows": data,
                }
            )
        except Exception as e:
            logger.exception("Error fetching workflow token usage")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="health")
    def health(self, request: Request) -> Response:
        """Health check endpoint for metrics system.

        Returns status of database and cache connectivity.
        Useful for liveness/readiness probes.

        Returns:
            200: All systems healthy
            503: One or more systems unhealthy
        """
        checks = {
            "database": self._check_database(),
            "cache": self._check_cache(),
        }

        healthy = all(check.get("status") == "ok" for check in checks.values())
        http_status = (
            status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            {
                "healthy": healthy,
                "checks": checks,
                "timestamp": timezone.now().isoformat(),
            },
            status=http_status,
        )

    def _check_database(self) -> dict:
        """Check database connectivity."""
        try:
            EventMetricsHourly.objects.exists()
            return {"status": "ok"}
        except Exception as e:
            logger.exception("Database health check failed")
            return {"status": "error", "message": str(e)}

    def _check_cache(self) -> dict:
        """Check cache connectivity."""
        try:
            cache.set("metrics_health_check", "ok", 10)
            result = cache.get("metrics_health_check")
            if result == "ok":
                return {"status": "ok"}
            return {"status": "error", "message": "Cache read/write mismatch"}
        except Exception as e:
            logger.exception("Cache health check failed")
            return {"status": "error", "message": str(e)}
