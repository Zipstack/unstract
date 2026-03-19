"""Django app configuration for dashboard_metrics."""

from django.apps import AppConfig


class DashboardMetricsConfig(AppConfig):
    """Configuration for the Dashboard Metrics app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard_metrics"
    verbose_name = "Dashboard Metrics"
