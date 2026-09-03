"""Internal API URLs for the dashboard-metrics periodics (UN-3796).

Called by the thin worker tasks that the PG scheduler fires, replacing Beat +
``workerMetrics``. Mirrors the shape of ``execution_log_internal_urls``.
"""

from django.urls import path

from . import internal_views

app_name = "dashboard_metrics_internal"

urlpatterns = [
    path(
        "aggregate/",
        internal_views.AggregateMetricsAPIView.as_view(),
        name="aggregate_metrics",
    ),
    path(
        "cleanup/hourly/",
        internal_views.CleanupHourlyMetricsAPIView.as_view(),
        name="cleanup_hourly_metrics",
    ),
    path(
        "cleanup/daily/",
        internal_views.CleanupDailyMetricsAPIView.as_view(),
        name="cleanup_daily_metrics",
    ),
]
