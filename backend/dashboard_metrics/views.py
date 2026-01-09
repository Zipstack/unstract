"""API views for Dashboard Metrics."""

import logging
from collections import defaultdict
from datetime import timedelta

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

from .cache import cache_metrics_response
from .models import EventMetricsHourly
from .serializers import (
    EventMetricsHourlySerializer,
    MetricsQuerySerializer,
)
from .services import MetricsQueryService

logger = logging.getLogger(__name__)


class MetricsRateThrottle(UserRateThrottle):
    """Rate throttle for metrics endpoints."""

    rate = "100/hour"


class DashboardMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for dashboard metrics API.

    Provides read-only access to aggregated metrics data with
    time series and summary endpoints.
    """

    permission_classes = [IsAuthenticated, IsOrganizationMember]
    throttle_classes = [MetricsRateThrottle]
    serializer_class = EventMetricsHourlySerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["timestamp", "metric_name", "metric_value"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        """Return queryset filtered by user's organization."""
        try:
            organization = UserContext.get_organization()
            if not organization:
                logger.warning("No organization context for metrics request")
                raise PermissionDenied("No organization context")
            return EventMetricsHourly.objects.filter(organization=organization)
        except Exception as e:
            if isinstance(e, PermissionDenied):
                raise
            logger.error(f"Error getting metrics queryset: {e}")
            raise PermissionDenied("Unable to access metrics")

    @action(detail=False, methods=["get"], url_path="summary")
    @cache_metrics_response(endpoint="summary")
    def summary(self, request: Request) -> Response:
        """Get summary statistics for all metrics.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            metric_name: Filter by specific metric name
            project: Filter by project identifier

        Returns:
            Summary statistics for each metric including totals,
            averages, min, and max values.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        queryset = self._apply_filters(self.get_queryset(), params)

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

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "summary": list(summary),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="series")
    @cache_metrics_response(endpoint="series")
    def series(self, request: Request) -> Response:
        """Get time series data for metrics.

        Query Parameters:
            start_date: Start of date range (ISO 8601)
            end_date: End of date range (ISO 8601)
            granularity: Time granularity (hour, day, week)
            metric_name: Filter by specific metric name
            project: Filter by project identifier

        Returns:
            Time series data grouped by the specified granularity.
        """
        query_serializer = MetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        queryset = self._apply_filters(self.get_queryset(), params)
        granularity = params.get("granularity", "day")

        # Apply time truncation based on granularity
        trunc_func = {
            "hour": TruncHour,
            "day": TruncDay,
            "week": TruncWeek,
        }.get(granularity, TruncDay)

        # Aggregate by time period and metric
        series_data = (
            queryset.annotate(period=trunc_func("timestamp"))
            .values("period", "metric_name", "metric_type", "project", "tag")
            .annotate(
                value=Sum("metric_value"),
                count=Sum("metric_count"),
            )
            .order_by("period", "metric_name")
        )

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
            series["data"].append(
                {
                    "timestamp": row["period"].isoformat(),
                    "value": row["value"],
                    "count": row["count"],
                }
            )
            series["total_value"] += row["value"]
            series["total_count"] += row["count"]

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "granularity": granularity,
                "series": list(series_by_metric.values()),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="overview")
    @cache_metrics_response(endpoint="overview")
    def overview(self, request: Request) -> Response:
        """Get a quick overview of recent metrics.

        Returns last 7 days of key metrics for dashboard display.
        """
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)

        queryset = self.get_queryset().filter(
            timestamp__gte=start_date,
            timestamp__lte=end_date,
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

        # Get daily trend for the period
        daily_trend = (
            queryset.annotate(day=TruncDay("timestamp"))
            .values("day")
            .annotate(
                total_value=Sum("metric_value"),
                total_count=Sum("metric_count"),
            )
            .order_by("day")
        )

        return Response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": 7,
                },
                "totals": list(totals),
                "daily_trend": [
                    {
                        "date": row["day"].isoformat(),
                        "value": row["total_value"],
                        "count": row["total_count"],
                    }
                    for row in daily_trend
                ],
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

        organization = UserContext.get_organization()
        org_id = str(organization.id)

        summary = MetricsQueryService.get_all_metrics_summary(
            org_id,
            params["start_date"],
            params["end_date"],
        )

        return Response(
            {
                "start_date": params["start_date"].isoformat(),
                "end_date": params["end_date"].isoformat(),
                "source": "live",
                "metrics": [
                    {"metric_name": name, "total_value": value}
                    for name, value in summary.items()
                ],
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

        organization = UserContext.get_organization()
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
            except Exception as e:
                logger.error(f"Failed to fetch metric {metric_name}: {e}")
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

    def _apply_filters(self, queryset, params):
        """Apply common filters to queryset."""
        queryset = queryset.filter(
            timestamp__gte=params["start_date"],
            timestamp__lte=params["end_date"],
        )

        if params.get("metric_name"):
            queryset = queryset.filter(metric_name=params["metric_name"])

        if params.get("project"):
            queryset = queryset.filter(project=params["project"])

        if "tag" in params and params["tag"] is not None:
            queryset = queryset.filter(tag=params["tag"])

        return queryset

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
            logger.error(f"Database health check failed: {e}")
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
            logger.error(f"Cache health check failed: {e}")
            return {"status": "error", "message": str(e)}
