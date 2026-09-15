"""Celery tasks for Dashboard Metrics aggregation and cleanup.

Tasks:
- aggregate_metrics_from_sources: Periodic aggregation from source tables
- cleanup_hourly_metrics: Remove hourly metrics older than retention period
- cleanup_daily_metrics: Remove daily metrics older than retention period
"""

import calendar
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from account_v2.models import Organization
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache
from django.db.models import Count, F, Min, OuterRef, Subquery, Sum
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

# Cap on the under-count report: a fleet-wide daily loss would otherwise name every
# (organization, month) pair in one log line and one JSON body.
LOWERED_MONTHS_REPORT_LIMIT = 20

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

# Floor on the prefilter lookback. _active_org_ids takes the wider of this and the
# run's own window, so a widened source_window_days is never prefiltered back down.
# It does NOT rescue a metric keyed on another column: get_hitl_completions windows
# on approved_at, so an org approving today with no execution inside the floor is
# still absent from the run. Widening a created_at lookback cannot reach it — only
# unioning the shortlist with those orgs would.
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


def truncate_to_day(ts: datetime) -> datetime:
    """Truncate a datetime to midnight (start of day).

    Public because backfill_metrics shares it: the day boundary is a contract
    between the cron and the repair command, not an internal of either. An
    untruncated boundary writes the oldest day as a partial bucket, which the
    monthly rollup then makes permanent.

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


def _upsert_monthly(objects: list[EventMetricsMonthly]) -> int:
    """Upsert one batch of derived monthly rows."""
    EventMetricsMonthly._base_manager.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["organization", "month", "metric_name", "project", "tag"],
        update_fields=["metric_type", "metric_value", "metric_count"],
        batch_size=MONTHLY_ROLLUP_BATCH_SIZE,
    )
    return len(objects)


def _pairs_the_rollup_would_lower(month_start: date) -> list[tuple]:
    """Conflict keys whose monthly total the pending rollup would reduce.

    Run before the upsert, while the stored value is still the old one, and
    evaluated in the database: one statement returning only the offending pairs,
    which in a healthy install is none.

    Materialising the old and new totals in Python would have compared the same
    thing, but it scales with tenant x metric x project x tag — the axis the
    streaming rollup below exists to keep off the heap.

    Compared at the grain the rollup writes at, because that is the grain the damage
    occurs at: one tenant's metric can lose days while every other tenant covers
    them. A fleet-wide count of missing dates misses exactly that, and flags an idle
    day or a fresh install, where nothing is wrong, as if it were damage.
    """
    new_total = Subquery(
        EventMetricsDaily._base_manager.filter(
            organization_id=OuterRef("organization_id"),
            metric_name=OuterRef("metric_name"),
            project=OuterRef("project"),
            tag=OuterRef("tag"),
            date__gte=month_start,
        )
        .annotate(bucket=TruncMonth("date"))
        .filter(bucket=OuterRef("month"))
        .values("bucket")
        .annotate(total=Sum("metric_value"))
        .values("total")[:1]
    )
    # One conjunct, not two: SQL three-valued logic already drops a NULL new_total
    # from `<`, and Django inlines the correlated subquery once per conjunct — so
    # adding `new_total__isnull=False` doubles the per-row subplan executions and
    # changes nothing. A month the daily tier no longer produces at all is left in
    # place by the upsert, which is why NULL is not a lowering.
    lowered = (
        EventMetricsMonthly._base_manager.filter(month__gte=month_start)
        .annotate(new_total=new_total)
        .filter(new_total__lt=F("metric_value"))
        # The full conflict key, not just (org, month): the comparison is per metric,
        # project and tag, so skipping at a coarser grain would freeze a metric whose
        # own total is fine just because a sibling metric's is short.
        .values_list("organization_id", "month", "metric_name", "project", "tag")
        .order_by("month", "organization_id", "metric_name")
    )
    return list(lowered)


def _months_missing_days(month_start: date) -> list[str]:
    """Months in the rollup window whose daily tier is missing whole days.

    The companion to _pairs_the_rollup_would_lower, and neither covers the other's
    cases. That one compares against a stored monthly total, so it is blind twice:
    a month with no stored row yet — the first run of any calendar month — has
    nothing to compare against, and once a short total IS stored it only ever grows,
    so it is never "lowered" again. Both leave an under-count permanent and silent.
    This reads the daily tier itself, so neither blind spot applies.

    Fleet-wide rather than per tenant, because that is the grain the cause has: a
    missing day means the aggregation did not run, which affects every organisation
    at once. Counted per tenant it would instead flag every organisation that was
    merely idle that day, which is normal and constant.

    That grain is also the limit: one row from any tenant for any metric marks a
    date covered, so a day lost by a single tenant or a single metric is invisible
    here. `_pairs_the_rollup_would_lower` is what covers that case, and only where a
    stored total actually falls — neither check sees a partial loss on a month with
    no stored total.

    Whole days only, on both sides of the comparison. A date on which nothing ran
    anywhere reads as a gap and will be reported for the rest of the window; that is
    a false alarm this cannot distinguish from a real one without querying the
    source tables, which is the load this whole change exists to remove.
    """
    yesterday = timezone.now().date() - timedelta(days=1)
    covered = (
        # Whole days on BOTH sides. Counting today while measuring against yesterday
        # lets today's row cancel exactly one missing earlier day, which hides the
        # single-missing-day case entirely once the day's first run has landed.
        EventMetricsDaily._base_manager.filter(date__gte=month_start, date__lte=yesterday)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(days=Count("date", distinct=True))
        .order_by("month")
    )

    short = []
    for row in covered:
        month = row["month"]
        last_day = month.replace(day=calendar.monthrange(month.year, month.month)[1])
        last_complete = min(last_day, yesterday)
        expected = (last_complete - month).days + 1
        if expected > 0 and row["days"] < expected:
            short.append(f"{month:%Y-%m} ({row['days']}/{expected} days)")
    return short


def _name_lowered_pairs(pairs: list[tuple]) -> list[str]:
    """Render the pairs for a log line, capped.

    A fleet-wide daily loss makes this one entry per tenant per month, which would
    otherwise be joined into a single log line and returned in a JSON body.
    """
    seen = sorted({(org_id, month) for org_id, month, *_ in pairs})
    names = [f"{month:%Y-%m} (org {org_id})" for org_id, month in seen]
    total = len(names)
    if total > LOWERED_MONTHS_REPORT_LIMIT:
        names = names[:LOWERED_MONTHS_REPORT_LIMIT]
        # The total, not the cap: three affected tenants and four thousand read
        # identically otherwise, and the count is what decides whether this is one
        # tenant's gap or a fleet-wide one.
        names.append(f"... and {total - LOWERED_MONTHS_REPORT_LIMIT} more of {total}")
    return names


def _rollup_monthly_from_daily(month_start: date, skip: set | None = None) -> int:
    """Sum the daily tier from month_start into monthly, for all orgs at once.

    Pairs in ``skip`` are left untouched: their stored total is higher than what the
    daily tier now sums to, so rewriting them would replace a correct figure with a
    known-short one. That is what makes the prescribed pre-deploy backfill a repair
    step rather than a race against the first scheduled run — the schedule row 0006
    adds goes live at the end of ``migrate``, so the backfill cannot be sequenced
    before it.

    Upsert-only, per the design agreed on UN-3973: a monthly row the daily tier
    no longer produces *at all* is left in place rather than deleted. A stale total
    is recoverable with backfill_metrics; a deleted one is not, because the daily
    rows that would rebuild it are exactly what is missing.

    A month the daily tier covers only *partially* is a different case: date is not
    a grouping key, so its sum is smaller than the stored total. Those rows reach
    this function in ``skip`` and are left alone rather than overwritten — see
    _pairs_the_rollup_would_lower, which needs a stored total to compare against,
    and _months_missing_days, which does not.

    metric_type is aggregated rather than grouped: it is not part of
    unique_monthly_metric, so grouping on it could yield two rows for one
    conflict target.

    Streamed rather than materialised: the grouping spans every organization, so
    holding the whole result and an equal-length list of model instances scales
    with tenant count — and on the PG transport this runs inside a request worker.
    """
    rows = (
        # NULLS DISTINCT: a NULL-org row never matches ON CONFLICT, so it would be
        # re-inserted every run. Latent — but this reads the column, not a loop var.
        EventMetricsDaily._base_manager.filter(date__gte=month_start)
        .exclude(organization_id__isnull=True)
        .annotate(month=TruncMonth("date"))
        .values("organization_id", "month", "metric_name", "project", "tag")
        .annotate(
            value=Sum("metric_value"),
            count=Sum("metric_count"),
            mtype=Min("metric_type"),
        )
        # Ordered so two concurrent rollups take row locks in the same sequence and
        # block rather than deadlock. The aggregate emits no stable order otherwise.
        .order_by("organization_id", "month", "metric_name", "project", "tag")
    )

    upserted = 0
    batch: list[EventMetricsMonthly] = []
    # One transaction per batch, not one across the whole scan. A fleet-wide
    # transaction holds row locks on every rewritten monthly row until the cursor
    # drains, and two runs that do not share a lock key — the :20 row and the 04:40
    # reconcile take different ones, namespaced by window — then contend for the
    # winner's full rollup or deadlock. Each bulk_create is already one statement,
    # so a batch is atomic without an explicit block.
    #
    # What that trades away is an all-or-nothing rewrite. Nothing needed it: every
    # row written is correct as of this run, the upsert is idempotent, and a partial
    # rollup is repaired on the next tick — the same tolerance the hourly and daily
    # tiers in this function already accept. The merge-base had no transaction here
    # at all; monthly was upserted per organization in autocommit.
    skip = skip or set()
    for row in rows.iterator(chunk_size=MONTHLY_ROLLUP_BATCH_SIZE):
        key = (
            row["organization_id"],
            row["month"],
            row["metric_name"],
            row["project"],
            row["tag"],
        )
        if key in skip:
            # This row's stored total is higher than what the daily tier now sums to,
            # so writing it would replace a good figure with a known-short one. Left
            # alone until the daily tier is repaired; the caller warns. Scoped to the
            # exact row, so a sibling metric that is fine still gets its update.
            continue
        batch.append(
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
        )
        if len(batch) >= MONTHLY_ROLLUP_BATCH_SIZE:
            upserted += _upsert_monthly(batch)
            batch = []
    if batch:
        upserted += _upsert_monthly(batch)

    return upserted


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
# Expiry is the only recovery path, so this ordering is the whole guarantee. Equal to
# the shortest schedule period, not under it, so a leaked lock frees exactly on the
# next tick rather than before it. The Celery ceilings (time_limit 660s) sit below it
# but bound only that transport — the internal-HTTP path calls the task body directly,
# where the ceiling is gunicorn's request timeout instead.
AGGREGATION_LOCK_TIMEOUT = 900


def _aggregation_lock_keys(tier: AggregationTier, source_window_days: int) -> list[str]:
    """One key per granularity written, namespaced by source window.

    Per granularity, not per enum member: keying on the label alone gives ALL a third
    key that excludes nothing, so an ALL run and the scheduled hourly run would write
    EventMetricsHourly concurrently. Taking one key per granularity restores that
    exclusion between runs sharing a window, and the two scheduled tiers still never
    block. Across windows it does not exclude — see the next paragraph.

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


