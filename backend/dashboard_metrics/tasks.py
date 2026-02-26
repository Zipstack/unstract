"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from celery import shared_task
from django.core.cache import cache
from django.db.utils import DatabaseError, OperationalError
from django.utils import timezone

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

    Uses a Redis distributed lock to prevent overlapping runs when a task
    takes longer than the 15-minute schedule interval.

    Aggregation windows:
    - Hourly: Last 24 hours (rolling window)
    - Daily: Last 2 days (to catch day boundaries)
    - Monthly: Current month (updates running total)

    Returns:
        Dict with aggregation summary for all three tiers
    """
    # Acquire distributed lock to prevent overlapping runs
    if not cache.add(AGGREGATION_LOCK_KEY, "running", AGGREGATION_LOCK_TIMEOUT):
        logger.info("Skipping aggregation — another run is in progress")
        return {"success": True, "skipped": True, "reason": "lock_held"}

    try:
        return _run_aggregation()
    finally:
        cache.delete(AGGREGATION_LOCK_KEY)


def _run_aggregation() -> dict[str, Any]:
    """Execute the actual aggregation logic.

    Separated from the task function to keep the lock management clean.
    """
    from account_v2.models import Organization
    from workflow_manager.workflow_v2.models.execution import WorkflowExecution

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
    metric_configs = [
        ("documents_processed", MetricsQueryService.get_documents_processed, False),
        ("pages_processed", MetricsQueryService.get_pages_processed, True),
        ("llm_calls", MetricsQueryService.get_llm_calls, False),
        ("challenges", MetricsQueryService.get_challenges, False),
        ("summarization_calls", MetricsQueryService.get_summarization_calls, False),
        ("deployed_api_requests", MetricsQueryService.get_deployed_api_requests, False),
        (
            "etl_pipeline_executions",
            MetricsQueryService.get_etl_pipeline_executions,
            False,
        ),
        ("llm_usage", MetricsQueryService.get_llm_usage_cost, True),
        ("prompt_executions", MetricsQueryService.get_prompt_executions, False),
        ("failed_pages", MetricsQueryService.get_failed_pages, True),
        ("hitl_reviews", MetricsQueryService.get_hitl_reviews, False),
        ("hitl_completions", MetricsQueryService.get_hitl_completions, False),
    ]

    stats = {
        "hourly": {"upserted": 0},
        "daily": {"upserted": 0},
        "monthly": {"upserted": 0},
        "errors": 0,
        "orgs_processed": 0,
    }

    # Pre-filter to orgs with recent activity to reduce DB load.
    # One lightweight query avoids running 36 queries per dormant org.
    active_org_ids = set(
        WorkflowExecution.objects.filter(
            created_at__gte=monthly_start,
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

    organizations = Organization.objects.filter(id__in=active_org_ids).only("id")

    for org in organizations:
        org_id = str(org.id)
        hourly_agg: dict[tuple, dict] = {}
        daily_agg: dict[tuple, dict] = {}
        monthly_agg: dict[tuple, dict] = {}

        try:
            for metric_name, query_method, is_histogram in metric_configs:
                metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

                try:
                    # === HOURLY AGGREGATION (last 24 hours) ===
                    hourly_results = query_method(
                        org_id, hourly_start, end_date, granularity=Granularity.HOUR
                    )
                    for row in hourly_results:
                        period = row["period"]
                        value = row["value"] or 0
                        hour_ts = _truncate_to_hour(period)
                        key = (org_id, hour_ts.isoformat(), metric_name, "default", "")

                        if key not in hourly_agg:
                            hourly_agg[key] = {
                                "metric_type": metric_type,
                                "value": 0,
                                "count": 0,
                            }
                        hourly_agg[key]["value"] += value
                        hourly_agg[key]["count"] += 1

                    # === DAILY AGGREGATION (last 7 days) ===
                    daily_results = query_method(
                        org_id, daily_start, end_date, granularity=Granularity.DAY
                    )
                    for row in daily_results:
                        period = row["period"]
                        value = row["value"] or 0
                        day_ts = _truncate_to_day(period)
                        key = (
                            org_id,
                            day_ts.date().isoformat(),
                            metric_name,
                            "default",
                            "",
                        )

                        if key not in daily_agg:
                            daily_agg[key] = {
                                "metric_type": metric_type,
                                "value": 0,
                                "count": 0,
                            }
                        daily_agg[key]["value"] += value
                        daily_agg[key]["count"] += 1

                    # === MONTHLY AGGREGATION (last 2 months) ===
                    monthly_results = query_method(
                        org_id, monthly_start, end_date, granularity=Granularity.DAY
                    )
                    # Group results by month and create separate records
                    monthly_buckets: dict[str, dict] = {}
                    for row in monthly_results:
                        period = row["period"]
                        value = row["value"] or 0
                        month_ts = _truncate_to_month(period)
                        month_key_str = month_ts.date().isoformat()

                        if month_key_str not in monthly_buckets:
                            monthly_buckets[month_key_str] = {"value": 0, "count": 0}
                        monthly_buckets[month_key_str]["value"] += value
                        monthly_buckets[month_key_str]["count"] += 1

                    # Create aggregation entries for each month
                    for month_key_str, bucket in monthly_buckets.items():
                        month_key = (
                            org_id,
                            month_key_str,
                            metric_name,
                            "default",
                            "",
                        )
                        monthly_agg[month_key] = {
                            "metric_type": metric_type,
                            "value": bucket["value"],
                            "count": bucket["count"] or 1,
                        }

                except Exception:
                    logger.exception("Error querying %s for org %s", metric_name, org_id)
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
