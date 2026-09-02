"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import logging
import time
from datetime import datetime, timedelta
from enum import StrEnum
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
        update_fields=["metric_type", "metric_value", "metric_count"],
    )
    return len(objects)


class AggregationTier(StrEnum):
    """Which metric tiers one aggregation run writes.

    Daily and monthly stay together because one DAY-granularity query feeds both.
    """

    HOURLY = "hourly"
    DAILY_MONTHLY = "daily_monthly"
    ALL = "all"


# Keyed per tier: the two schedules collide hourly and must not block each other.
# Daily-tier source lookback. The reconciliation schedule 0005 declares dispatches a
# wider one, so this signature has to accept it — see workers/scheduler and
# internal_views for the other two legs of the same path.
DASHBOARD_SOURCE_WINDOW_DAYS = 7
MAX_SOURCE_WINDOW_DAYS = 90

AGGREGATION_LOCK_KEY_PREFIX = "dashboard_metrics:aggregation_lock"
AGGREGATION_LOCK_TIMEOUT = 900  # 15 minutes (matches the fastest task schedule)


# Which granularities each tier writes. One table rather than a predicate per
# granularity: add a member without an entry here and _tiers_written raises on the
# first run, instead of the run acquiring its lock, iterating every org, writing
# nothing and returning success.
_TIER_WRITES: dict[AggregationTier, frozenset[str]] = {
    AggregationTier.HOURLY: frozenset({AggregationTier.HOURLY.value}),
    AggregationTier.DAILY_MONTHLY: frozenset({AggregationTier.DAILY_MONTHLY.value}),
    AggregationTier.ALL: frozenset(
        {AggregationTier.HOURLY.value, AggregationTier.DAILY_MONTHLY.value}
    ),
}


def _tiers_written(tier: AggregationTier) -> frozenset[str]:
    """The granularities one tier writes. Unhandled members raise rather than no-op."""
    try:
        return _TIER_WRITES[tier]
    except KeyError:
        raise AssertionError(f"Unhandled AggregationTier: {tier!r}") from None


def _writes_hourly(tier: AggregationTier) -> bool:
    return AggregationTier.HOURLY.value in _tiers_written(tier)


def _writes_daily_monthly(tier: AggregationTier) -> bool:
    return AggregationTier.DAILY_MONTHLY.value in _tiers_written(tier)


def _aggregation_lock_keys(tier: AggregationTier, source_window_days: int) -> list[str]:
    """One key per granularity written, namespaced by source window.

    Per granularity, not per enum member: keying on the label alone gives ALL a third
    key that excludes nothing, so an ALL run and the scheduled hourly run would write
    EventMetricsHourly concurrently. Taking one key per granularity restores exclusion
    exactly where writes collide, and the two scheduled tiers still never block.

    Per window because a wider window is a different job. The reconciliation pass runs
    once a day on a fixed crontab against a drifting 15-minute interval; on a shared
    key it would lose the race, return skipped=True and never be retried — and it is
    the only thing that repairs the narrowed window. Both are idempotent upserts, so
    that once-a-day overlap costs duplicated work at worst.
    """
    return [
        f"{AGGREGATION_LOCK_KEY_PREFIX}:{source_window_days}d:{granularity}"
        for granularity in sorted(_tiers_written(tier))
    ]


def _acquire_aggregation_locks(lock_keys: list[str]) -> list[str]:
    """Take every key or none; returns the keys taken, empty if the run must skip."""
    taken: list[str] = []
    for key in lock_keys:
        if not _acquire_aggregation_lock(key):
            for held in taken:
                cache.delete(held)
            return []
        taken.append(key)
    return taken


