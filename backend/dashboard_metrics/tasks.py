"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from account_v2.models import Organization
from celery import shared_task
from django.core.cache import cache
from django.db.utils import DatabaseError, OperationalError
from django.utils import timezone
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from .models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    Granularity,
    MetricType,
)
from .services import MetricsQueryService

logger = logging.getLogger(__name__)

# Retention periods for metrics cleanup
DASHBOARD_HOURLY_METRICS_RETENTION_DAYS = 30
DASHBOARD_DAILY_METRICS_RETENTION_DAYS = 365


def _truncate_to_hour(ts: float | datetime) -> datetime:
    """Truncate a timestamp to the hour.

    Args:
        ts: Unix timestamp (float) or datetime object

    Returns:
        datetime truncated to the hour in UTC
    """
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        dt = ts if ts.tzinfo else timezone.make_aware(ts, timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def _truncate_to_day(ts: datetime) -> datetime:
    """Truncate a datetime to midnight (start of day).

    Args:
        ts: datetime object

    Returns:
        datetime truncated to midnight
    """
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _truncate_to_month(ts: datetime) -> datetime:
    """Truncate a datetime to first day of month.

    Args:
        ts: datetime object

    Returns:
        datetime set to first day of month at midnight
    """
    return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _bulk_upsert_hourly(aggregations: dict) -> int:
    """Bulk upsert hourly aggregations using INSERT ... ON CONFLICT.

    Uses bulk_create with update_conflicts to perform a single SQL statement
    instead of N×2 roundtrips (SELECT + INSERT/UPDATE per row).

    Uses _base_manager to bypass DefaultOrganizationManagerMixin which
    filters by UserContext.get_organization() — returns None in Celery context.

    Args:
        aggregations: Dict of aggregated metric data keyed by
            (org_id, hour_ts_str, metric_name, project, tag)

    Returns:
        Number of rows upserted
    """
    objects = []
    for key, agg in aggregations.items():
        org_id, hour_ts_str, metric_name, project, tag = key
        objects.append(
            EventMetricsHourly(
                organization_id=org_id,
                timestamp=datetime.fromisoformat(hour_ts_str),
                metric_name=metric_name,
                project=project,
                tag=tag,
                metric_type=agg["metric_type"],
                metric_value=agg["value"],
                metric_count=agg["count"],
            )
        )

    if not objects:
        return 0

    EventMetricsHourly._base_manager.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["organization", "timestamp", "metric_name", "project", "tag"],
        update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
    )
    return len(objects)


def _bulk_upsert_daily(aggregations: dict) -> int:
    """Bulk upsert daily aggregations using INSERT ... ON CONFLICT.

    Uses _base_manager to bypass DefaultOrganizationManagerMixin.

    Args:
        aggregations: Dict keyed by (org_id, date_str, metric_name, project, tag)

    Returns:
        Number of rows upserted
    """
    objects = []
    for key, agg in aggregations.items():
        org_id, date_str, metric_name, project, tag = key
        objects.append(
            EventMetricsDaily(
                organization_id=org_id,
                date=datetime.fromisoformat(date_str).date(),
                metric_name=metric_name,
                project=project,
                tag=tag,
                metric_type=agg["metric_type"],
                metric_value=agg["value"],
                metric_count=agg["count"],
            )
        )

    if not objects:
        return 0

    EventMetricsDaily._base_manager.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["organization", "date", "metric_name", "project", "tag"],
        update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
    )
    return len(objects)


def _bulk_upsert_monthly(aggregations: dict) -> int:
    """Bulk upsert monthly aggregations using INSERT ... ON CONFLICT.

    Uses _base_manager to bypass DefaultOrganizationManagerMixin.

    Args:
        aggregations: Dict keyed by (org_id, month_str, metric_name, project, tag)

    Returns:
        Number of rows upserted
    """
    objects = []
    for key, agg in aggregations.items():
        org_id, month_str, metric_name, project, tag = key
        objects.append(
            EventMetricsMonthly(
                organization_id=org_id,
                month=datetime.fromisoformat(month_str).date(),
                metric_name=metric_name,
                project=project,
                tag=tag,
                metric_type=agg["metric_type"],
                metric_value=agg["value"],
                metric_count=agg["count"],
            )
        )

    if not objects:
        return 0

    EventMetricsMonthly._base_manager.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["organization", "month", "metric_name", "project", "tag"],
        update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
    )
    return len(objects)


