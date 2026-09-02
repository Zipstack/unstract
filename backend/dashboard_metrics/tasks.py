"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import logging
import time
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from account_v2.models import Organization
from celery import shared_task
from django.core.cache import cache
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

# Floor on the prefilter lookback: metrics keyed on another column (e.g.
# approved_at) can land for an org whose executions are older. _active_org_ids
# takes the wider of this and the run's own window, so the prefilter is never
# narrower than what is being queried — at the 7-day reconciliation window the
# two are equal rather than this one being wider.
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


def _rollup_monthly_from_daily(month_start: date) -> int:
    """Sum the daily tier from month_start into monthly, for all orgs at once.

    Upsert-only, per the design agreed on UN-3973: a monthly row the daily tier
    no longer produces is left in place rather than deleted. A stale total is
    recoverable with backfill_metrics; a deleted one is not, because the daily
    rows that would rebuild it are exactly what is missing.

    metric_type is aggregated rather than grouped: it is not part of
    unique_monthly_metric, so grouping on it could yield two rows for one
    conflict target.
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

    if not objects:
        return 0

    EventMetricsMonthly._base_manager.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["organization", "month", "metric_name", "project", "tag"],
        update_fields=["metric_type", "metric_value", "metric_count"],
        batch_size=MONTHLY_ROLLUP_BATCH_SIZE,
    )
    return len(objects)


class AggregationTier(StrEnum):
    """Which metric tiers one aggregation run writes.

    Daily and monthly stay together because monthly is rolled up from the daily tier.
    """

    HOURLY = "hourly"
    DAILY_MONTHLY = "daily_monthly"
    ALL = "all"


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


AGGREGATION_LOCK_KEY_PREFIX = "dashboard_metrics:aggregation_lock"
AGGREGATION_LOCK_TIMEOUT = 900  # 15 minutes (matches task schedule)


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
        logger.warning("Reclaiming aggregation lock with invalid value: %s", lock_value)
        cache.delete(lock_key)
        return cache.add(lock_key, str(now), AGGREGATION_LOCK_TIMEOUT)

    age = now - lock_time
    if age > AGGREGATION_LOCK_TIMEOUT:
        logger.warning(
            "Reclaiming stale aggregation lock (age=%.0fs, timeout=%ds)",
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
    """Aggregate source tables into the hourly, daily and monthly tiers.

    Three schedules call this: the hourly tier every 15 minutes, the daily and
    monthly tiers hourly at :20, and a once-daily reconciliation pass over every
    tier at a wider window. Hourly covers the last 24h, daily the source window,
    monthly is rolled up from daily.

    Args:
        tier: An AggregationTier value. Defaults to all, so a caller that omits it
            — a schedule row written before 0006 — writes every tier rather than
            none.
        source_window_days: Daily-tier source lookback. The reconciliation pass
            reruns this task at DASHBOARD_RECONCILE_WINDOW_DAYS to repair gaps
            after downtime.

    Returns:
        Dict with aggregation summary for the tiers that ran

    Raises:
        ValueError: tier is not a recognised AggregationTier, or the window is not
            an integer between 1 and MAX_SOURCE_WINDOW_DAYS
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
    end_date: datetime,
    hourly_agg: dict,
    daily_agg: dict,
    tier: AggregationTier,
    extra_kwargs: dict | None = None,
) -> None:
    """Run a single metric query at the granularities this run writes."""
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

    # === DAILY (monthly is rolled up from it, so one query feeds both) ===
    if not _writes_daily_monthly(tier):
        return

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
    tier: AggregationTier,
) -> None:
    """Run the combined LLM metrics query at the granularities this run writes.

    Two queries covering four metrics.
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

    # === DAILY ===
    if not _writes_daily_monthly(tier):
        return

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
    tier: AggregationTier,
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
                tier,
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
            tier,
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
    tier: AggregationTier,
    stats: dict[str, Any],
) -> None:
    """Aggregate one organization and upsert the tiers this run writes."""
    hourly_agg, daily_agg, errors = _collect_org_metrics(
        org, hourly_start, daily_start, end_date, tier
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
    tier: AggregationTier,
    skipped_reason: str | None = None,
) -> dict[str, Any]:
    """Shape the task's return value from the accumulated stats."""
    result = {
        "tier": tier.value,
        # Not a literal: every metric for every org can fail while each exception is
        # caught per-metric, and the run would otherwise report 200 / success with
        # zero rows written and the dashboard frozen.
        "success": stats["errors"] == 0,
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


# A negative window puts daily_start in the future so nothing matches; 0 never
# refreshes yesterday; an unbounded one restores the multi-month per-org scan this
# change exists to remove, past soft_time_limit.
MAX_SOURCE_WINDOW_DAYS = 90


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


def _roll_up_monthly(monthly_start: date, stats: dict[str, Any]) -> None:
    """Derive the monthly tier from daily, recording a failure distinctly."""
    try:
        stats["monthly"]["upserted"] = _rollup_monthly_from_daily(monthly_start)
    except (DatabaseError, OperationalError):
        # Configured on the task for autoretry — swallowing them here would
        # leave monthly permanently stale behind successful-looking runs.
        raise
    except Exception:
        # upserted stays 0, which is also the legitimate empty-rollup value, so
        # mark the failure explicitly rather than letting the two collapse.
        logger.exception("Error rolling up monthly metrics from %s", monthly_start)
        stats["monthly"]["failed"] = True
        stats["errors"] += 1


def _run_aggregation(
    tier: AggregationTier = AggregationTier.ALL,
    source_window_days: int = DASHBOARD_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Execute the aggregation, separately from the task's lock handling."""
    tier = AggregationTier(tier)
    source_window_days = _validate_source_window(source_window_days)
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
        "monthly": {"upserted": 0, "failed": False},
        "errors": 0,
        "orgs_processed": 0,
    }

    # Pre-filter to orgs with recent activity to reduce DB load.
    active_org_ids = _active_org_ids(end_date, daily_start)
    # No total_orgs here: a full count of the organization table, on every run of
    # every tier, whose only consumer was this log line.
    logger.info("Aggregation (%s): %d active orgs", tier.value, len(active_org_ids))

    if not active_org_ids:
        return _build_result(
            stats,
            hourly_start,
            daily_start,
            monthly_start,
            end_date,
            tier,
            skipped_reason="no_active_orgs",
        )

    organizations = Organization.objects.filter(id__in=active_org_ids).only(
        "id", "organization_id"
    )

    for org in organizations:
        try:
            _aggregate_org(org, hourly_start, daily_start, end_date, tier, stats)
        except Exception:
            logger.exception("Error processing org %s", org.id)
            stats["errors"] += 1

    if _writes_daily_monthly(tier):
        _roll_up_monthly(monthly_start, stats)

    log = logger.warning if stats["errors"] else logger.info
    log(
        f"Aggregation completed: {stats['orgs_processed']} orgs, "
        f"hourly={stats['hourly']['upserted']}, "
        f"daily={stats['daily']['upserted']}, "
        f"monthly={stats['monthly']['upserted']}, "
        f"errors={stats['errors']}"
    )

    return _build_result(stats, hourly_start, daily_start, monthly_start, end_date, tier)


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
