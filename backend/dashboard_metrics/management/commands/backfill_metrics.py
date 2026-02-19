"""Management command to backfill metrics from source tables.

This command populates EventMetricsHourly, EventMetricsDaily, and EventMetricsMonthly
tables from historical data in source tables (Usage, PageUsage, WorkflowExecution, etc.)

Usage:
    python manage.py backfill_metrics --days=30
    python manage.py backfill_metrics --days=90 --org-id=12
    python manage.py backfill_metrics --days=7 --dry-run
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
    MetricType,
)
from dashboard_metrics.services import MetricsQueryService

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        days = options["days"]
        org_id = options.get("org_id")
        dry_run = options["dry_run"]
        skip_hourly = options["skip_hourly"]
        skip_daily = options["skip_daily"]
        skip_monthly = options["skip_monthly"]

        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        self.stdout.write(f"Backfill period: {start_date.date()} to {end_date.date()}")
        self.stdout.write(f"Days: {days}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        # Get organizations to process
        if org_id:
            try:
                orgs = [Organization.objects.get(id=org_id)]
                self.stdout.write(f"Processing single org: {org_id}")
            except Organization.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Organization {org_id} not found"))
                return
        else:
            orgs = list(Organization.objects.all())
            self.stdout.write(f"Processing {len(orgs)} organizations")

        total_stats = {
            "hourly": {"created": 0, "updated": 0},
            "daily": {"created": 0, "updated": 0},
            "monthly": {"created": 0, "updated": 0},
            "errors": 0,
        }

        for org in orgs:
            org_id_str = str(org.id)
            self.stdout.write(f"\nProcessing org: {org.display_name} ({org_id_str})")

            try:
                # Collect all metric data for this org
                hourly_data, daily_data, monthly_data = self._collect_metrics(
                    org_id_str, start_date, end_date
                )

                self.stdout.write(
                    f"  Collected: {len(hourly_data)} hourly, "
                    f"{len(daily_data)} daily, {len(monthly_data)} monthly records"
                )

                if not dry_run:
                    # Write to tables
                    if not skip_hourly:
                        h_created, h_updated = self._upsert_hourly(hourly_data)
                        total_stats["hourly"]["created"] += h_created
                        total_stats["hourly"]["updated"] += h_updated
                        self.stdout.write(
                            f"  Hourly: {h_created} created, {h_updated} updated"
                        )

                    if not skip_daily:
                        d_created, d_updated = self._upsert_daily(daily_data)
                        total_stats["daily"]["created"] += d_created
                        total_stats["daily"]["updated"] += d_updated
                        self.stdout.write(
                            f"  Daily: {d_created} created, {d_updated} updated"
                        )

                    if not skip_monthly:
                        m_created, m_updated = self._upsert_monthly(monthly_data)
                        total_stats["monthly"]["created"] += m_created
                        total_stats["monthly"]["updated"] += m_updated
                        self.stdout.write(
                            f"  Monthly: {m_created} created, {m_updated} updated"
                        )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"  Error processing org {org_id_str}: {e}")
                )
                total_stats["errors"] += 1
                logger.exception(f"Error backfilling org {org_id_str}")

        # Print summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("BACKFILL COMPLETE"))
        self.stdout.write(
            f"Hourly: {total_stats['hourly']['created']} created, "
            f"{total_stats['hourly']['updated']} updated"
        )
        self.stdout.write(
            f"Daily: {total_stats['daily']['created']} created, "
            f"{total_stats['daily']['updated']} updated"
        )
        self.stdout.write(
            f"Monthly: {total_stats['monthly']['created']} created, "
            f"{total_stats['monthly']['updated']} updated"
        )
        self.stdout.write(f"Errors: {total_stats['errors']}")

    def _collect_metrics(
        self, org_id: str, start_date: datetime, end_date: datetime
    ) -> tuple[dict, dict, dict]:
        """Collect metrics from source tables for all granularities."""
        hourly_agg = {}
        daily_agg = {}
        monthly_agg = {}

        for metric_name, query_method, is_histogram in self.METRIC_CONFIGS:
            metric_type = MetricType.HISTOGRAM if is_histogram else MetricType.COUNTER

            try:
                # Query hourly data
                hourly_results = query_method(
                    org_id, start_date, end_date, granularity="hour"
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
                    org_id, start_date, end_date, granularity="day"
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
                logger.warning(f"Error querying {metric_name} for org {org_id}: {e}")

        return hourly_agg, daily_agg, monthly_agg

    def _truncate_to_hour(self, ts: datetime) -> datetime:
        """Truncate datetime to hour."""
        if ts.tzinfo is None:
            ts = timezone.make_aware(ts, timezone.utc)
        return ts.replace(minute=0, second=0, microsecond=0)

    def _upsert_hourly(self, aggregations: dict) -> tuple[int, int]:
        """Upsert hourly aggregations."""
        created, updated = 0, 0
        for key, agg in aggregations.items():
            org_id, ts_str, metric_name, project, tag = key
            timestamp = datetime.fromisoformat(ts_str)

            try:
                obj, was_created = EventMetricsHourly._base_manager.update_or_create(
                    organization_id=org_id,
                    timestamp=timestamp,
                    metric_name=metric_name,
                    project=project,
                    tag=tag,
                    defaults={
                        "metric_type": agg["metric_type"],
                        "metric_value": agg["value"],
                        "metric_count": agg["count"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                logger.warning(f"Error upserting hourly {key}: {e}")

        return created, updated

    def _upsert_daily(self, aggregations: dict) -> tuple[int, int]:
        """Upsert daily aggregations."""
        created, updated = 0, 0
        for key, agg in aggregations.items():
            org_id, date_str, metric_name, project, tag = key
            date_val = datetime.fromisoformat(date_str).date()

            try:
                obj, was_created = EventMetricsDaily._base_manager.update_or_create(
                    organization_id=org_id,
                    date=date_val,
                    metric_name=metric_name,
                    project=project,
                    tag=tag,
                    defaults={
                        "metric_type": agg["metric_type"],
                        "metric_value": agg["value"],
                        "metric_count": agg["count"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                logger.warning(f"Error upserting daily {key}: {e}")

        return created, updated

    def _upsert_monthly(self, aggregations: dict) -> tuple[int, int]:
        """Upsert monthly aggregations."""
        created, updated = 0, 0
        for key, agg in aggregations.items():
            org_id, month_str, metric_name, project, tag = key
            month_val = datetime.fromisoformat(month_str).date()

            try:
                obj, was_created = EventMetricsMonthly._base_manager.update_or_create(
                    organization_id=org_id,
                    month=month_val,
                    metric_name=metric_name,
                    project=project,
                    tag=tag,
                    defaults={
                        "metric_type": agg["metric_type"],
                        "metric_value": agg["value"],
                        "metric_count": agg["count"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                logger.warning(f"Error upserting monthly {key}: {e}")

        return created, updated
