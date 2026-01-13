"""Management command to populate test metrics data for dashboard testing."""

import random
from datetime import datetime, timedelta

from account_v2.models import Organization
from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    MetricType,
)
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    """Populate test metrics data for dashboard testing."""

    help = "Populate test metrics data for dashboard testing"

    # Metric definitions matching MetricName enum
    METRICS = [
        ("documents_processed", MetricType.COUNTER),
        ("pages_processed", MetricType.COUNTER),
        ("prompt_executions", MetricType.COUNTER),
        ("llm_calls", MetricType.COUNTER),
        ("challenges", MetricType.COUNTER),
        ("summarization_calls", MetricType.COUNTER),
        ("deployed_api_requests", MetricType.HISTOGRAM),
        ("etl_pipeline_executions", MetricType.HISTOGRAM),
        ("llm_usage", MetricType.HISTOGRAM),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=str,
            help="Organization ID to populate data for. If not specified, uses first org.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days of data to generate (default: 30)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing metrics data before populating",
        )

    def handle(self, *args, **options):
        org_id = options.get("org_id")
        days = options["days"]
        clear = options["clear"]

        # Get organization
        if org_id:
            try:
                org = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                raise CommandError(f"Organization with ID {org_id} not found")
        else:
            org = Organization.objects.first()
            if not org:
                raise CommandError("No organizations found. Create one first.")

        self.stdout.write(f"Using organization: {org.display_name} ({org.id})")

        # Clear existing data if requested
        if clear:
            self.stdout.write("Clearing existing metrics data...")
            EventMetricsHourly.objects.filter(organization=org).delete()
            EventMetricsDaily.objects.filter(organization=org).delete()
            self.stdout.write(self.style.SUCCESS("Cleared existing data"))

        # Generate data
        self.stdout.write(f"Generating {days} days of test metrics data...")

        now = timezone.now()
        hourly_records = []
        daily_records = []

        for day_offset in range(days):
            current_date = (now - timedelta(days=day_offset)).date()

            for metric_name, metric_type in self.METRICS:
                # Generate daily aggregate
                daily_value = self._generate_value(metric_name, metric_type)
                daily_count = random.randint(10, 100)

                daily_records.append(
                    EventMetricsDaily(
                        organization=org,
                        date=current_date,
                        metric_name=metric_name,
                        metric_type=metric_type,
                        metric_value=daily_value,
                        metric_count=daily_count,
                        labels=self._generate_labels(metric_name),
                        project="default",
                        tag="",
                    )
                )

                # Generate hourly data for recent days only (last 7 days)
                if day_offset < 7:
                    for hour in range(24):
                        timestamp = datetime.combine(
                            current_date, datetime.min.time()
                        ).replace(hour=hour, tzinfo=timezone.utc)

                        hourly_value = self._generate_value(
                            metric_name, metric_type, scale=0.1
                        )
                        hourly_count = random.randint(1, 20)

                        hourly_records.append(
                            EventMetricsHourly(
                                organization=org,
                                timestamp=timestamp,
                                metric_name=metric_name,
                                metric_type=metric_type,
                                metric_value=hourly_value,
                                metric_count=hourly_count,
                                labels=self._generate_labels(metric_name),
                                project="default",
                                tag="",
                            )
                        )

        # Bulk create records
        self.stdout.write("Inserting daily records...")
        EventMetricsDaily.objects.bulk_create(
            daily_records,
            ignore_conflicts=True,
        )
        self.stdout.write(f"  Created {len(daily_records)} daily records")

        self.stdout.write("Inserting hourly records...")
        EventMetricsHourly.objects.bulk_create(
            hourly_records,
            ignore_conflicts=True,
        )
        self.stdout.write(f"  Created {len(hourly_records)} hourly records")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully populated test metrics data for {org.display_name}"
            )
        )

    def _generate_value(self, metric_name, metric_type, scale=1.0):
        """Generate a realistic value based on metric type."""
        if metric_type == MetricType.COUNTER:
            # Counter metrics - integer counts
            base_values = {
                "documents_processed": (50, 500),
                "pages_processed": (200, 2000),
                "prompt_executions": (100, 1000),
                "llm_calls": (200, 2000),
                "challenges": (10, 100),
                "summarization_calls": (20, 200),
            }
            min_val, max_val = base_values.get(metric_name, (10, 100))
            return int(random.randint(min_val, max_val) * scale)
        else:
            # Histogram metrics - can be floats (cost, latency)
            if metric_name == "llm_usage":
                # Cost in dollars
                return round(random.uniform(0.5, 50.0) * scale, 2)
            elif metric_name == "deployed_api_requests":
                return int(random.randint(100, 1000) * scale)
            elif metric_name == "etl_pipeline_executions":
                return int(random.randint(10, 100) * scale)
            return int(random.randint(10, 100) * scale)

    def _generate_labels(self, metric_name):
        """Generate sample labels for a metric."""
        labels = {}

        if metric_name in ["llm_calls", "llm_usage"]:
            labels["model"] = random.choice(
                ["gpt-4", "gpt-3.5-turbo", "claude-3-opus", "claude-3-sonnet"]
            )
            labels["provider"] = random.choice(["openai", "anthropic"])

        if metric_name == "documents_processed":
            labels["doc_type"] = random.choice(["pdf", "docx", "xlsx", "txt"])

        if metric_name in ["deployed_api_requests", "etl_pipeline_executions"]:
            labels["status"] = random.choice(["success", "success", "success", "error"])

        return labels