AGGREGATION_LOCK_KEY = "dashboard_metrics:aggregation_lock"
AGGREGATION_LOCK_TIMEOUT = 900  # 15 minutes (matches task schedule)


def _acquire_aggregation_lock() -> bool:
    """Acquire the distributed aggregation lock with self-healing.

    Stores a Unix timestamp as the lock value. If a previous run crashed
    (OOM kill, SIGKILL) without releasing the lock, the next run detects
    that the lock is older than AGGREGATION_LOCK_TIMEOUT and reclaims it.

    Returns:
        True if lock was acquired, False if another run is legitimately active.
    """
    now = time.time()

    # Fast path: lock is free
    if cache.add(AGGREGATION_LOCK_KEY, str(now), AGGREGATION_LOCK_TIMEOUT):
        return True

    # Lock exists — check if it's stale (previous run died without releasing)
    lock_value = cache.get(AGGREGATION_LOCK_KEY)
    if lock_value is None:
        # Expired between our check and get — race is fine, next run will pick up
        return False

    try:
        lock_time = float(lock_value)
    except (TypeError, ValueError):
        # Corrupted value (e.g. old "running" string) — reclaim it
        logger.warning("Reclaiming aggregation lock with invalid value: %s", lock_value)
        cache.delete(AGGREGATION_LOCK_KEY)
        return cache.add(AGGREGATION_LOCK_KEY, str(now), AGGREGATION_LOCK_TIMEOUT)

    age = now - lock_time
    if age > AGGREGATION_LOCK_TIMEOUT:
        logger.warning(
            "Reclaiming stale aggregation lock (age=%.0fs, timeout=%ds)",
            age,
            AGGREGATION_LOCK_TIMEOUT,
        )
        cache.delete(AGGREGATION_LOCK_KEY)
        return cache.add(AGGREGATION_LOCK_KEY, str(now), AGGREGATION_LOCK_TIMEOUT)

    return False


