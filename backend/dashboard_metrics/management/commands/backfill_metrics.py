"""Management command to backfill metrics from source tables.

This command populates EventMetricsHourly, EventMetricsDaily, and EventMetricsMonthly
tables from historical data in source tables (Usage, PageUsage, WorkflowExecution, etc.)

Usage:
    python manage.py backfill_metrics --days=30
    python manage.py backfill_metrics --days=90 --org-id=5
    python manage.py backfill_metrics --days=7 --dry-run
    python manage.py backfill_metrics --days=90 --active-only
"""

import logging
from datetime import datetime, timedelta

from account_v2.models import Organization
from django.core.management.base import BaseCommand
from django.utils import timezone

from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
    Granularity,
    MetricType,
)
from dashboard_metrics.services import MetricsQueryService

logger = logging.getLogger(__name__)

# Cloud-only: Subscription model for --active-only filtering
try:
    from pluggable_apps.subscription_v2.models import Subscription

    HAS_SUBSCRIPTION = True
except ImportError:
    HAS_SUBSCRIPTION = False


class Command(BaseCommand):
    help = "Backfill metrics from source tables into aggregated tables"

    # Metric configurations: (name, query_method, is_histogram)
    METRIC_CONFIGS = [
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

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
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
            help="Skip hourly aggregation (only do daily/monthly)",
        )
        parser.add_argument(
            "--skip-daily",
            action="store_true",
            help="Skip daily aggregation",
        )
        parser.add_argument(
            "--skip-monthly",
            action="store_true",
            help="Skip monthly aggregation",
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

        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        self.stdout.write(f"Backfill period: {start_date.date()} to {end_date.date()}")
        self.stdout.write(f"Days: {days}")

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
                hourly_data, daily_data, monthly_data = self._collect_metrics(
                    current_org_id,
                    start_date,
                    end_date,
                    org_identifier=org_identifier,
                )

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
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("BACKFILL COMPLETE"))
        self.stdout.write(f"Hourly: {total_stats['hourly']['upserted']} upserted")
        self.stdout.write(f"Daily: {total_stats['daily']['upserted']} upserted")
        self.stdout.write(f"Monthly: {total_stats['monthly']['upserted']} upserted")
        self.stdout.write(f"Errors: {total_stats['errors']}")

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

    def _collect_metrics(
        self,
        org_id: str,
        start_date: datetime,
        end_date: datetime,
        org_identifier: str | None = None,
    ) -> tuple[dict, dict, dict]:
        """Collect metrics from source tables for all granularities."""
        hourly_agg = {}
        daily_agg = {}
        monthly_agg = {}

        for metric_name, query_method, is_histogram in self.METRIC_CONFIGS:
            metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

            # Pass org_identifier to PageUsage-based metrics to
            # avoid redundant Organization lookups per call.
            extra_kwargs = {}
            if metric_name == "pages_processed":
                extra_kwargs["org_identifier"] = org_identifier

            try:
                # Query hourly data
                hourly_results = query_method(
                    org_id,
                    start_date,
                    end_date,
                    granularity=Granularity.HOUR,
                    **extra_kwargs,
                )
                for row in hourly_results:
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

                # Query daily data
                daily_results = query_method(
                    org_id,
                    start_date,
                    end_date,
                    granularity=Granularity.DAY,
                    **extra_kwargs,
                )
                for row in daily_results:
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

                # Query for monthly (aggregate daily results by month)
                for row in daily_results:
                    period = row["period"]
                    value = row["value"] or 0
                    if hasattr(period, "date"):
                        month_date = period.replace(day=1).date()
                    else:
                        month_date = period.replace(day=1)
                    key = (org_id, month_date.isoformat(), metric_name, "default", "")

                    if key not in monthly_agg:
                        monthly_agg[key] = {
                            "metric_type": metric_type,
                            "value": 0,
                            "count": 0,
                        }
                    monthly_agg[key]["value"] += value
                    monthly_agg[key]["count"] += 1

            except Exception as e:
                logger.warning("Error querying %s for org %s: %s", metric_name, org_id, e)

        return hourly_agg, daily_agg, monthly_agg

    def _truncate_to_hour(self, ts: datetime) -> datetime:
        """Truncate datetime to hour."""
        if ts.tzinfo is None:
            ts = timezone.make_aware(ts, timezone.utc)
        return ts.replace(minute=0, second=0, microsecond=0)

    def _bulk_upsert_hourly(self, aggregations: dict) -> int:
        """Bulk upsert hourly aggregations using INSERT ... ON CONFLICT."""
        objects = []
        for key, agg in aggregations.items():
            org_id, ts_str, metric_name, project, tag = key
            objects.append(
                EventMetricsHourly(
                    organization_id=org_id,
                    timestamp=datetime.fromisoformat(ts_str),
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
            unique_fields=[
                "organization",
                "timestamp",
                "metric_name",
                "project",
                "tag",
            ],
            update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
        )
        return len(objects)

    def _bulk_upsert_daily(self, aggregations: dict) -> int:
        """Bulk upsert daily aggregations using INSERT ... ON CONFLICT."""
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
            unique_fields=[
                "organization",
                "date",
                "metric_name",
                "project",
                "tag",
            ],
            update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
        )
        return len(objects)

    def _bulk_upsert_monthly(self, aggregations: dict) -> int:
        """Bulk upsert monthly aggregations using INSERT ... ON CONFLICT."""
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
            unique_fields=[
                "organization",
                "month",
                "metric_name",
                "project",
                "tag",
            ],
            update_fields=["metric_type", "metric_value", "metric_count", "modified_at"],
        )
        return len(objects)
