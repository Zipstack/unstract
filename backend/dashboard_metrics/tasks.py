"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Any

from account_v2.models import Organization
from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.db.models import Min, Sum
from django.db.models.functions import TruncMonth
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

# Django 4.2's PostgreSQL backend does not override bulk_batch_size, so an
# unbatched bulk_create emits one statement whose size scales with tenant count.
MONTHLY_ROLLUP_BATCH_SIZE = 1000

# Retention periods for metrics cleanup
DASHBOARD_HOURLY_METRICS_RETENTION_DAYS = 30
DASHBOARD_DAILY_METRICS_RETENTION_DAYS = 365

# Daily-tier source lookback, sized against the worst observed
# created_at -> terminal-status lag.
DASHBOARD_SOURCE_WINDOW_DAYS = 2

# Wider lookback for the once-daily reconciliation pass. A migration must not
# import live app code, so 0005_add_reconciliation_task carries this as a literal
# in the schedule row's kwargs — editing this constant does not move the schedule.
DASHBOARD_RECONCILE_WINDOW_DAYS = 7

# Wider than the source window: metrics keyed on another column
# (e.g. approved_at) can land for an org whose executions are older.
DASHBOARD_ACTIVE_ORG_LOOKBACK_DAYS = 7


def _upsert_agg(agg: dict, key: tuple, metric_type: str, value: float) -> None:
    """Add a value to an aggregation dict, creating the entry if needed."""
    if key not in agg:
        agg[key] = {"metric_type": metric_type, "value": 0, "count": 0}
    agg[key]["value"] += value
    agg[key]["count"] += 1


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
        update_fields=["metric_type", "metric_value", "metric_count"],
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
        update_fields=["metric_type", "metric_value", "metric_count"],
    )
    return len(objects)


def _delete_orphan_monthly(objects: list[EventMetricsMonthly]) -> int:
    """Drop stale monthly rows inside the partitions the rollup actually covered.

    Monthly derives from the daily tier, so a key with no daily rows left must
    not survive as a stale total. An (organization, month) the rollup produced
    nothing for is left alone instead: absent daily rows there mean an
    incomplete tier, not a metric that went to zero.
    """
    fresh_keys = {
        (o.organization_id, o.month, o.metric_name, o.project, o.tag) for o in objects
    }
    covered: dict[date, set] = {}
    for o in objects:
        covered.setdefault(o.month, set()).add(o.organization_id)

    deleted = 0
    for month, org_ids in covered.items():
        stale_pks = [
            row["pk"]
            for row in EventMetricsMonthly._base_manager.filter(
                month=month, organization_id__in=org_ids
            ).values("pk", "organization_id", "month", "metric_name", "project", "tag")
            if (
                row["organization_id"],
                row["month"],
                row["metric_name"],
                row["project"],
                row["tag"],
            )
            not in fresh_keys
        ]
        if not stale_pks:
            continue
        removed, _ = EventMetricsMonthly._base_manager.filter(pk__in=stale_pks).delete()
        deleted += removed

    return deleted


