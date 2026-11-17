"""Management command to backfill metrics from source tables.

This command populates EventMetricsHourly, EventMetricsDaily, and EventMetricsMonthly
tables from historical data in source tables (Usage, PageUsage, WorkflowExecution, etc.)

The current and previous month are recomputed from the daily tier by the aggregation
task's daily/monthly pass, so inside that window this command's monthly output is
overwritten and --skip-monthly is largely a no-op. --skip-daily leaves that tier short
on purpose: the rollup will not lower a stored monthly total it would reduce, so the
month is not under-counted, but it is frozen at the stored figure until daily is
repaired, and the daily tier the dashboards read stays wrong meanwhile. Repair daily.

It never lowers a stored metric_value: the sources shrink after aggregation (HITL TTL
cleanup, workflow deletes), so a lower recount keeps the stored row. The scheduled
aggregator still rewrites rows inside its own window. Monthly is summed from the
daily rows after their check, so a month never sits below its own days.

Usage:
    python manage.py backfill_metrics --days=30
    python manage.py backfill_metrics --days=90 --org-id=5
    python manage.py backfill_metrics --days=7 --dry-run
    python manage.py backfill_metrics --days=90 --active-only
    python manage.py backfill_metrics --start-date=2026-03-12 --end-date=2026-04-08 \
        --skip-hourly --skip-monthly
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from account_v2.models import Organization
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    Granularity,
    MetricType,
)
from dashboard_metrics.services import MetricsQueryService
from dashboard_metrics.tasks import truncate_to_day

logger = logging.getLogger(__name__)

# One parameter per column per row; Postgres allows 65,535 a statement.
UPSERT_BATCH_SIZE = 1000

# Cloud-only: Subscription model for --active-only filtering
try:
    from pluggable_apps.subscription_v2.models import Subscription

    HAS_SUBSCRIPTION = True
except ImportError:
    HAS_SUBSCRIPTION = False


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


class Command(BaseCommand):
    help = "Backfill metrics from source tables into aggregated tables"

    # Metric configurations: (name, query_method, is_histogram)
    # LLM metrics are handled separately via get_llm_metrics_split().
    METRIC_CONFIGS = [
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

    # LLM metric names and whether they are histograms
    LLM_METRIC_TYPES: dict[str, bool] = {
        "llm_calls": False,
        "challenges": False,
        "summarization_calls": False,
        "llm_usage": True,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="First UTC day to backfill (YYYY-MM-DD). Overrides --days.",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=None,
            help=(
                "Last UTC day to backfill, inclusive (YYYY-MM-DD). Requires "
                "--start-date. Default: now."
            ),
        )
        parser.add_argument(
            "--org-id",
            type=str,
            default=None,
            help="Specific organization ID to backfill (default: all orgs)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--skip-hourly",
            action="store_true",
            help=(
                "Skip the HOUR-granularity source queries, not just their upsert. "
                "The deploy step passes it over a window measured in weeks."
            ),
        )
        parser.add_argument(
            "--skip-daily",
            action="store_true",
            help=(
                "Skip daily aggregation. Leaves the daily tier short for the "
                "current and previous month. The rollup's guard keeps monthly from "
                "being lowered, so the month freezes at its stored total rather than "
                "under-counting — but daily stays wrong until it is repaired."
            ),
        )
        parser.add_argument(
            "--skip-monthly",
            action="store_true",
            help=(
                "Skip monthly aggregation. Largely a no-op for the current and "
                "previous month: the aggregation task rederives them from daily, "
                "except where its guard preserves a higher stored total."
            ),
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help=(
                "Only process orgs with an active subscription "
                "(cloud-only, requires subscription_v2)"
            ),
        )

    def handle(self, *args, **options):
        days = options["days"]
        org_id = options.get("org_id")
        dry_run = options["dry_run"]
        skip_hourly = options["skip_hourly"]
        skip_daily = options["skip_daily"]
        skip_monthly = options["skip_monthly"]
        active_only = options["active_only"]

        start_date, end_date = self._resolve_window(
            days, options["start_date"], options["end_date"]
        )

        if (
            options["start_date"]
            and not skip_monthly
            and not self._covers_whole_months(start_date, end_date, options["end_date"])
        ):
            raise CommandError(
                "The range covers part of a month, so its monthly total would be "
                "summed from days this run did not rebuild. Pass --skip-monthly, or "
                "give whole months."
            )

        self.stdout.write(f"Backfill period: {start_date.date()} to {end_date.date()}")

        if skip_daily and not skip_monthly:
            self.stdout.write(
                self.style.WARNING(
                    "--skip-daily without --skip-monthly: the daily tier is left "
                    "short, so the rollup's guard will freeze the current and "
                    "previous month at their stored totals. Repair daily."
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        # Get organizations to process
        org_ids = self._resolve_org_ids(
            org_id=org_id,
            active_only=active_only,
        )

        if not org_ids:
            self.stdout.write(self.style.WARNING("No organizations to process"))
            return

        self.stdout.write(f"Processing {len(org_ids)} organizations")

        total_stats = {
            "hourly": {"upserted": 0},
            "daily": {"upserted": 0},
            "monthly": {"upserted": 0},
            "errors": 0,
        }

        # Pre-resolve org identifiers for PageUsage queries (avoids
        # redundant Organization lookups inside the metric query loop).
        org_identifiers = dict(
            Organization.objects.filter(
                id__in=[int(oid) if oid.isdigit() else oid for oid in org_ids]
            ).values_list("id", "organization_id")
        )

        for i, current_org_id in enumerate(org_ids):
            self.stdout.write(
                f"\n[{i + 1}/{len(org_ids)}] Processing org: {current_org_id}"
            )

            try:
                # Resolve org string identifier for PageUsage queries
                org_id_key = (
                    int(current_org_id) if current_org_id.isdigit() else current_org_id
                )
                org_identifier = org_identifiers.get(org_id_key)

                # Collect all metric data for this org
                hourly_data, daily_data, monthly_data, failures = self._collect_metrics(
                    current_org_id,
                    start_date,
                    end_date,
                    org_identifier=org_identifier,
                    skip_hourly=skip_hourly,
                )
                total_stats["errors"] += failures

                self.stdout.write(
                    f"  Collected: {len(hourly_data)} hourly, "
                    f"{len(daily_data)} daily, {len(monthly_data)} monthly records"
                )

                if not dry_run:
                    # Write to tables (bulk INSERT...ON CONFLICT)
                    if not skip_hourly:
                        h_count = self._bulk_upsert_hourly(hourly_data)
                        total_stats["hourly"]["upserted"] += h_count
                        self.stdout.write(f"  Hourly: {h_count} upserted")

                    if not skip_daily:
                        d_count = self._bulk_upsert_daily(daily_data)
                        total_stats["daily"]["upserted"] += d_count
                        self.stdout.write(f"  Daily: {d_count} upserted")

                    if not skip_monthly:
                        if not skip_daily:
                            monthly_data = self._monthly_from_daily(
                                current_org_id, monthly_data
                            )
                        m_count = self._bulk_upsert_monthly(monthly_data)
                        total_stats["monthly"]["upserted"] += m_count
                        self.stdout.write(f"  Monthly: {m_count} upserted")

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"  Error processing org {current_org_id}: {e}")
                )
                total_stats["errors"] += 1
                logger.exception("Error backfilling org %s", current_org_id)

        # Print summary
        failed = total_stats["errors"]
        self.stdout.write("\n" + "=" * 50)
        style = self.style.ERROR if failed else self.style.SUCCESS
        self.stdout.write(style("BACKFILL FAILED" if failed else "BACKFILL COMPLETE"))
        self.stdout.write(f"Hourly: {total_stats['hourly']['upserted']} upserted")
        self.stdout.write(f"Daily: {total_stats['daily']['upserted']} upserted")
        self.stdout.write(f"Monthly: {total_stats['monthly']['upserted']} upserted")
        self.stdout.write(f"Errors: {failed}")
        if failed:
            # Non-zero exit, so a deploy runbook cannot tick this step green. The
            # rows that did land are kept: this repairs the daily tier, and a partial
            # repair is worth more than a rollback.
            raise CommandError(
                f"{failed} error(s) during backfill; the metrics tiers are "
                "incomplete. Re-run before the next aggregation."
            )

    @staticmethod
    def _resolve_window(
        days: int, start_day: str | None, end_day: str | None
    ) -> tuple[datetime, datetime]:
        """Return the (start, end) instants to backfill, both whole UTC days."""
        if end_day and not start_day:
            raise CommandError("--end-date requires --start-date")
        if not start_day:
            end_date = timezone.now()
            # Truncated to match the cron's daily_start: an untruncated boundary
            # writes the oldest day covering only part of it, and the monthly rollup
            # sums the persisted daily tier rather than recomputing it from source.
            return truncate_to_day(end_date - timedelta(days=days)), end_date

        try:
            start_date = datetime.combine(date.fromisoformat(start_day), time.min, UTC)
            end_date = timezone.now()
            if end_day:
                # The source queries are end-inclusive, so stop just short of the
                # next midnight: ending on it would rewrite that day with only the
                # rows stamped at exactly 00:00.
                next_day = date.fromisoformat(end_day) + timedelta(days=1)
                end_date = datetime.combine(next_day, time.min, UTC) - timedelta(
                    microseconds=1
                )
        except ValueError as e:
            raise CommandError(f"Dates must be YYYY-MM-DD: {e}") from e
        if start_date > end_date:
            raise CommandError("--start-date is after --end-date")
        return start_date, end_date

    @staticmethod
    def _covers_whole_months(
        start_date: datetime, end_date: datetime, end_day: str | None
    ) -> bool:
        """Whether every month in the range is complete in it.

        Without --end-date the range ends now, in the current month, which the
        aggregation task rederives from daily anyway.
        """
        ends_on_month_end = end_day is None or (
            (end_date + timedelta(microseconds=1)).day == 1
        )
        return start_date.day == 1 and ends_on_month_end

    def _resolve_org_ids(
        self,
        org_id: str | None,
        active_only: bool,
    ) -> list[str]:
        """Resolve the list of organization PKs to process.

        Returns Organization.id (int PK) values as strings, since all
        downstream queries (services, bulk upserts) use the FK which
        references Organization.id, not Organization.organization_id.

        Applies filters in order:
        1. Single org (--org-id) — returns immediately
        2. Active subscription filter (--active-only) — cloud only
        """
        # Single org mode
        if org_id:
            try:
                org = Organization.objects.filter(id=org_id).first()
            except (ValueError, TypeError):
                org = None
            if not org:
                self.stderr.write(self.style.ERROR(f"Organization {org_id} not found"))
                return []
            self.stdout.write(f"Single org mode: {org_id}")
            return [str(org.id)]

        # Get org PKs based on filtering mode
        if active_only and HAS_SUBSCRIPTION:
            active_org_id_strings = set(
                Subscription.objects.filter(is_active=True).values_list(
                    "organization_id", flat=True
                )
            )
            # Map org_* strings back to Organization PKs
            all_org_ids = set(
                Organization.objects.filter(
                    organization_id__in=active_org_id_strings
                ).values_list("id", flat=True)
            )
            self.stdout.write(
                f"Active organizations (subscription filter): {len(all_org_ids)}"
            )
        elif active_only and not HAS_SUBSCRIPTION:
            self.stdout.write(
                self.style.WARNING(
                    "subscription_v2 not available (OSS mode), ignoring --active-only"
                )
            )
            all_org_ids = set(Organization.objects.values_list("id", flat=True))
            self.stdout.write(f"Total organizations: {len(all_org_ids)}")
        else:
            all_org_ids = set(Organization.objects.values_list("id", flat=True))
            self.stdout.write(f"Total organizations: {len(all_org_ids)}")

        return sorted(str(oid) for oid in all_org_ids)

    @staticmethod
    def _granularities(skip_hourly: bool) -> tuple:
        """Which granularities to query.

        `--skip-hourly` skips the HOUR *queries*, not just their upsert: the deploy
        step passes it over a window measured in weeks, and issuing them anyway
        reinstates the scan this change exists to remove.
        """
        return (Granularity.DAY,) if skip_hourly else (Granularity.HOUR, Granularity.DAY)

    def _collect_metrics(
        self,
        org_id: str,
        start_date: datetime,
        end_date: datetime,
        org_identifier: str | None = None,
        skip_hourly: bool = False,
    ) -> tuple[dict, dict, dict, int]:
        """Collect metrics from source tables for all granularities.

        Returns the aggregations plus a count of failed metric queries. Each query
        is caught individually, so a failure never reaches the per-organisation
        handler that owns the error counter — it has to be carried back explicitly,
        the same way ``_collect_org_metrics`` does in ``tasks.py``.

        ``skip_hourly`` skips the HOUR-granularity source queries, not just their
        upsert. The prescribed deploy step passes it over a window measured in
        weeks, and issuing those queries anyway would reinstate the scan this
        change exists to remove.
        """
        failures = 0
        hourly_agg = {}
        daily_agg = {}
        monthly_agg = {}

        def _ingest_results(
            results: list[dict[str, Any]],
            metric_name: str,
            metric_type: str,
        ) -> None:
            """Ingest query results into hourly/daily/monthly aggregation dicts."""
            for row in results:
                period = row["period"]
                value = row["value"] or 0
                hour_ts = self._truncate_to_hour(period)
                key = (org_id, hour_ts.isoformat(), metric_name, "default", "")

                if key not in hourly_agg:
                    hourly_agg[key] = {
                        "metric_type": metric_type,
                        "value": 0,
                        "count": 0,
                    }
                hourly_agg[key]["value"] += value
                hourly_agg[key]["count"] += 1

        def _ingest_daily_results(
            results: list[dict[str, Any]],
            metric_name: str,
            metric_type: str,
        ) -> None:
            """Ingest daily query results into daily and monthly aggregation dicts."""
            for row in results:
                period = row["period"]
                value = row["value"] or 0
                day_date = period.date() if hasattr(period, "date") else period
                key = (org_id, day_date.isoformat(), metric_name, "default", "")

                if key not in daily_agg:
                    daily_agg[key] = {
                        "metric_type": metric_type,
                        "value": 0,
                        "count": 0,
                    }
                daily_agg[key]["value"] += value
                daily_agg[key]["count"] += 1

                # Monthly aggregation from daily results
                if hasattr(period, "date"):
                    month_date = period.replace(day=1).date()
                else:
                    month_date = period.replace(day=1)
                mkey = (org_id, month_date.isoformat(), metric_name, "default", "")

                if mkey not in monthly_agg:
                    monthly_agg[mkey] = {
                        "metric_type": metric_type,
                        "value": 0,
                        "count": 0,
                    }
                monthly_agg[mkey]["value"] += value
                monthly_agg[mkey]["count"] += 1

        # Fetch all 4 LLM metrics in one query per granularity
        try:
            for granularity in self._granularities(skip_hourly):
                llm_split = MetricsQueryService.get_llm_metrics_split(
                    org_id, start_date, end_date, granularity
                )
                for metric_name, data in llm_split.items():
                    is_histogram = self.LLM_METRIC_TYPES[metric_name]
                    metric_type = (
                        MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER
                    )
                    if granularity == Granularity.HOUR:
                        _ingest_results(data, metric_name, metric_type)
                    else:
                        _ingest_daily_results(data, metric_name, metric_type)
        except Exception:
            # Counted: every metric query is caught individually, so a failure here
            # never reaches the per-org handler that owns the error counter.
            failures += 1
            logger.exception("Error querying LLM metrics for org %s", org_id)

        # Fetch remaining (non-LLM) metrics individually
        for metric_name, query_method, is_histogram in self.METRIC_CONFIGS:
            metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

            # Pass org_identifier to PageUsage-based metrics to
            # avoid redundant Organization lookups per call.
            extra_kwargs: dict[str, Any] = {}
            if metric_name == "pages_processed":
                extra_kwargs["org_identifier"] = org_identifier

            try:
                if Granularity.HOUR in self._granularities(skip_hourly):
                    hourly_results = query_method(
                        org_id,
                        start_date,
                        end_date,
                        granularity=Granularity.HOUR,
                        **extra_kwargs,
                    )
                    _ingest_results(hourly_results, metric_name, metric_type)

                daily_results = query_method(
                    org_id,
                    start_date,
                    end_date,
                    granularity=Granularity.DAY,
                    **extra_kwargs,
                )
                _ingest_daily_results(daily_results, metric_name, metric_type)

            except Exception:
                failures += 1
                logger.exception("Error querying %s for org %s", metric_name, org_id)

        return hourly_agg, daily_agg, monthly_agg, failures

    def _truncate_to_hour(self, ts: datetime) -> datetime:
        """Truncate datetime to hour."""
        if ts.tzinfo is None:
            ts = timezone.make_aware(ts, timezone.utc)
        return ts.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _monthly_from_daily(org_id: str, monthly_agg: dict) -> dict:
        """Sum the stored daily rows of each month the recount touched.

        Runs after the daily upsert, so a day whose higher stored value was kept
        counts at that value. Summing the raw recount instead would leave a month
        below its own days. Grouped as the aggregator's monthly rollup groups.
        """
        months = {_parse_date(key[1]) for key in monthly_agg}
        if not months:
            return {}
        last = max(months)
        after_last = (last.replace(day=28) + timedelta(days=4)).replace(day=1)
        rows = (
            EventMetricsDaily._base_manager.filter(
                organization_id=org_id, date__gte=min(months), date__lt=after_last
            )
            .annotate(month=TruncMonth("date"))
            .values("month", "metric_name", "project", "tag")
            .annotate(
                value=Sum("metric_value"),
                count=Sum("metric_count"),
                mtype=Min("metric_type"),
            )
        )
        return {
            (
                org_id,
                row["month"].isoformat(),
                row["metric_name"],
                row["project"],
                row["tag"],
            ): {
                "metric_type": row["mtype"],
                "value": row["value"],
                "count": row["count"],
            }
            for row in rows
        }

    def _bulk_upsert_hourly(self, aggregations: dict) -> int:
        return self._upsert(
            EventMetricsHourly,
            "timestamp",
            datetime.fromisoformat,
            aggregations,
            "Hourly",
        )

    def _bulk_upsert_daily(self, aggregations: dict) -> int:
        return self._upsert(EventMetricsDaily, "date", _parse_date, aggregations, "Daily")

    def _bulk_upsert_monthly(self, aggregations: dict) -> int:
        return self._upsert(
            EventMetricsMonthly, "month", _parse_date, aggregations, "Monthly"
        )

    def _upsert(
        self, model, period_field: str, parse, aggregations: dict, tier: str
    ) -> int:
        """Write the recounts that do not lower a stored value, in one statement each batch.

        INSERT ... ON CONFLICT DO UPDATE ... WHERE excluded >= stored compares
        against the row it has locked, so a value the aggregator commits first is
        never lowered, and a separate read cannot go stale or join a lock cycle.
        Rows go in the order the monthly rollup locks them.
        """
        objects = sorted(
            (
                model(
                    organization_id=org_id,
                    metric_name=metric_name,
                    project=project,
                    tag=tag,
                    metric_type=agg["metric_type"],
                    metric_value=agg["value"],
                    metric_count=agg["count"],
                    **{period_field: parse(period)},
                )
                for (
                    org_id,
                    period,
                    metric_name,
                    project,
                    tag,
                ), agg in aggregations.items()
            ),
            key=lambda o: (
                getattr(o, period_field),
                o.metric_name,
                o.project,
                o.tag,
            ),
        )
        quote = connection.ops.quote_name
        fields = model._meta.concrete_fields
        table = quote(model._meta.db_table)
        unique = ("organization", period_field, "metric_name", "project", "tag")
        updated = ("metric_type", "metric_value", "metric_count", "modified_at")
        row = "(" + ", ".join(["%s"] * len(fields)) + ")"
        sql_tail = (
            f" ON CONFLICT ({', '.join(quote(model._meta.get_field(f).column) for f in unique)})"
            f" DO UPDATE SET {', '.join(f'{quote(c)} = EXCLUDED.{quote(c)}' for c in updated)}"
            f" WHERE EXCLUDED.metric_value >= {table}.metric_value RETURNING 1"
        )
        written = 0
        with connection.cursor() as cursor:
            for i in range(0, len(objects), UPSERT_BATCH_SIZE):
                batch = objects[i : i + UPSERT_BATCH_SIZE]
                params = [
                    f.get_db_prep_save(f.pre_save(obj, True), connection)
                    for obj in batch
                    for f in fields
                ]
                # Only quoted names from model metadata are formatted in; values
                # go as parameters.
                cursor.execute(  # NOSONAR
                    f"INSERT INTO {table} ({', '.join(quote(f.column) for f in fields)})"
                    f" VALUES {', '.join([row] * len(batch))}{sql_tail}",
                    params,
                )
                written += len(cursor.fetchall())
        kept = len(objects) - written
        if kept:
            self.stdout.write(f"  {tier}: kept {kept} stored values above the recount")
        return written