def _acquire_aggregation_locks(lock_keys: list[str]) -> tuple[list[str], str]:
    """Take every key or none. Returns the keys taken and this run's owner token."""
    token = uuid4().hex
    taken: list[str] = []
    try:
        for key in lock_keys:
            if not _acquire_aggregation_lock(key, token):
                _release_aggregation_locks(taken, token)
                return [], token
            taken.append(key)
    except Exception:
        # A cache fault partway through would otherwise strand the keys already
        # taken for the full TTL, blocking every tier this run was going to write.
        _release_aggregation_locks(taken, token)
        raise
    return taken, token


def _lock_owner(lock_key: str) -> str | None:
    """The token holding a lock, or None if it is free or holds a legacy value."""
    value = cache.get(lock_key)
    if isinstance(value, str) and ":" in value:
        return value.split(":", 1)[0]
    return None


def _release_aggregation_locks(lock_keys: list[str], token: str) -> None:
    """Release only the keys this run still owns.

    Without the ownership check, a run whose lock had already expired would delete
    whichever run took the key next, letting a third in immediately.

    This narrows that window to one cache round trip rather than closing it: the
    read and the delete are separate calls and Django's cache API has no
    compare-and-delete. Bounded, because the writes on either side are idempotent
    upserts — a compare-and-delete would need a Redis-specific Lua eval.
    """
    for key in lock_keys:
        try:
            if _lock_owner(key) == token:
                cache.delete(key)
        except Exception:
            logger.exception("Failed to release aggregation lock %s", key)