def _rollup_monthly_from_daily(month_start: date) -> tuple[int, int]:
    """Sum the daily tier from month_start into monthly, for all orgs at once.

    metric_type is aggregated rather than grouped: it is not part of
    unique_monthly_metric, so grouping on it could yield two rows for one
    conflict target.

    Returns:
        (rows upserted, rows deleted as orphans)
    """
    rows = (
        EventMetricsDaily._base_manager.filter(date__gte=month_start)
        .annotate(month=TruncMonth("date"))
        .values("organization_id", "month", "metric_name", "project", "tag")
        .annotate(
            value=Sum("metric_value"),
            count=Sum("metric_count"),
            mtype=Min("metric_type"),
        )
    )

    objects = [
        EventMetricsMonthly(
            organization_id=row["organization_id"],
            month=row["month"],
            metric_name=row["metric_name"],
            project=row["project"],
            tag=row["tag"],
            metric_type=row["mtype"],
            metric_value=row["value"],
            metric_count=row["count"],
        )
        for row in rows
    ]

    # Nothing to write and nothing covered, so nothing to sweep. The scoping in
    # _delete_orphan_monthly already makes this safe; returning early just skips a
    # pointless transaction.
    if not objects:
        return 0, 0

    with transaction.atomic():
        EventMetricsMonthly._base_manager.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["organization", "month", "metric_name", "project", "tag"],
            update_fields=["metric_type", "metric_value", "metric_count"],
            batch_size=MONTHLY_ROLLUP_BATCH_SIZE,
        )
        deleted = _delete_orphan_monthly(objects)

    return len(objects), deleted


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
        # Expired between our check and get — lock is now free, try to acquire it
        return cache.add(AGGREGATION_LOCK_KEY, str(now), AGGREGATION_LOCK_TIMEOUT)

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
def aggregate_metrics_from_sources(
    source_window_days: int = DASHBOARD_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Aggregate source tables into the hourly, daily and monthly tiers.

    Runs every 15 minutes under a self-healing Redis lock. Hourly covers the
    last 24h, daily the source window, monthly is rolled up from daily.

    Args:
        source_window_days: Daily-tier source lookback. The once-daily
            reconciliation pass reruns this task at
            DASHBOARD_RECONCILE_WINDOW_DAYS to repair gaps after downtime.

    Returns:
        Dict with aggregation summary for all three tiers
    """
    if not _acquire_aggregation_lock():
        logger.info("Skipping aggregation — another run is in progress")
        return {"success": True, "skipped": True, "reason": "lock_held"}

    try:
        return _run_aggregation(source_window_days)
    finally:
        cache.delete(AGGREGATION_LOCK_KEY)


def _aggregate_single_metric(
    query_method,
    metric_name: str,
    metric_type: str,
    org_id: str,
    hourly_start: datetime,
    daily_start: datetime,
    end_date: datetime,
    hourly_agg: dict,
    daily_agg: dict,
    extra_kwargs: dict | None = None,
) -> None:
    """Run a single metric query at hourly and daily granularity."""
    extra_kwargs = extra_kwargs or {}

    # === HOURLY (last 24h) ===
    for row in query_method(
        org_id,
        hourly_start,
        end_date,
        granularity=Granularity.HOUR,
        **extra_kwargs,
    ):
        hour_ts = _truncate_to_hour(row["period"])
        key = (org_id, hour_ts.isoformat(), metric_name, "default", "")
        _upsert_agg(hourly_agg, key, metric_type, row["value"] or 0)

    # === DAILY ===
    for row in query_method(
        org_id,
        daily_start,
        end_date,
        granularity=Granularity.DAY,
        **extra_kwargs,
    ):
        day_ts = _truncate_to_day(row["period"])
        key = (org_id, day_ts.date().isoformat(), metric_name, "default", "")
        _upsert_agg(daily_agg, key, metric_type, row["value"] or 0)


def _aggregate_llm_combined(
    org_id: str,
    hourly_start: datetime,
    daily_start: datetime,
    end_date: datetime,
    hourly_agg: dict,
    daily_agg: dict,
    llm_combined_fields: dict,
) -> None:
    """Run the combined LLM metrics query at hourly and daily granularity.

    Two queries covering four metrics.
    """
    # === HOURLY (last 24h) ===
    for row in MetricsQueryService.get_llm_metrics_combined(
        org_id,
        hourly_start,
        end_date,
        granularity=Granularity.HOUR,
    ):
        ts_str = _truncate_to_hour(row["period"]).isoformat()
        for field, (metric_name, metric_type) in llm_combined_fields.items():
            key = (org_id, ts_str, metric_name, "default", "")
            _upsert_agg(hourly_agg, key, metric_type, row[field] or 0)

    # === DAILY ===
    for row in MetricsQueryService.get_llm_metrics_combined(
        org_id,
        daily_start,
        end_date,
        granularity=Granularity.DAY,
    ):
        day_str = _truncate_to_day(row["period"]).date().isoformat()
        for field, (metric_name, metric_type) in llm_combined_fields.items():
            key = (org_id, day_str, metric_name, "default", "")
            _upsert_agg(daily_agg, key, metric_type, row[field] or 0)


# Metric definitions: (name, query_method, is_histogram)
# Note: llm_calls, challenges, summarization_calls, and llm_usage are
# handled separately via get_llm_metrics_combined (1 query instead of 4).
METRIC_CONFIGS = [
    ("documents_processed", MetricsQueryService.get_documents_processed, False),
    ("pages_processed", MetricsQueryService.get_pages_processed, True),
    ("deployed_api_requests", MetricsQueryService.get_deployed_api_requests, False),
    ("etl_pipeline_executions", MetricsQueryService.get_etl_pipeline_executions, False),
    ("prompt_executions", MetricsQueryService.get_prompt_executions, False),
    ("failed_pages", MetricsQueryService.get_failed_pages, True),
    ("hitl_reviews", MetricsQueryService.get_hitl_reviews, False),
    ("hitl_completions", MetricsQueryService.get_hitl_completions, False),
]

# LLM metrics combined via conditional aggregation (4 metrics in 1 query).
# Maps combined query field -> (metric_name, metric_type)
LLM_COMBINED_FIELDS = {
    "llm_calls": ("llm_calls", MetricType.COUNTER),
    "challenges": ("challenges", MetricType.COUNTER),
    "summarization_calls": ("summarization_calls", MetricType.COUNTER),
    "llm_usage": ("llm_usage", MetricType.HISTOGRAM),
}


def _collect_org_metrics(
    org: Organization,
    hourly_start: datetime,
    daily_start: datetime,
    end_date: datetime,
) -> tuple[dict, dict, int]:
    """Query every metric for one org into hourly/daily aggregates.

    A failing metric is logged and counted, leaving the rest to proceed.

    Returns:
        Tuple of (hourly aggregations, daily aggregations, error count)
    """
    org_id = str(org.id)
    hourly_agg: dict[tuple, dict] = {}
    daily_agg: dict[tuple, dict] = {}
    errors = 0

    for metric_name, query_method, is_histogram in METRIC_CONFIGS:
        metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER
        # Pre-resolved identifier spares PageUsage a lookup per call.
        extra_kwargs = (
            {"org_identifier": org.organization_id}
            if metric_name == "pages_processed"
            else {}
        )
        try:
            _aggregate_single_metric(
                query_method,
                metric_name,
                metric_type,
                org_id,
                hourly_start,
                daily_start,
                end_date,
                hourly_agg,
                daily_agg,
                extra_kwargs,
            )
        except Exception:
            logger.exception("Error querying %s for org %s", metric_name, org_id)
            errors += 1

    try:
        _aggregate_llm_combined(
            org_id,
            hourly_start,
            daily_start,
            end_date,
            hourly_agg,
            daily_agg,
            LLM_COMBINED_FIELDS,
        )
    except Exception:
        logger.exception("Error querying combined LLM metrics for org %s", org_id)
        errors += 1

    return hourly_agg, daily_agg, errors


def _aggregate_org(
    org: Organization,
    hourly_start: datetime,
    daily_start: datetime,
    end_date: datetime,
    stats: dict[str, Any],
) -> None:
    """Aggregate one organization and upsert its hourly and daily tiers."""
    hourly_agg, daily_agg, errors = _collect_org_metrics(
        org, hourly_start, daily_start, end_date
    )
    stats["errors"] += errors

    if hourly_agg:
        stats["hourly"]["upserted"] += _bulk_upsert_hourly(hourly_agg)

    if daily_agg:
        stats["daily"]["upserted"] += _bulk_upsert_daily(daily_agg)

    stats["orgs_processed"] += 1


def _active_org_ids(end_date: datetime, window_start: datetime) -> set:
    """Organizations with execution activity in the prefilter lookback.

    Never narrower than the caller's own query window: a widened
    source_window_days must not be prefiltered back down to the default
    lookback, or the reconciliation pass skips the orgs it exists to repair.
    """
    cutoff = min(
        window_start,
        end_date - timedelta(days=DASHBOARD_ACTIVE_ORG_LOOKBACK_DAYS),
    )
    return set(
        WorkflowExecution.objects.filter(created_at__gte=cutoff)
        .values_list("workflow__organization_id", flat=True)
        .distinct()
    )


def _build_result(
    stats: dict[str, Any],
    hourly_start: datetime,
    daily_start: datetime,
    monthly_start: date,
    end_date: datetime,
    skipped_reason: str | None = None,
) -> dict[str, Any]:
    """Shape the task's return value from the accumulated stats."""
    result = {
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
    if skipped_reason:
        result["skipped_reason"] = skipped_reason
    return result


def _run_aggregation(
    source_window_days: int = DASHBOARD_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Execute the aggregation, separately from the task's lock handling."""
    end_date = timezone.now()

    # Monthly spans the current and previous month.
    hourly_start = end_date - timedelta(hours=24)
    daily_start = _truncate_to_day(end_date - timedelta(days=source_window_days))
    monthly_start = _truncate_to_month(
        _truncate_to_month(end_date) - timedelta(days=1)
    ).date()

    stats = {
        "hourly": {"upserted": 0},
        "daily": {"upserted": 0},
        "monthly": {"upserted": 0, "deleted": 0},
        "errors": 0,
        "orgs_processed": 0,
    }

    # Pre-filter to orgs with recent activity to reduce DB load.
    active_org_ids = _active_org_ids(end_date, daily_start)
    logger.info(
        "Aggregation: %d active orgs out of %d total",
        len(active_org_ids),
        Organization.objects.count(),
    )

    if not active_org_ids:
        return _build_result(
            stats,
            hourly_start,
            daily_start,
            monthly_start,
            end_date,
            skipped_reason="no_active_orgs",
        )

    organizations = Organization.objects.filter(id__in=active_org_ids).only(
        "id", "organization_id"
    )

    for org in organizations:
        try:
            _aggregate_org(org, hourly_start, daily_start, end_date, stats)
        except Exception:
            logger.exception("Error processing org %s", org.id)
            stats["errors"] += 1

    try:
        upserted, deleted = _rollup_monthly_from_daily(monthly_start)
        stats["monthly"]["upserted"] = upserted
        stats["monthly"]["deleted"] = deleted
        if deleted:
            logger.warning(
                "Monthly rollup deleted %d orphan row(s) from %s", deleted, monthly_start
            )
    except (DatabaseError, OperationalError):
        # Configured on the task for autoretry — swallowing them here would
        # leave monthly permanently stale behind successful-looking runs.
        raise
    except Exception:
        logger.exception("Error rolling up monthly metrics from %s", monthly_start)
        stats["errors"] += 1

    logger.info(
        f"Aggregation completed: {stats['orgs_processed']} orgs, "
        f"hourly={stats['hourly']['upserted']}, "
        f"daily={stats['daily']['upserted']}, "
        f"monthly={stats['monthly']['upserted']}, "
        f"monthly_deleted={stats['monthly']['deleted']}, "
        f"errors={stats['errors']}"
    )

    return _build_result(stats, hourly_start, daily_start, monthly_start, end_date)


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