def _acquire_aggregation_lock(lock_key: str) -> bool:
    """Acquire the distributed aggregation lock with self-healing.

    Stores a Unix timestamp as the lock value. If a previous run crashed
    (OOM kill, SIGKILL) without releasing the lock, the next run detects
    that the lock is older than AGGREGATION_LOCK_TIMEOUT and reclaims it.

    Args:
        lock_key: Cache key to lock on, one per tier

    Returns:
        True if lock was acquired, False if another run is legitimately active.
    """
    now = time.time()

    # Fast path: lock is free
    if cache.add(lock_key, str(now), AGGREGATION_LOCK_TIMEOUT):
        return True

    # Lock exists — check if it's stale (previous run died without releasing)
    lock_value = cache.get(lock_key)
    if lock_value is None:
        # Expired between our check and get — lock is now free, try to acquire it
        return cache.add(lock_key, str(now), AGGREGATION_LOCK_TIMEOUT)

    try:
        lock_time = float(lock_value)
    except (TypeError, ValueError):
        # Corrupted value (e.g. old "running" string) — reclaim it
        logger.warning(
            "Reclaiming aggregation lock %s with invalid value: %s", lock_key, lock_value
        )
        cache.delete(lock_key)
        return cache.add(lock_key, str(now), AGGREGATION_LOCK_TIMEOUT)

    age = now - lock_time
    if age > AGGREGATION_LOCK_TIMEOUT:
        logger.warning(
            "Reclaiming stale aggregation lock %s (age=%.0fs, timeout=%ds)",
            lock_key,
            age,
            AGGREGATION_LOCK_TIMEOUT,
        )
        cache.delete(lock_key)
        return cache.add(lock_key, str(now), AGGREGATION_LOCK_TIMEOUT)

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
    tier: str = AggregationTier.ALL,
    source_window_days: int = DASHBOARD_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Aggregate metrics from source tables into the hourly/daily/monthly tables.

    Two schedules call this with different tiers: hourly every 15 minutes, daily
    and monthly hourly. Each tier locks separately.

    Uses a Redis distributed lock with self-healing to prevent overlapping
    runs. If a previous run was killed without releasing the lock, the next
    run detects the stale lock and reclaims it automatically.

    Aggregation windows:
    - Hourly: Last 24 hours (rolling window)
    - Daily: Last 7 days (ensures we capture late-arriving data)
    - Monthly: Last 2 months (current + previous month)

    Args:
        tier: An AggregationTier value. Defaults to all, so a caller that omits
            it writes every tier rather than none.
        source_window_days: Daily-tier source lookback. The once-daily
            reconciliation schedule declared by 0005 dispatches a wider one.

    Returns:
        Dict with aggregation summary for the tiers that ran

    Raises:
        ValueError: tier is not a recognised AggregationTier, or the window is
            not an integer between 1 and MAX_SOURCE_WINDOW_DAYS
    """
    tier = AggregationTier(tier)
    source_window_days = _validate_source_window(source_window_days)
    lock_keys = _aggregation_lock_keys(tier, source_window_days)

    held = _acquire_aggregation_locks(lock_keys)
    if not held:
        logger.warning(
            "Skipping the %s aggregation over %d day(s) — another run writing the "
            "same tier is in progress",
            tier.value,
            source_window_days,
        )
        return {
            "success": True,
            "skipped": True,
            "reason": "lock_held",
            "tier": tier.value,
            "source_window_days": source_window_days,
        }

    try:
        return _run_aggregation(tier, source_window_days)
    finally:
        for key in held:
            cache.delete(key)


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
    tier: AggregationTier,
    extra_kwargs: dict | None = None,
) -> None:
    """Run a single metric query at the requested granularities and populate agg dicts.

    Uses 2 queries instead of 3: the daily query is widened to monthly_start
    and its results are split into both daily_agg and monthly_agg in Python.
    This is the same pattern proven in the backfill management command.

    Each query is skipped when its tier is not in scope for this run.
    """
    extra_kwargs = extra_kwargs or {}

    # === HOURLY (last 24h) ===
    if _writes_hourly(tier):
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

    # === DAILY + MONTHLY (single query from monthly_start) ===
    if not _writes_daily_monthly(tier):
        return

    for row in query_method(
        org_id,
        monthly_start,
        end_date,
        granularity=Granularity.DAY,
        **extra_kwargs,
    ):
        value = row["value"] or 0
        day_ts = _truncate_to_day(row["period"])

        if day_ts >= daily_start:
            key = (org_id, day_ts.date().isoformat(), metric_name, "default", "")
            _upsert_agg(daily_agg, key, metric_type, value)

        month_key = _truncate_to_month(row["period"]).date().isoformat()
        key = (org_id, month_key, metric_name, "default", "")
        _upsert_agg(monthly_agg, key, metric_type, value)


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
    tier: AggregationTier,
) -> None:
    """Run the combined LLM metrics query at the requested granularities.

    Issues 2 queries total (hourly + daily/monthly) instead of 3.
    The DAY-granularity query is widened to monthly_start and results are
    split into daily_agg (recent rows) and monthly_agg (all rows bucketed
    by month) in Python. Same pattern as _aggregate_single_metric.
    """
    # === HOURLY (last 24h) ===
    if _writes_hourly(tier):
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

    # === DAILY + MONTHLY (single query from monthly_start) ===
    if not _writes_daily_monthly(tier):
        return

    for row in MetricsQueryService.get_llm_metrics_combined(
        org_id,
        monthly_start,
        end_date,
        granularity=Granularity.DAY,
    ):
        day_ts = _truncate_to_day(row["period"])
        month_key = _truncate_to_month(row["period"]).date().isoformat()

        for field, (metric_name, metric_type) in llm_combined_fields.items():
            value = row[field] or 0

            if day_ts >= daily_start:
                key = (org_id, day_ts.date().isoformat(), metric_name, "default", "")
                _upsert_agg(daily_agg, key, metric_type, value)

            key = (org_id, month_key, metric_name, "default", "")
            _upsert_agg(monthly_agg, key, metric_type, value)


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
    monthly_start: datetime,
    end_date: datetime,
    tier: AggregationTier,
) -> tuple[dict, dict, dict, int]:
    """Query every metric for one org into per-tier aggregate dicts.

    A failing metric is counted, not raised, so it does not cost the org the rest.

    Returns:
        (hourly_agg, daily_agg, monthly_agg, error_count)
    """
    org_id = str(org.id)
    hourly_agg: dict[tuple, dict] = {}
    daily_agg: dict[tuple, dict] = {}
    monthly_agg: dict[tuple, dict] = {}
    errors = 0

    for metric_name, query_method, is_histogram in METRIC_CONFIGS:
        metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

        # Pass org_identifier to PageUsage-based metrics to
        # avoid redundant Organization lookups per call.
        extra_kwargs = {}
        if metric_name == "pages_processed":
            extra_kwargs["org_identifier"] = org.organization_id

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
                tier,
                extra_kwargs,
            )
        except Exception:
            logger.exception("Error querying %s for org %s", metric_name, org_id)
            errors += 1

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
            LLM_COMBINED_FIELDS,
            tier,
        )
    except Exception:
        logger.exception("Error querying combined LLM metrics for org %s", org_id)
        errors += 1

    return hourly_agg, daily_agg, monthly_agg, errors


def _aggregate_org(
    org: Organization,
    hourly_start: datetime,
    daily_start: datetime,
    monthly_start: datetime,
    end_date: datetime,
    tier: AggregationTier,
    stats: dict[str, Any],
) -> None:
    """Aggregate one organization and upsert the tiers this run writes."""
    try:
        hourly_agg, daily_agg, monthly_agg, errors = _collect_org_metrics(
            org, hourly_start, daily_start, monthly_start, end_date, tier
        )
        stats["errors"] += errors

        # Bulk upsert each populated tier (single INSERT...ON CONFLICT each)
        if hourly_agg:
            stats["hourly"]["upserted"] += _bulk_upsert_hourly(hourly_agg)
        if daily_agg:
            stats["daily"]["upserted"] += _bulk_upsert_daily(daily_agg)
        if monthly_agg:
            stats["monthly"]["upserted"] += _bulk_upsert_monthly(monthly_agg)

        stats["orgs_processed"] += 1
    except Exception:
        logger.exception("Error processing org %s", org.id)
        stats["errors"] += 1


def _validate_source_window(source_window_days: int) -> int:
    """Coerce and bound the window. It arrives as JSON from an editable Beat row."""
    try:
        days = int(source_window_days)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"source_window_days must be an integer, got {source_window_days!r}"
        ) from exc
    if not 1 <= days <= MAX_SOURCE_WINDOW_DAYS:
        raise ValueError(
            f"source_window_days must be between 1 and {MAX_SOURCE_WINDOW_DAYS}, "
            f"got {days}"
        )
    return days


def _run_aggregation(
    tier: AggregationTier = AggregationTier.ALL,
    source_window_days: int = DASHBOARD_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Execute the actual aggregation logic.

    Separated from the task function to keep the lock management clean.
    """
    source_window_days = _validate_source_window(source_window_days)
    end_date = timezone.now()

    # Query windows for each granularity
    # - Hourly: Last 24 hours (rolling window, matches retention of 30 days)
    # - Daily: Last 7 days (ensures we capture late-arriving data)
    # - Monthly: Last 2 months (current + previous, ensures month transitions are captured)
    hourly_start = end_date - timedelta(hours=24)
    daily_start = _truncate_to_day(end_date - timedelta(days=source_window_days))
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
    # No total_orgs here: a full count of the organization table, on every run of
    # every tier, whose only consumer was this log line.
    logger.info("Aggregation (%s): %d active orgs", tier.value, len(active_org_ids))

    if not active_org_ids:
        return {
            "success": True,
            "tier": tier.value,
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
        _aggregate_org(
            org, hourly_start, daily_start, monthly_start, end_date, tier, stats
        )

    logger.info(
        f"Aggregation completed ({tier.value}): {stats['orgs_processed']} orgs, "
        f"hourly={stats['hourly']['upserted']}, "
        f"daily={stats['daily']['upserted']}, "
        f"monthly={stats['monthly']['upserted']}, "
        f"errors={stats['errors']}"
    )

    # Only the windows this run queried; a skipped tier reports no period.
    period = {}
    if _writes_hourly(tier):
        period["hourly"] = {
            "start": hourly_start.isoformat(),
            "end": end_date.isoformat(),
        }
    if _writes_daily_monthly(tier):
        period["daily"] = {"start": daily_start.isoformat(), "end": end_date.isoformat()}
        period["monthly"] = {
            "start": monthly_start.isoformat(),
            "end": end_date.isoformat(),
        }

    return {
        "success": True,
        "tier": tier.value,
        "organizations_processed": stats["orgs_processed"],
        "hourly": stats["hourly"],
        "daily": stats["daily"],
        "monthly": stats["monthly"],
        "errors": stats["errors"],
        "period": period,
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