@shared_task(
    name="dashboard_metrics.aggregate_from_sources",
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
    autoretry_for=(DatabaseError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=300,
)
def aggregate_metrics_from_sources() -> dict[str, Any]:
    """Aggregate metrics from source tables into hourly, daily, and monthly tables.

    This task runs periodically (every 15 minutes) to query metrics from
    source tables (Usage, PageUsage, WorkflowExecution, etc.) and aggregate
    them into EventMetricsHourly, EventMetricsDaily, and EventMetricsMonthly
    tables for fast dashboard queries at different granularities.

    Uses a Redis distributed lock with self-healing to prevent overlapping
    runs. If a previous run was killed without releasing the lock, the next
    run detects the stale lock and reclaims it automatically.

    Aggregation windows:
    - Hourly: Last 24 hours (rolling window)
    - Daily: Last 7 days (ensures we capture late-arriving data)
    - Monthly: Last 2 months (current + previous month)

    Returns:
        Dict with aggregation summary for all three tiers
    """
    if not _acquire_aggregation_lock():
        logger.info("Skipping aggregation — another run is in progress")
        return {"success": True, "skipped": True, "reason": "lock_held"}

    try:
        return _run_aggregation()
    finally:
        cache.delete(AGGREGATION_LOCK_KEY)


def _aggregate_single_metric(
    query_method,
    metric_name: str,
    metric_type: str,
    org_id: str,
    hourly_start: datetime,
    daily_start: datetime,
    monthly_start: datetime,
    end_date: datetime,
    hourly_agg: dict,
    daily_agg: dict,
    monthly_agg: dict,
    extra_kwargs: dict | None = None,
) -> None:
    """Run a single metric query at all 3 granularities and populate agg dicts.

    Uses 2 queries instead of 3: the daily query is widened to monthly_start
    and its results are split into both daily_agg and monthly_agg in Python.
    This is the same pattern proven in the backfill management command.
    """
    extra_kwargs = extra_kwargs or {}

    # === HOURLY (last 24h) ===
    for row in query_method(
        org_id,
        hourly_start,
        end_date,
        granularity=Granularity.HOUR,
        **extra_kwargs,
    ):
        value = row["value"] or 0
        hour_ts = _truncate_to_hour(row["period"])
        key = (org_id, hour_ts.isoformat(), metric_name, "default", "")
        if key not in hourly_agg:
            hourly_agg[key] = {"metric_type": metric_type, "value": 0, "count": 0}
        hourly_agg[key]["value"] += value
        hourly_agg[key]["count"] += 1

    # === DAILY + MONTHLY (single query from monthly_start) ===
    # Query with DAY granularity from monthly_start (2 months back).
    # Each row is bucketed into daily_agg if within daily window,
    # and always bucketed into monthly_agg for the month rollup.
    monthly_buckets: dict[str, dict] = {}
    for row in query_method(
        org_id,
        monthly_start,
        end_date,
        granularity=Granularity.DAY,
        **extra_kwargs,
    ):
        value = row["value"] or 0
        day_ts = _truncate_to_day(row["period"])

        # Daily: only include rows within the daily window
        if day_ts >= daily_start:
            key = (org_id, day_ts.date().isoformat(), metric_name, "default", "")
            if key not in daily_agg:
                daily_agg[key] = {"metric_type": metric_type, "value": 0, "count": 0}
            daily_agg[key]["value"] += value
            daily_agg[key]["count"] += 1

        # Monthly: bucket all rows by month
        month_key_str = _truncate_to_month(row["period"]).date().isoformat()
        if month_key_str not in monthly_buckets:
            monthly_buckets[month_key_str] = {"value": 0, "count": 0}
        monthly_buckets[month_key_str]["value"] += value
        monthly_buckets[month_key_str]["count"] += 1

    for month_key_str, bucket in monthly_buckets.items():
        key = (org_id, month_key_str, metric_name, "default", "")
        monthly_agg[key] = {
            "metric_type": metric_type,
            "value": bucket["value"],
            "count": bucket["count"] or 1,
        }


def _aggregate_llm_combined(
    org_id: str,
    hourly_start: datetime,
    daily_start: datetime,
    monthly_start: datetime,
    end_date: datetime,
    hourly_agg: dict,
    daily_agg: dict,
    monthly_agg: dict,
    llm_combined_fields: dict,
) -> None:
    """Run the combined LLM metrics query at all granularities.

    Issues 2 queries total (hourly + daily/monthly) instead of 3.
    The DAY-granularity query is widened to monthly_start and results are
    split into daily_agg (recent rows) and monthly_agg (all rows bucketed
    by month) in Python. Same pattern as _aggregate_single_metric.
    """
    # === HOURLY (last 24h) ===
    hourly_results = MetricsQueryService.get_llm_metrics_combined(
        org_id,
        hourly_start,
        end_date,
        granularity=Granularity.HOUR,
    )
    for row in hourly_results:
        ts = _truncate_to_hour(row["period"])
        ts_str = ts.isoformat()
        for field, (metric_name, metric_type) in llm_combined_fields.items():
            value = row[field] or 0
            key = (org_id, ts_str, metric_name, "default", "")
            if key not in hourly_agg:
                hourly_agg[key] = {"metric_type": metric_type, "value": 0, "count": 0}
            hourly_agg[key]["value"] += value
            hourly_agg[key]["count"] += 1

    # === DAILY + MONTHLY (single query from monthly_start) ===
    daily_monthly_results = MetricsQueryService.get_llm_metrics_combined(
        org_id,
        monthly_start,
        end_date,
        granularity=Granularity.DAY,
    )
    monthly_buckets: dict[tuple[str, str], dict] = {}
    for row in daily_monthly_results:
        day_ts = _truncate_to_day(row["period"])

        # Daily: only include rows within the daily window
        if day_ts >= daily_start:
            ts_str = day_ts.date().isoformat()
            for field, (metric_name, metric_type) in llm_combined_fields.items():
                value = row[field] or 0
                key = (org_id, ts_str, metric_name, "default", "")
                if key not in daily_agg:
                    daily_agg[key] = {"metric_type": metric_type, "value": 0, "count": 0}
                daily_agg[key]["value"] += value
                daily_agg[key]["count"] += 1

        # Monthly: bucket all rows by month
        month_key_str = _truncate_to_month(row["period"]).date().isoformat()
        for field, (metric_name, metric_type) in llm_combined_fields.items():
            value = row[field] or 0
            bkey = (month_key_str, metric_name)
            if bkey not in monthly_buckets:
                monthly_buckets[bkey] = {
                    "metric_type": metric_type,
                    "value": 0,
                    "count": 0,
                }
            monthly_buckets[bkey]["value"] += value
            monthly_buckets[bkey]["count"] += 1

    for (month_key_str, metric_name), bucket in monthly_buckets.items():
        key = (org_id, month_key_str, metric_name, "default", "")
        monthly_agg[key] = {
            "metric_type": bucket["metric_type"],
            "value": bucket["value"],
            "count": bucket["count"] or 1,
        }


def _run_aggregation() -> dict[str, Any]:
    """Execute the actual aggregation logic.

    Separated from the task function to keep the lock management clean.
    """
    end_date = timezone.now()

    # Query windows for each granularity
    # - Hourly: Last 24 hours (rolling window, matches retention of 30 days)
    # - Daily: Last 7 days (ensures we capture late-arriving data)
    # - Monthly: Last 2 months (current + previous, ensures month transitions are captured)
    hourly_start = end_date - timedelta(hours=24)
    daily_start = end_date - timedelta(days=7)
    # Include previous month to handle month boundaries
    if end_date.month == 1:
        monthly_start = end_date.replace(
            year=end_date.year - 1,
            month=12,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        monthly_start = end_date.replace(
            month=end_date.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    # Metric definitions: (name, query_method, is_histogram)
    # Note: llm_calls, challenges, summarization_calls, and llm_usage are
    # handled separately via get_llm_metrics_combined (1 query instead of 4).
    metric_configs = [
        ("documents_processed", MetricsQueryService.get_documents_processed, False),
        ("pages_processed", MetricsQueryService.get_pages_processed, True),
        ("deployed_api_requests", MetricsQueryService.get_deployed_api_requests, False),
        (
            "etl_pipeline_executions",
            MetricsQueryService.get_etl_pipeline_executions,
            False,
        ),
        ("prompt_executions", MetricsQueryService.get_prompt_executions, False),
        ("failed_pages", MetricsQueryService.get_failed_pages, True),
        ("hitl_reviews", MetricsQueryService.get_hitl_reviews, False),
        ("hitl_completions", MetricsQueryService.get_hitl_completions, False),
    ]

    # LLM metrics combined via conditional aggregation (4 metrics in 1 query).
    # Maps combined query field -> (metric_name, metric_type)
    llm_combined_fields = {
        "llm_calls": ("llm_calls", MetricType.COUNTER),
        "challenges": ("challenges", MetricType.COUNTER),
        "summarization_calls": ("summarization_calls", MetricType.COUNTER),
        "llm_usage": ("llm_usage", MetricType.HISTOGRAM),
    }

    stats = {
        "hourly": {"upserted": 0},
        "daily": {"upserted": 0},
        "monthly": {"upserted": 0},
        "errors": 0,
        "orgs_processed": 0,
    }

    # Pre-filter to orgs with recent activity to reduce DB load.
    # Uses daily_start (7 days) instead of monthly_start (2 months) because:
    # - Hourly/daily queries only need recent data (24h / 7d windows)
    # - Monthly totals for dormant orgs were already written by previous
    #   runs when the org was active — re-running just overwrites same values
    # - This avoids 28 queries per dormant org that had activity 2-8 weeks ago
    active_org_ids = set(
        WorkflowExecution.objects.filter(
            created_at__gte=daily_start,
        )
        .values_list("workflow__organization_id", flat=True)
        .distinct()
    )
    total_orgs = Organization.objects.count()
    logger.info(
        "Aggregation: %d active orgs out of %d total",
        len(active_org_ids),
        total_orgs,
    )

    if not active_org_ids:
        return {
            "success": True,
            "organizations_processed": 0,
            "hourly": stats["hourly"],
            "daily": stats["daily"],
            "monthly": stats["monthly"],
            "errors": 0,
            "skipped_reason": "no_active_orgs",
        }

    organizations = Organization.objects.filter(id__in=active_org_ids).only(
        "id", "organization_id"
    )

    for org in organizations:
        org_id = str(org.id)
        org_identifier = org.organization_id  # Pre-resolved for PageUsage queries
        hourly_agg: dict[tuple, dict] = {}
        daily_agg: dict[tuple, dict] = {}
        monthly_agg: dict[tuple, dict] = {}

        try:
            for metric_name, query_method, is_histogram in metric_configs:
                metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

                # Pass org_identifier to PageUsage-based metrics to
                # avoid redundant Organization lookups per call.
                extra_kwargs = {}
                if metric_name == "pages_processed":
                    extra_kwargs["org_identifier"] = org_identifier

                try:
                    _aggregate_single_metric(
                        query_method,
                        metric_name,
                        metric_type,
                        org_id,
                        hourly_start,
                        daily_start,
                        monthly_start,
                        end_date,
                        hourly_agg,
                        daily_agg,
                        monthly_agg,
                        extra_kwargs,
                    )
                except Exception:
                    logger.exception("Error querying %s for org %s", metric_name, org_id)
                    stats["errors"] += 1

            # Combined LLM metrics: 1 query per granularity instead of 4
            try:
                _aggregate_llm_combined(
                    org_id,
                    hourly_start,
                    daily_start,
                    monthly_start,
                    end_date,
                    hourly_agg,
                    daily_agg,
                    monthly_agg,
                    llm_combined_fields,
                )
            except Exception:
                logger.exception("Error querying combined LLM metrics for org %s", org_id)
                stats["errors"] += 1

            # Bulk upsert all three tiers (single INSERT...ON CONFLICT each)
            if hourly_agg:
                stats["hourly"]["upserted"] += _bulk_upsert_hourly(hourly_agg)

            if daily_agg:
                stats["daily"]["upserted"] += _bulk_upsert_daily(daily_agg)

            if monthly_agg:
                stats["monthly"]["upserted"] += _bulk_upsert_monthly(monthly_agg)

            stats["orgs_processed"] += 1

        except Exception as e:
            logger.exception(f"Error processing org {org_id}: {e}")
            stats["errors"] += 1

    logger.info(
        f"Aggregation completed: {stats['orgs_processed']} orgs, "
        f"hourly={stats['hourly']['upserted']}, "
        f"daily={stats['daily']['upserted']}, "
        f"monthly={stats['monthly']['upserted']}, "
        f"errors={stats['errors']}"
    )

    return {
        "success": True,
        "organizations_processed": stats["orgs_processed"],
        "hourly": stats["hourly"],
        "daily": stats["daily"],
        "monthly": stats["monthly"],
        "errors": stats["errors"],
        "period": {
            "hourly": {"start": hourly_start.isoformat(), "end": end_date.isoformat()},
            "daily": {"start": daily_start.isoformat(), "end": end_date.isoformat()},
            "monthly": {"start": monthly_start.isoformat(), "end": end_date.isoformat()},
        },
    }


@shared_task(
    name="dashboard_metrics.cleanup_hourly_data",
    max_retries=3,
    autoretry_for=(DatabaseError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=300,
)
def cleanup_hourly_metrics(
    retention_days: int = DASHBOARD_HOURLY_METRICS_RETENTION_DAYS,
) -> dict[str, Any]:
    """Remove hourly metrics older than retention period.

    Args:
        retention_days: Number of days to retain hourly data (default: 30)

    Returns:
        Dict with deletion summary
    """
    cutoff = timezone.now() - timedelta(days=retention_days)

    try:
        # Use _base_manager to bypass DefaultOrganizationManagerMixin
        # (UserContext is None in Celery tasks)
        deleted_count, _ = EventMetricsHourly._base_manager.filter(
            timestamp__lt=cutoff
        ).delete()

        logger.info(
            f"Cleanup completed: deleted {deleted_count} hourly records "
            f"older than {retention_days} days"
        )

        return {
            "success": True,
            "deleted": deleted_count,
            "cutoff_date": cutoff.isoformat(),
            "retention_days": retention_days,
        }

    except Exception as e:
        logger.exception("Error during hourly cleanup")
        return {
            "success": False,
            "error": str(e),
            "retention_days": retention_days,
        }


@shared_task(
    name="dashboard_metrics.cleanup_daily_data",
    max_retries=3,
    autoretry_for=(DatabaseError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=300,
)
def cleanup_daily_metrics(
    retention_days: int = DASHBOARD_DAILY_METRICS_RETENTION_DAYS,
) -> dict[str, Any]:
    """Remove daily metrics older than retention period.

    Args:
        retention_days: Number of days to retain daily data (default: 365)

    Returns:
        Dict with deletion summary
    """
    cutoff = (timezone.now() - timedelta(days=retention_days)).date()

    try:
        # Use _base_manager to bypass DefaultOrganizationManagerMixin
        # (UserContext is None in Celery tasks)
        deleted_count, _ = EventMetricsDaily._base_manager.filter(
            date__lt=cutoff
        ).delete()

        logger.info(
            f"Cleanup completed: deleted {deleted_count} daily records "
            f"older than {retention_days} days"
        )

        return {
            "success": True,
            "deleted": deleted_count,
            "cutoff_date": cutoff.isoformat(),
            "retention_days": retention_days,
        }

    except Exception as e:
        logger.exception("Error during daily cleanup")
        return {
            "success": False,
            "error": str(e),
            "retention_days": retention_days,
        }
