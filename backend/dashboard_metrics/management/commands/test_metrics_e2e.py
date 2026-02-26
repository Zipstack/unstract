"""E2E test for Dashboard Metrics pipeline.

Seeds synthetic source data, runs backfill, and validates API endpoints.
Does NOT require production database access — generates all data locally.

Usage:
    python manage.py test_metrics_e2e
    python manage.py test_metrics_e2e --days=30
    python manage.py test_metrics_e2e --cleanup
    python manage.py test_metrics_e2e --skip-seed --skip-api
"""

import random
import uuid
from datetime import timedelta

from account_v2.models import Organization
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from dashboard_metrics.models import (
    EventMetricsDaily,
    EventMetricsHourly,
    EventMetricsMonthly,
)

# Tag for identifying test data for cleanup
TEST_TAG = "e2e_test"


class Command(BaseCommand):
    help = "E2E test: seed source data, backfill metrics, validate API endpoints"

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=str,
            default=None,
            help="Organization ID to use (default: first org found)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Days of synthetic data to generate (default: 30)",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Remove test data and exit",
        )
        parser.add_argument(
            "--skip-seed",
            action="store_true",
            help="Skip seeding (use existing source data)",
        )
        parser.add_argument(
            "--skip-api",
            action="store_true",
            help="Skip API endpoint testing",
        )

    def handle(self, *args, **options):
        self.stdout.write("\n=== Metrics Dashboard E2E Test ===\n")

        # Resolve organization
        org = self._get_org(options.get("org_id"))
        if not org:
            self.stderr.write(self.style.ERROR("No organization found. Create one first."))
            return

        self.stdout.write(f"Organization: {org.display_name} (id={org.id})")
        org_id_str = str(org.id)

        if options["cleanup"]:
            self._cleanup(org)
            return

        days = options["days"]
        results = {"seed": None, "backfill": None, "api": None}

        # Step 1: Seed source data
        if not options["skip_seed"]:
            results["seed"] = self._seed_source_data(org, days)
        else:
            self.stdout.write(self.style.WARNING("\n[SEED] Skipped"))

        # Step 2: Run backfill
        self.stdout.write(f"\n[BACKFILL] Running backfill for last {days} days...")
        try:
            call_command(
                "backfill_metrics",
                days=days,
                org_id=org_id_str,
                verbosity=0,
            )
            hourly = EventMetricsHourly._base_manager.filter(
                organization=org
            ).count()
            daily = EventMetricsDaily._base_manager.filter(
                organization=org
            ).count()
            monthly = EventMetricsMonthly._base_manager.filter(
                organization=org
            ).count()
            self.stdout.write(
                f"  Hourly: {hourly} records, Daily: {daily} records, "
                f"Monthly: {monthly} records"
            )
            results["backfill"] = hourly > 0 and daily > 0 and monthly > 0
            if results["backfill"]:
                self.stdout.write(self.style.SUCCESS("  PASS"))
            else:
                self.stdout.write(self.style.ERROR("  FAIL — no records created"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"  FAIL — {e}"))
            results["backfill"] = False

        # Step 3: Test API endpoints
        if not options["skip_api"]:
            results["api"] = self._test_api_endpoints(org)
        else:
            self.stdout.write(self.style.WARNING("\n[API] Skipped"))

        # Summary
        self.stdout.write("\n" + "=" * 50)
        all_passed = all(v is not False for v in results.values() if v is not None)
        if all_passed:
            self.stdout.write(self.style.SUCCESS("=== ALL TESTS PASSED ==="))
        else:
            failed = [k for k, v in results.items() if v is False]
            self.stdout.write(self.style.ERROR(f"=== FAILED: {', '.join(failed)} ==="))

    def _get_org(self, org_id):
        """Resolve organization by ID or pick the first one."""
        if org_id:
            try:
                return Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                return None
        return Organization.objects.first()

    def _seed_source_data(self, org, days):
        """Seed synthetic source data into all source tables."""
        from account_usage.models import PageUsage
        from api_v2.models import APIDeployment
        from pipeline_v2.models import Pipeline
        from usage_v2.models import Usage
        from workflow_manager.file_execution.models import WorkflowFileExecution
        from workflow_manager.workflow_v2.models.execution import WorkflowExecution
        from workflow_manager.workflow_v2.models.workflow import Workflow

        self.stdout.write(f"\n[SEED] Creating synthetic data for last {days} days...")

        now = timezone.now()
        start = now - timedelta(days=days)
        org_id_str = str(org.id)

        # --- Workflows ---
        workflows = []
        for i in range(3):
            wf = Workflow._base_manager.create(
                workflow_name=f"E2E Test Workflow {i + 1}",
                organization=org,
                is_active=True,
            )
            workflows.append(wf)
        self.stdout.write(f"  Workflows: {len(workflows)} created")

        # --- Pipelines (1 ETL, 1 DEFAULT) ---
        pipeline_etl = Pipeline._base_manager.create(
            pipeline_name="E2E ETL",
            workflow=workflows[0],
            pipeline_type="ETL",
            organization=org,
        )
        pipeline_default = Pipeline._base_manager.create(
            pipeline_name="E2E Default",
            workflow=workflows[1],
            pipeline_type="DEFAULT",
            organization=org,
        )
        self.stdout.write("  Pipelines: 2 created (1 ETL, 1 DEFAULT)")

        # --- API Deployment ---
        api_deploy = APIDeployment._base_manager.create(
            display_name="E2E API",
            api_name="e2e-test-api",
            workflow=workflows[2],
            organization=org,
        )
        self.stdout.write("  API Deployments: 1 created")

        # --- Workflow Executions (80, spread over date range) ---
        executions = []
        pipeline_ids = [
            pipeline_etl.id,
            pipeline_default.id,
            api_deploy.id,
            None,
        ]
        statuses = ["COMPLETED"] * 7 + ["ERROR"] * 2 + ["PENDING"]

        for i in range(80):
            # Distribute timestamps across the date range
            offset_hours = random.uniform(0, days * 24)
            ts = start + timedelta(hours=offset_hours)
            wf = random.choice(workflows)
            pid = random.choice(pipeline_ids)
            status = random.choice(statuses)

            exe = WorkflowExecution._base_manager.create(
                workflow=wf,
                pipeline_id=pid,
                execution_mode="INSTANT",
                execution_method="DIRECT",
                execution_type="COMPLETE",
                status=status,
                total_files=random.randint(1, 10),
                execution_time=random.uniform(5, 120),
            )
            # Backdate created_at (auto_now_add prevents direct set)
            WorkflowExecution._base_manager.filter(pk=exe.pk).update(created_at=ts)
            executions.append(exe)

        self.stdout.write(f"  Workflow Executions: {len(executions)} created")

        # --- Workflow File Executions (120: 100 COMPLETED, 20 ERROR) ---
        file_execs = []
        file_statuses = ["COMPLETED"] * 100 + ["ERROR"] * 20

        for i, status in enumerate(file_statuses):
            exe = random.choice(executions)
            offset_hours = random.uniform(0, days * 24)
            ts = start + timedelta(hours=offset_hours)

            fe = WorkflowFileExecution._base_manager.create(
                workflow_execution=exe,
                file_name=f"test_doc_{i + 1}.pdf",
                status=status,
                mime_type="application/pdf",
                file_size=random.randint(10000, 5000000),
                execution_time=random.uniform(1, 30),
            )
            WorkflowFileExecution._base_manager.filter(pk=fe.pk).update(
                created_at=ts
            )
            file_execs.append(fe)

        completed_fe = [fe for fe, s in zip(file_execs, file_statuses, strict=False) if s == "COMPLETED"]
        error_fe = [fe for fe, s in zip(file_execs, file_statuses, strict=False) if s == "ERROR"]
        self.stdout.write(
            f"  File Executions: {len(file_execs)} created "
            f"({len(completed_fe)} COMPLETED, {len(error_fe)} ERROR)"
        )

        # --- Page Usage (120 records, linked to file executions) ---
        for i, fe in enumerate(file_execs):
            offset_hours = random.uniform(0, days * 24)
            ts = start + timedelta(hours=offset_hours)
            pages = random.randint(1, 50)

            pu = PageUsage.objects.create(
                organization_id=org_id_str,
                file_name=fe.file_name,
                file_type="application/pdf",
                run_id=str(fe.id),
                pages_processed=pages,
                file_size=random.randint(10000, 5000000),
            )
            PageUsage.objects.filter(pk=pu.pk).update(created_at=ts)

        self.stdout.write(f"  Page Usage: {len(file_execs)} created")

        # --- Usage records (200: llm type, mix of reasons) ---
        reasons = ["extraction"] * 12 + ["challenge"] * 4 + ["summarize"] * 4
        models_list = ["gpt-4", "gpt-3.5-turbo", "claude-3-sonnet", "llama-3"]

        for i in range(200):
            offset_hours = random.uniform(0, days * 24)
            ts = start + timedelta(hours=offset_hours)
            reason = random.choice(reasons)
            prompt_tok = random.randint(100, 5000)
            completion_tok = random.randint(50, 2000)

            u = Usage._base_manager.create(
                organization=org,
                workflow_id=str(random.choice(workflows).id),
                execution_id=str(random.choice(executions).id),
                adapter_instance_id=str(uuid.uuid4()),
                run_id=random.choice(file_execs).id,
                usage_type="llm",
                llm_usage_reason=reason,
                model_name=random.choice(models_list),
                embedding_tokens=0,
                prompt_tokens=prompt_tok,
                completion_tokens=completion_tok,
                total_tokens=prompt_tok + completion_tok,
                cost_in_dollars=round(random.uniform(0.001, 0.5), 4),
            )
            Usage._base_manager.filter(pk=u.pk).update(created_at=ts)

        self.stdout.write("  Usage: 200 created")

        self.stdout.write(self.style.SUCCESS("  SEED COMPLETE"))
        return True

    def _test_api_endpoints(self, org):
        """Test API endpoints via direct view invocation (bypasses auth)."""
        self.stdout.write("\n[API] Testing endpoints via service layer...")

        from dashboard_metrics.services import MetricsQueryService

        org_id_str = str(org.id)
        now = timezone.now()
        start = now - timedelta(days=7)

        tests = {
            "documents_processed": MetricsQueryService.get_documents_processed,
            "pages_processed": MetricsQueryService.get_pages_processed,
            "llm_calls": MetricsQueryService.get_llm_calls,
            "challenges": MetricsQueryService.get_challenges,
            "llm_usage_cost": MetricsQueryService.get_llm_usage_cost,
            "deployed_api_requests": MetricsQueryService.get_deployed_api_requests,
            "etl_pipeline_executions": MetricsQueryService.get_etl_pipeline_executions,
            "prompt_executions": MetricsQueryService.get_prompt_executions,
            "failed_pages": MetricsQueryService.get_failed_pages,
        }

        all_passed = True
        for name, query_fn in tests.items():
            try:
                results = query_fn(org_id_str, start, now, granularity="day")
                has_data = len(results) > 0
                total = sum(r.get("value", 0) or 0 for r in results)
                if has_data:
                    label = self.style.SUCCESS("PASS")
                    self.stdout.write(f"  {name}: {label} ({len(results)} buckets, total={total})")
                else:
                    label = self.style.WARNING("WARN")
                    self.stdout.write(f"  {name}: {label} (no data)")
            except Exception as e:
                label = self.style.ERROR("FAIL")
                self.stdout.write(f"  {name}: {label} — {e}")
                all_passed = False

        # Also verify aggregated tables have data
        self.stdout.write("\n  Aggregated table counts:")
        for model, label in [
            (EventMetricsHourly, "Hourly"),
            (EventMetricsDaily, "Daily"),
            (EventMetricsMonthly, "Monthly"),
        ]:
            count = model._base_manager.filter(organization=org).count()
            metrics = (
                model._base_manager.filter(organization=org)
                .values_list("metric_name", flat=True)
                .distinct()
            )
            self.stdout.write(f"    {label}: {count} records, {len(metrics)} metric types")

        return all_passed

    def _cleanup(self, org):
        """Remove all test data created by seed."""
        from account_usage.models import PageUsage
        from api_v2.models import APIDeployment
        from pipeline_v2.models import Pipeline
        from usage_v2.models import Usage
        from workflow_manager.file_execution.models import WorkflowFileExecution
        from workflow_manager.workflow_v2.models.execution import WorkflowExecution
        from workflow_manager.workflow_v2.models.workflow import Workflow

        self.stdout.write("\n[CLEANUP] Removing test data...")

        org_id_str = str(org.id)

        # Find test workflows by name pattern
        test_wfs = Workflow._base_manager.filter(
            organization=org,
            workflow_name__startswith="E2E Test Workflow",
        )
        wf_ids = list(test_wfs.values_list("id", flat=True))

        if not wf_ids:
            self.stdout.write("  No test data found.")
            return

        # Delete in reverse FK order
        # File executions
        fe_count = WorkflowFileExecution._base_manager.filter(
            workflow_execution__workflow_id__in=wf_ids
        ).delete()[0]
        self.stdout.write(f"  WorkflowFileExecution: {fe_count} deleted")

        # Workflow executions
        we_count = WorkflowExecution._base_manager.filter(
            workflow_id__in=wf_ids
        ).delete()[0]
        self.stdout.write(f"  WorkflowExecution: {we_count} deleted")

        # API deployments
        api_count = APIDeployment._base_manager.filter(
            organization=org,
            display_name__startswith="E2E ",
        ).delete()[0]
        self.stdout.write(f"  APIDeployment: {api_count} deleted")

        # Pipelines
        pipe_count = Pipeline._base_manager.filter(
            organization=org,
            pipeline_name__startswith="E2E ",
        ).delete()[0]
        self.stdout.write(f"  Pipeline: {pipe_count} deleted")

        # Page usage (by org)
        pu_count = PageUsage.objects.filter(
            organization_id=org_id_str,
            file_name__startswith="test_doc_",
        ).delete()[0]
        self.stdout.write(f"  PageUsage: {pu_count} deleted")

        # Usage (harder to filter — clean by workflows)
        usage_count = Usage._base_manager.filter(
            organization=org,
            workflow_id__in=[str(wid) for wid in wf_ids],
        ).delete()[0]
        self.stdout.write(f"  Usage: {usage_count} deleted")

        # Workflows
        wf_count = test_wfs.delete()[0]
        self.stdout.write(f"  Workflow: {wf_count} deleted")

        # Metrics tables
        h = EventMetricsHourly._base_manager.filter(organization=org).delete()[0]
        d = EventMetricsDaily._base_manager.filter(organization=org).delete()[0]
        m = EventMetricsMonthly._base_manager.filter(organization=org).delete()[0]
        self.stdout.write(f"  Metrics: {h} hourly, {d} daily, {m} monthly deleted")

        self.stdout.write(self.style.SUCCESS("  CLEANUP COMPLETE"))
