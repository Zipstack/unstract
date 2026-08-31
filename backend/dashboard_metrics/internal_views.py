"""Internal API for running the dashboard-metrics periodics (UN-3796).

Beat + ``workerMetrics`` are the last two Celery deployments blocking the
"scale every Celery deployment to zero" gate. The PG scheduler replaces Beat, but the
three ``dashboard_metrics.*`` tasks are **Django** — ORM, cache, a Redis lock — and the
PG consumer bootstraps its tasks from ``workers/`` with no Django, so it cannot run them
directly.

These endpoints are the execution half, following the pattern already used by
``ProcessLogHistoryAPIView`` / ``process_notification_buffer``: a thin worker-side task
POSTs here, and the backend runs the real function. The task bodies are plain functions
that happen to carry ``@shared_task``, so they are called **verbatim** — the aggregation
logic, its windows and its Redis lock are reused unchanged, not reimplemented.

Auth is entirely ``InternalAPIAuthMiddleware``, which fires on any ``/internal/`` path.

**Org context is deliberately absent.** The Celery path runs with no organization set —
which is why ``tasks.py`` uses ``_base_manager`` throughout — and the middleware
populates ``StateStore`` from ``X-Organization-ID``. The callers must not send that
header, and each view clears the slot defensively: ``StateStore`` is a thread-local and
gunicorn reuses threads, so a value left behind by an earlier request on the same thread
would silently scope these global aggregations to one tenant.
"""

import contextlib
import logging
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.constants import Account
from utils.local_context import StateStore

from dashboard_metrics.tasks import (
    aggregate_metrics_from_sources,
    cleanup_daily_metrics,
    cleanup_hourly_metrics,
)

logger = logging.getLogger(__name__)

# Mirrors the defaults the Beat rows carry in their kwargs
# (dashboard_metrics/migrations/0002_setup_periodic_tasks.py), so a caller that omits
# them gets the same retention the Celery path applies.
DEFAULT_HOURLY_RETENTION_DAYS = 30
DEFAULT_DAILY_RETENTION_DAYS = 365


def _clear_org_context() -> None:
    """Drop any organization left in this thread's StateStore. See the module docstring.

    ``suppress`` because ``StateStore.clear`` raises when the slot was never set, which
    is the normal case and not an error.
    """
    with contextlib.suppress(Exception):
        StateStore.clear(Account.ORGANIZATION_ID)


def _int_arg(request: Request, key: str, default: int) -> int:
    """Read an optional positive integer from the request body."""
    raw = request.data.get(key, default) if isinstance(request.data, dict) else default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{key} must be >= 1, got {value}")
    return value


class _MetricsTaskAPIView(APIView):
    """Shared plumbing: clear org context, run, translate errors."""

    def _run(self, fn, *args: Any, **kwargs: Any) -> Response:
        _clear_org_context()
        try:
            return Response(fn(*args, **kwargs))
        except ValueError as exc:  # bad request body
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("dashboard-metrics internal call failed: %s", exc, exc_info=True)
            return Response(
                {"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AggregateMetricsAPIView(_MetricsTaskAPIView):
    """Run the metrics aggregation.

    Calls the Celery task body verbatim, Redis lock included — this endpoint exists
    only because the PG consumer has no Django, not to change what the job does.
    """

    def post(self, request: Request) -> Response:
        return self._run(aggregate_metrics_from_sources)


class CleanupHourlyMetricsAPIView(_MetricsTaskAPIView):
    def post(self, request: Request) -> Response:
        try:
            days = _int_arg(request, "retention_days", DEFAULT_HOURLY_RETENTION_DAYS)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._run(cleanup_hourly_metrics, retention_days=days)


class CleanupDailyMetricsAPIView(_MetricsTaskAPIView):
    def post(self, request: Request) -> Response:
        try:
            days = _int_arg(request, "retention_days", DEFAULT_DAILY_RETENTION_DAYS)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._run(cleanup_daily_metrics, retention_days=days)
