"""Thin PG-side tasks for the dashboard-metrics periodics (UN-3796).

These replace ``workerMetrics`` (``celery -A backend worker -Q dashboard_metric_events``)
once the matching schedules are adopted by the PG scheduler. They do **no** work
themselves: each POSTs to a backend internal endpoint that calls the real Django
function, mirroring ``log_consumer/process_log_history.py`` and
``process_notification_buffer.py``. The workers image has no Django, so the ORM-heavy
aggregation cannot run here.

**Registered under the exact Beat task names.** That is deliberate: the mirror copies a
Beat row verbatim (task, queue, args, kwargs), so matching names mean no remap table and
``--release`` stays a true inverse. The same name therefore exists in two registries —
the backend image (the Django implementation, consumed by Celery) and this one (the HTTP
proxy, consumed by ``worker-pg-metrics``). They are separate processes with separate
registries and neither imports the other; the name is a logical contract, not a symbol
clash. A reader who assumes otherwise will be very confused, hence this paragraph.

Redelivery is safe without extra guards: the backend's upserts are
``INSERT … ON CONFLICT DO UPDATE SET`` (overwrite with recomputed values, not
increment) and the cleanups are ``DELETE … WHERE ts < cutoff``, so a double-run costs
duplicate DB work, never wrong numbers.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from queue_backend import worker_task
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)

# Sits just above gunicorn's --timeout 600, which is the ceiling that actually applies
# here (the task's Celery soft_time_limit=600 / time_limit=660 govern the Celery path,
# where a Celery worker runs the body in-process — not this one). Above it so a long
# aggregation surfaces the SERVER's error; a shorter client timeout would abort first
# and read as a network fault while the server kept working.
DEFAULT_HTTP_TIMEOUT_SECONDS = 630.0

_AGGREGATE_PATH = "v1/dashboard-metrics/aggregate/"
_CLEANUP_HOURLY_PATH = "v1/dashboard-metrics/cleanup/hourly/"
_CLEANUP_DAILY_PATH = "v1/dashboard-metrics/cleanup/daily/"


def _call_internal(
    path: str,
    *,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call a backend internal endpoint and return its decoded body.

    Single seam so tests have one thing to patch.

    **Raises** on any failure, unlike ``process_log_history.py`` which returns False.
    That script is driven by a bash loop with no other channel; this runs inside a PG
    consumer, where raising is what marks the message failed and gets it logged loudly
    (with ``MAX_ATTEMPTS=1`` it is then dropped rather than retried — the next cron tick
    supersedes it).

    Never sends ``X-Organization-ID``: these are global aggregations, and the middleware
    would otherwise scope every ORM read in them to a single tenant.
    """
    base_url = os.getenv("INTERNAL_API_BASE_URL")
    api_key = os.getenv("INTERNAL_SERVICE_API_KEY")
    if not base_url:
        raise RuntimeError("INTERNAL_API_BASE_URL environment variable not set")
    if not api_key:
        raise RuntimeError("INTERNAL_SERVICE_API_KEY environment variable not set")

    url = f"{base_url.rstrip('/')}/{path}"
    # Transport-level retries only — these re-establish a connection that never
    # delivered the request. They do NOT re-send after the server received it, which
    # matters: a retry on a slow-but-live aggregation would run it twice concurrently.
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(transport=transport) as client:
        response = client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=timeout,
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"{method} {path} failed: HTTP {response.status_code} {response.text[:500]}"
        )
    return response.json()


def _log_if_skipped(name: str, result: dict[str, Any]) -> None:
    """Surface a lock-held no-op.

    The backend returns success with ``skipped=True`` when the Redis lock is held. That
    is correct behaviour, but left at INFO a permanently leaked lock looks like 96
    successful runs a day that did nothing.
    """
    if result.get("skipped"):
        logger.warning(
            "%s did no work: %s", name, result.get("reason", "reported skipped=True")
        )


@worker_task(name="dashboard_metrics.aggregate_from_sources")
def dashboard_metrics_aggregate(
    tier: str | None = None, source_window_days: int | None = None
) -> dict[str, Any]:
    """Aggregate source tables into the hourly/daily/monthly metrics tables.

    Both kwargs come from the schedule row and both are optional: ``tier`` selects
    which tiers to write, ``source_window_days`` widens the daily lookback for the
    reconciliation pass. Omitting either applies the backend task's own default.
    """
    body = {
        key: value
        for key, value in (
            ("tier", tier),
            ("source_window_days", source_window_days),
        )
        if value is not None
    } or None
    result = _call_internal(_AGGREGATE_PATH, body=body)
    _log_if_skipped("dashboard_metrics.aggregate_from_sources", result)
    return result


@worker_task(name="dashboard_metrics.cleanup_hourly_data")
def dashboard_metrics_cleanup_hourly(retention_days: int | None = None) -> dict[str, Any]:
    """Delete hourly metrics older than the retention window."""
    body = {"retention_days": retention_days} if retention_days is not None else None
    return _call_internal(_CLEANUP_HOURLY_PATH, body=body)


@worker_task(name="dashboard_metrics.cleanup_daily_data")
def dashboard_metrics_cleanup_daily(retention_days: int | None = None) -> dict[str, Any]:
    """Delete daily metrics older than the retention window."""
    body = {"retention_days": retention_days} if retention_days is not None else None
    return _call_internal(_CLEANUP_DAILY_PATH, body=body)
