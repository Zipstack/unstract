"""Celery tasks for Dashboard Metrics processing with batching.

Tasks:
- process_dashboard_metric_events: Batched processing of metric events
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period

This implementation uses celery-batches to efficiently process metric events
in batches, reducing database contention and improving throughput.
"""
import logging
from datetime import datetime, timedelta
from typing import Any

from celery import shared_task
from celery_batches import Batches
from django.db import transaction
from django.db.models import F
from django.db.utils import DatabaseError, OperationalError
from django.utils import timezone

from .models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    MetricType,
)

logger = logging.getLogger(__name__)

# Default retention periods
DEFAULT_RETENTION_DAYS_HOURLY = 30
DEFAULT_RETENTION_DAYS_DAILY = 365


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


@shared_task(
    base=Batches,
    name="dashboard_metrics.process_events",
    flush_every=100,
    flush_interval=60,
    acks_late=True,
    max_retries=5,
    autoretry_for=(DatabaseError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_dashboard_metric_events(requests) -> dict[str, Any]:
    """Process batched metric events into hourly, daily, and monthly aggregations.

    This task uses celery-batches to accumulate events and flush them either:
    - After 100 events (flush_every=100)
    - After 60 seconds (flush_interval=60)

    Each batch is aggregated into hourly, daily, and monthly tables simultaneously.

    Args:
        requests: List of celery-batches Request objects containing metric events

    Returns:
        Dict with processing summary including counts for each tier
    """
    if not requests:
        return {"processed": 0, "errors": 0}

    # Aggregation buckets
    hourly_agg: dict[tuple, dict] = {}
    daily_agg: dict[tuple, dict] = {}
    monthly_agg: dict[tuple, dict] = {}

    errors = 0

    for request in requests:
        try:
            # Extract event from request (celery-batches wraps args)
            event = request.args[0] if request.args else request.kwargs.get("event", {})

            timestamp = event.get("timestamp", timezone.now().timestamp())
            org_id = event["org_id"]
            metric_name = event["metric_name"]
            metric_value = event.get("metric_value", 1)
            metric_type = event.get("metric_type", MetricType.COUNTER)
            labels = event.get("labels", {})
            project = event.get("project", "default")
            tag = event.get("tag")

            # Calculate time buckets
            hour_ts = _truncate_to_hour(timestamp)
            day_ts = _truncate_to_day(hour_ts)
            month_ts = _truncate_to_month(hour_ts)

            # Aggregate into hourly bucket
            hourly_key = (org_id, hour_ts.isoformat(), metric_name, project, tag)
            if hourly_key not in hourly_agg:
                hourly_agg[hourly_key] = {
                    "metric_type": metric_type,
                    "value": 0,
                    "count": 0,
                    "labels": {},
                }
            hourly_agg[hourly_key]["value"] += metric_value
            hourly_agg[hourly_key]["count"] += 1
            if labels:
                hourly_agg[hourly_key]["labels"].update(labels)

            # Aggregate into daily bucket
            daily_key = (org_id, day_ts.date().isoformat(), metric_name, project, tag)
            if daily_key not in daily_agg:
                daily_agg[daily_key] = {
                    "metric_type": metric_type,
                    "value": 0,
                    "count": 0,
                    "labels": {},
                }
            daily_agg[daily_key]["value"] += metric_value
            daily_agg[daily_key]["count"] += 1
            if labels:
                daily_agg[daily_key]["labels"].update(labels)

            # Aggregate into monthly bucket
            monthly_key = (
                org_id,
                month_ts.date().isoformat(),
                metric_name,
                project,
                tag,
            )
            if monthly_key not in monthly_agg:
                monthly_agg[monthly_key] = {
                    "metric_type": metric_type,
                    "value": 0,
                    "count": 0,
                    "labels": {},
                }
            monthly_agg[monthly_key]["value"] += metric_value
            monthly_agg[monthly_key]["count"] += 1
            if labels:
                monthly_agg[monthly_key]["labels"].update(labels)

        except KeyError as e:
            logger.warning(f"Skipping event with missing required field: {e}")
            errors += 1
        except Exception as e:
            logger.warning(f"Error processing event: {e}")
            errors += 1

    # Bulk upsert to all three tables
    hourly_created, hourly_updated = _bulk_upsert_hourly(hourly_agg)
    daily_created, daily_updated = _bulk_upsert_daily(daily_agg)
    monthly_created, monthly_updated = _bulk_upsert_monthly(monthly_agg)

    logger.info(
        f"Batch processed: hourly({hourly_created}+{hourly_updated}), "
        f"daily({daily_created}+{daily_updated}), "
        f"monthly({monthly_created}+{monthly_updated}), "
        f"errors={errors}"
    )

    return {
        "processed": len(requests) - errors,
        "errors": errors,
        "hourly": {"created": hourly_created, "updated": hourly_updated},
        "daily": {"created": daily_created, "updated": daily_updated},
        "monthly": {"created": monthly_created, "updated": monthly_updated},
    }


def _bulk_upsert_hourly(aggregations: dict) -> tuple[int, int]:
    """Bulk upsert hourly aggregations.

    Args:
        aggregations: Dict of aggregated metric data keyed by
            (org_id, hour_ts_str, metric_name, project, tag)

    Returns:
        Tuple of (created_count, updated_count)
    """
    created, updated = 0, 0
    with transaction.atomic():
        for key, agg in aggregations.items():
            org_id, hour_ts_str, metric_name, project, tag = key
            hour_ts = datetime.fromisoformat(hour_ts_str)

            try:
                obj, was_created = (
                    EventMetricsHourly.objects.select_for_update().get_or_create(
                        organization_id=org_id,
                        timestamp=hour_ts,
                        metric_name=metric_name,
                        project=project,
                        tag=tag,
                        defaults={
                            "metric_type": agg["metric_type"],
                            "metric_value": agg["value"],
                            "metric_count": agg["count"],
                            "labels": agg["labels"],
                        },
                    )
                )
                if was_created:
                    created += 1
                else:
                    obj.metric_value = F("metric_value") + agg["value"]
                    obj.metric_count = F("metric_count") + agg["count"]
                    if agg["labels"]:
                        obj.labels = {**obj.labels, **agg["labels"]}
                    obj.save(
                        update_fields=[
                            "metric_value",
                            "metric_count",
                            "labels",
                            "modified_at",
                        ]
                    )
                    updated += 1
            except Exception as e:
                logger.error(f"Error upserting hourly metric {key}: {e}")

    return created, updated


def _bulk_upsert_daily(aggregations: dict) -> tuple[int, int]:
    """Bulk upsert daily aggregations.

    Args:
        aggregations: Dict of aggregated metric data keyed by
            (org_id, date_str, metric_name, project, tag)

    Returns:
        Tuple of (created_count, updated_count)
    """
    created, updated = 0, 0
    with transaction.atomic():
        for key, agg in aggregations.items():
            org_id, date_str, metric_name, project, tag = key
            date_val = datetime.fromisoformat(date_str).date()

            try:
                obj, was_created = (
                    EventMetricsDaily.objects.select_for_update().get_or_create(
                        organization_id=org_id,
                        date=date_val,
                        metric_name=metric_name,
                        project=project,
                        tag=tag,
                        defaults={
                            "metric_type": agg["metric_type"],
                            "metric_value": agg["value"],
                            "metric_count": agg["count"],
                            "labels": agg["labels"],
                        },
                    )
                )
                if was_created:
                    created += 1
                else:
                    obj.metric_value = F("metric_value") + agg["value"]
                    obj.metric_count = F("metric_count") + agg["count"]
                    if agg["labels"]:
                        obj.labels = {**obj.labels, **agg["labels"]}
                    obj.save(
                        update_fields=[
                            "metric_value",
                            "metric_count",
                            "labels",
                            "modified_at",
                        ]
                    )
                    updated += 1
            except Exception as e:
                logger.error(f"Error upserting daily metric {key}: {e}")

    return created, updated


def _bulk_upsert_monthly(aggregations: dict) -> tuple[int, int]:
    """Bulk upsert monthly aggregations.

    Args:
        aggregations: Dict of aggregated metric data keyed by
            (org_id, month_str, metric_name, project, tag)

    Returns:
        Tuple of (created_count, updated_count)
    """
    created, updated = 0, 0
    with transaction.atomic():
        for key, agg in aggregations.items():
            org_id, month_str, metric_name, project, tag = key
            month_val = datetime.fromisoformat(month_str).date()

            try:
                obj, was_created = (
                    EventMetricsMonthly.objects.select_for_update().get_or_create(
                        organization_id=org_id,
                        month=month_val,
                        metric_name=metric_name,
                        project=project,
                        tag=tag,
                        defaults={
                            "metric_type": agg["metric_type"],
                            "metric_value": agg["value"],
                            "metric_count": agg["count"],
                            "labels": agg["labels"],
                        },
                    )
                )
                if was_created:
                    created += 1
                else:
                    obj.metric_value = F("metric_value") + agg["value"]
                    obj.metric_count = F("metric_count") + agg["count"]
                    if agg["labels"]:
                        obj.labels = {**obj.labels, **agg["labels"]}
                    obj.save(
                        update_fields=[
                            "metric_value",
                            "metric_count",
                            "labels",
                            "modified_at",
                        ]
                    )
                    updated += 1
            except Exception as e:
                logger.error(f"Error upserting monthly metric {key}: {e}")

    return created, updated


@shared_task(
    name="dashboard_metrics.cleanup_hourly_data",
    max_retries=3,
    autoretry_for=(DatabaseError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=300,
)
def cleanup_hourly_metrics(
    retention_days: int = DEFAULT_RETENTION_DAYS_HOURLY,
) -> dict[str, Any]:
    """Remove hourly metrics older than retention period.

    Args:
        retention_days: Number of days to retain hourly data (default: 30)

    Returns:
        Dict with deletion summary
    """
    cutoff = timezone.now() - timedelta(days=retention_days)

    try:
        deleted_count, _ = EventMetricsHourly.objects.filter(
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
        logger.error(f"Error during hourly cleanup: {e}", exc_info=True)
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
    retention_days: int = DEFAULT_RETENTION_DAYS_DAILY,
) -> dict[str, Any]:
    """Remove daily metrics older than retention period.

    Args:
        retention_days: Number of days to retain daily data (default: 365)

    Returns:
        Dict with deletion summary
    """
    cutoff = (timezone.now() - timedelta(days=retention_days)).date()

    try:
        deleted_count, _ = EventMetricsDaily.objects.filter(date__lt=cutoff).delete()

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
        logger.error(f"Error during daily cleanup: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "retention_days": retention_days,
        }