def _acquire_aggregation_lock(lock_key: str, token: str) -> bool:
    """Acquire one aggregation lock, storing this run's token with the timestamp.

    A crashed run (OOM kill, SIGKILL) is recovered by the key's own
    AGGREGATION_LOCK_TIMEOUT TTL, and that is the only recovery path.

    Never reclaimed by age. Reading a value, judging it stale and replacing it is
    not atomic — two runs can both read the same timestamp, both delete and both
    add, the second wiping the first's fresh lock while both believe they hold it.
    The age check could not tell a live holder from a dead one anyway, since it
    compares a local clock against another worker's.

    Exclusion does not span the key format. These keys are new in this release, so
    a run on the previous image holds a different key and neither blocks the other;
    the overlap is bounded by the rollout.

    Returns:
        True if the lock was acquired, False if another run is legitimately active.
    """
    if cache.add(lock_key, f"{token}:{time.time()}", AGGREGATION_LOCK_TIMEOUT):
        return True
    # Anything already here belongs to a run this code did not start.
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
    **_ignored: Any,
) -> dict[str, Any]:
    """Aggregate source tables into the hourly, daily and monthly tiers.

    Three schedules call this: the hourly tier every 15 minutes, the daily and
    monthly tiers hourly at :20, and a once-daily reconciliation pass over the
    daily and monthly tiers at a wider window. Hourly covers the last 24h, daily the source window,
    monthly is rolled up from daily.

    Args:
        tier: An AggregationTier value. Defaults to all, so a caller that omits it
            — a schedule row written before 0006 — writes every tier rather than
            none.
        source_window_days: Daily-tier source lookback. The reconciliation pass
            reruns this task at DASHBOARD_RECONCILE_WINDOW_DAYS to repair gaps
            after downtime.
        _ignored: Unknown kwargs are accepted rather than rejected. This does NOT
            protect the deploy that introduces a kwarg — a pod on the previous image
            has the old signature and still raises TypeError; that window is bounded
            by the rollout. What it buys is that a LATER release may add a kwarg to a
            schedule row without breaking pods still running this one. Dropped keys
            are logged, because the same tolerance would otherwise hide a typo.

    Returns:
        Dict with aggregation summary for the tiers that ran

    Raises:
        ValueError: tier is not a recognised AggregationTier, or the window is not
            an integer between 1 and MAX_SOURCE_WINDOW_DAYS
    """
    if _ignored:
        # Tolerated for the rolling-deploy case above, but an unrecognised key is far
        # more often a typo in an editable schedule row — and a reconciliation row
        # whose window kwarg is misspelled silently runs at the 2-day default.
        logger.warning("Ignoring unrecognised aggregation kwargs: %s", sorted(_ignored))
    tier = AggregationTier(tier)
    source_window_days = _validate_source_window(source_window_days)
    lock_keys = _aggregation_lock_keys(tier, source_window_days)

    held, token = _acquire_aggregation_locks(lock_keys)
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
        # Isolated per key: a raise here would replace the run's return value, reporting
        # a completed aggregation as a hard failure, and would strand the keys after it.
        # The TTL bounds whatever is not released.
        _release_aggregation_locks(held, token)


