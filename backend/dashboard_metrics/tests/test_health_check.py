"""``metrics/health/`` must not hand infrastructure details to the caller.

The endpoint answers any org member. A failing DB or cache raises an exception
whose text names the host, port and user; that belongs in the server log, not
the response body (CodeQL py/stack-trace-exposure).
"""

from unittest import mock

from rest_framework import status
from rest_framework.test import APIRequestFactory

from dashboard_metrics import views
from dashboard_metrics.views import DashboardMetricsViewSet

DB_ERROR = (
    'connection to server at "db.internal" (10.0.0.5), port 5432 failed: '
    'FATAL: password authentication failed for user "unstract_dev"'
)
CACHE_ERROR = "Error 111 connecting to redis.internal:6379. Connection refused."


def _health():
    viewset = DashboardMetricsViewSet()
    request = APIRequestFactory().get("/metrics/health/")
    return viewset.health(request)


def test_database_failure_hides_exception_text_and_logs_it():
    with (
        mock.patch.object(
            views.EventMetricsHourly.objects, "exists", side_effect=Exception(DB_ERROR)
        ),
        mock.patch.object(views.cache, "set"),
        mock.patch.object(views.cache, "get", return_value="ok"),
        mock.patch.object(views.logger, "exception") as log_exception,
    ):
        response = _health()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["healthy"] is False
    assert response.data["checks"]["database"] == {
        "status": "error",
        "message": "Database unavailable",
    }
    assert response.data["checks"]["cache"] == {"status": "ok"}
    assert "db.internal" not in str(response.data)
    log_exception.assert_called_once_with("Database health check failed")


def test_cache_failure_hides_exception_text_and_logs_it():
    with (
        mock.patch.object(views.EventMetricsHourly.objects, "exists", return_value=True),
        mock.patch.object(views.cache, "set", side_effect=Exception(CACHE_ERROR)),
        mock.patch.object(views.logger, "exception") as log_exception,
    ):
        response = _health()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["checks"]["cache"] == {
        "status": "error",
        "message": "Cache unavailable",
    }
    assert "redis.internal" not in str(response.data)
    log_exception.assert_called_once_with("Cache health check failed")


def test_all_healthy_is_200():
    with (
        mock.patch.object(views.EventMetricsHourly.objects, "exists", return_value=True),
        mock.patch.object(views.cache, "set"),
        mock.patch.object(views.cache, "get", return_value="ok"),
    ):
        response = _health()

    assert response.status_code == status.HTTP_200_OK
    assert response.data["healthy"] is True
