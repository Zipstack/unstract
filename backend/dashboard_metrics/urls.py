"""URL configuration for Dashboard Metrics API."""

from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import DashboardMetricsViewSet

# ViewSet action mappings
metrics_list = DashboardMetricsViewSet.as_view({"get": "list"})
metrics_detail = DashboardMetricsViewSet.as_view({"get": "retrieve"})
metrics_summary = DashboardMetricsViewSet.as_view({"get": "summary"})
metrics_series = DashboardMetricsViewSet.as_view({"get": "series"})
metrics_overview = DashboardMetricsViewSet.as_view({"get": "overview"})
metrics_live_summary = DashboardMetricsViewSet.as_view({"get": "live_summary"})
metrics_live_series = DashboardMetricsViewSet.as_view({"get": "live_series"})
metrics_health = DashboardMetricsViewSet.as_view({"get": "health"})

urlpatterns = format_suffix_patterns(
    [
        # Main list endpoint
        path("", metrics_list, name="metrics-list"),
        # Summary statistics
        path("summary/", metrics_summary, name="metrics-summary"),
        # Time series data
        path("series/", metrics_series, name="metrics-series"),
        # Quick overview (last 7 days)
        path("overview/", metrics_overview, name="metrics-overview"),
        # Live data from source tables
        path("live-summary/", metrics_live_summary, name="metrics-live-summary"),
        path("live-series/", metrics_live_series, name="metrics-live-series"),
        # Health check endpoint
        path("health/", metrics_health, name="metrics-health"),
        # Individual metric detail
        path("<uuid:pk>/", metrics_detail, name="metrics-detail"),
    ]
)