def _aggregate_single_metric(
    query_method,
    *,
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
        day_ts = truncate_to_day(row["period"])
        key = (org_id, day_ts.date().isoformat(), metric_name, "default", "")
        _upsert_agg(daily_agg, key, metric_type, row["value"] or 0)


def _aggregate_llm_combined(
    org_id: str,
    *,
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
        day_str = truncate_to_day(row["period"]).date().isoformat()
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
    *,
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
                metric_name=metric_name,
                metric_type=metric_type,
                org_id=org_id,
                hourly_start=hourly_start,
                daily_start=daily_start,
                end_date=end_date,
                hourly_agg=hourly_agg,
                daily_agg=daily_agg,
                tier=tier,
                extra_kwargs=extra_kwargs,
            )
        except SoftTimeLimitExceeded:
            # Ahead of the broad catch: it subclasses Exception, and swallowing it
            # defeats the soft limit's whole purpose.
            raise
        except Exception:
            logger.exception("Error querying %s for org %s", metric_name, org_id)
            errors += 1

    try:
        _aggregate_llm_combined(
            org_id,
            hourly_start=hourly_start,
            daily_start=daily_start,
            end_date=end_date,
            hourly_agg=hourly_agg,
            daily_agg=daily_agg,
            llm_combined_fields=LLM_COMBINED_FIELDS,
            tier=tier,
        )
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        logger.exception("Error querying combined LLM metrics for org %s", org_id)
        errors += 1

    return hourly_agg, daily_agg, errors


def _aggregate_org(
    org: Organization,
    *,
    hourly_start: datetime,
    daily_start: datetime,
    end_date: datetime,
    tier: AggregationTier,
    stats: dict[str, Any],
) -> None:
    """Aggregate one organization and upsert the tiers this run writes."""
    hourly_agg, daily_agg, errors = _collect_org_metrics(
        org,
        hourly_start=hourly_start,
        daily_start=daily_start,
        end_date=end_date,
        tier=tier,
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
        # Reported, not enforced: _run answers 200 for any dict, so this does not
        # fail the call. `errors` is what the worker alerts on and what switches the
        # completion line to WARNING.
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


# An upper sanity guard on a value that arrives as JSON from an editable schedule row,
# not a bound derived from the run budget: 90 days is itself wider than the 32-62 day
# scan this change removed, so a window near it is a manual repair, not a routine run.
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


def _run_diagnostic(
    check: Callable[[date], list],
    month_start: date,
    stats: dict[str, Any],
    key: str,
    what: str,
) -> list:
    """Run one pre-rollup check, returning [] if it fails rather than aborting.

    The rollup is the job and these only inform it, so a failing check must not
    skip the upsert. It is still counted: `[]` alone reads as "checked, nothing
    found", and a failed lowering check means the upsert runs with that guard off.
    One call each, so one failing does not disable the other. The soft time limit
    is the exception and does propagate.
    """
    try:
        return check(month_start)
    except SoftTimeLimitExceeded:
        # Swallowing it would hand an empty `skip` to the rollup, guard off.
        raise
    except Exception:
        logger.exception("Could not %s", what)
        stats["monthly"][key] = "unavailable"
        stats["errors"] += 1
        return []


_KEPT_MSG = (
    "Monthly rollup left %s unchanged — the daily tier now sums lower than the "
    "stored total, so the figures were kept rather than overwritten. Repair daily "
    "for those months with `backfill_metrics`"
)

_SHORT_TIER_MSG = (
    "Monthly rollup ran against an incomplete daily tier for %s — those totals are "
    "under-counted whether or not they were lowered. Repair with `backfill_metrics` "
    "if the source tables hold those days; a date on which nothing ran anywhere "
    "reads the same and needs no action"
)


def _report(stats: dict[str, Any], key: str, names: list[str], message: str) -> None:
    """Record one monthly-tier gap in the result and the log, if there is one."""
    if not names:
        return
    stats["monthly"][key] = names
    logger.warning(message, ", ".join(names))


def _roll_up_monthly(monthly_start: date, stats: dict[str, Any]) -> None:
    """Derive the monthly tier from daily, recording a failure distinctly."""
    # Before the upsert, while the stored values are still the old ones.
    lowered_pairs = _run_diagnostic(
        _pairs_the_rollup_would_lower,
        monthly_start,
        stats,
        "lowered_check",
        "check whether the rollup lowers monthly totals",
    )
    missing_days = _run_diagnostic(
        _months_missing_days,
        monthly_start,
        stats,
        "coverage_check",
        "check whether the daily tier is missing whole days",
    )

    try:
        stats["monthly"]["upserted"] = _rollup_monthly_from_daily(
            monthly_start, skip=set(lowered_pairs)
        )
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        # Counted, not raised: autoretry_for is a no-op on the internal-HTTP path,
        # where Task.retry re-raises under called_directly. errors > 0 is the signal.
        logger.exception("Error rolling up monthly metrics from %s", monthly_start)
        stats["monthly"]["failed"] = True
        stats["errors"] += 1
        return

    _report(stats, "needs_daily_repair", _name_lowered_pairs(lowered_pairs), _KEPT_MSG)
    # Reported, not skipped: refusing to write a short month leaves dashboards empty
    # rather than slightly low, and there is no stored total here to preserve.
    _report(stats, "incomplete_daily_coverage", missing_days, _SHORT_TIER_MSG)


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
    daily_start = truncate_to_day(end_date - timedelta(days=source_window_days))
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

    # No early return on an empty shortlist: the monthly rollup is org-agnostic, so
    # it must still run. An empty id__in issues no query, so the loop below is free.
    organizations = Organization.objects.filter(id__in=active_org_ids).only(
        "id", "organization_id"
    )

    for org in organizations:
        try:
            _aggregate_org(
                org,
                hourly_start=hourly_start,
                daily_start=daily_start,
                end_date=end_date,
                tier=tier,
                stats=stats,
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.exception("Error processing org %s", org.id)
            stats["errors"] += 1

    if _writes_daily_monthly(tier):
        _roll_up_monthly(monthly_start, stats)

    # A tier with orgs to process, no error and nothing written is the regression
    # signature of narrowing the source window. Raised here rather than only in the
    # worker proxy, which the Celery transport never loads.
    #
    # Daily/monthly only. The prefilter shortlists orgs active in the last
    # DASHBOARD_ACTIVE_ORG_LOOKBACK_DAYS days while the hourly tier queries 24h, so an
    # org quiet for 2-7 days is shortlisted and contributes nothing — on the */15 row
    # that would warn 96 times a day about a healthy weekend.
    wrote_nothing = (
        _writes_daily_monthly(tier)
        and active_org_ids
        and not stats["errors"]
        and not any(
            stats[granularity]["upserted"]
            for granularity in ("hourly", "daily", "monthly")
        )
    )
    log = logger.warning if stats["errors"] or wrote_nothing else logger.info
    # tier and window are named because three schedules now emit this line and they
    # can overlap: without them a reconcile run is indistinguishable from a routine
    # one, and the window this change turns on appears in no successful run's logs.
    log(
        "Aggregation completed (tier=%s window=%dd): %d orgs, "
        "hourly=%d, daily=%d, monthly=%d, errors=%d",
        tier.value,
        source_window_days,
        stats["orgs_processed"],
        stats["hourly"]["upserted"],
        stats["daily"]["upserted"],
        stats["monthly"]["upserted"],
        stats["errors"],
    )

    return _build_result(
        stats,
        hourly_start,
        daily_start,
        monthly_start,
        end_date,
        tier,
        skipped_reason="no_active_orgs" if not active_org_ids else None,
    )


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
