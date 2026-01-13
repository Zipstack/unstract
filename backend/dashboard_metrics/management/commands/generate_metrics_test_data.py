"""Generate test data for dashboard metrics testing.

This command creates realistic test data in source tables that the
aggregate_metrics_from_sources task will use to populate EventMetricsHourly.

Usage:
    python manage.py generate_metrics_test_data --org-id=12 --days=7
"""

import random
import uuid
from datetime import timedelta

from account_usage.models import PageUsage
from account_v2.models import Organization
from django.core.management.base import BaseCommand
from django.utils import timezone
from usage_v2.models import LLMUsageReason, Usage, UsageType
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow


class Command(BaseCommand):
    help = "Generate test data for dashboard metrics testing"

    # Sample data templates based on staging data
    MODEL_NAMES = [
        "azure/gpt-4o-mini",
        "azure/gpt-4o",
    ]

    FILE_NAMES = [
        "invoice_001.pdf",
        "contract_v2.pdf",
        "report_2024.pdf",
        "statement_jan.pdf",
        "receipt_12345.pdf",
        "agreement_final.pdf",
    ]

    FILE_TYPES = [
        "application/pdf",
    ]

    # Error messages matching staging patterns
    EXECUTION_ERRORS = [
        "Workflow execution failed: timeout exceeded",
        "Error processing file: invalid format",
        "LLM API error: rate limit exceeded",
        "Connection timeout to external service",
        "File extraction failed: corrupted document",
    ]

    FILE_EXECUTION_ERRORS = [
        "Failed to extract text from document",
        "OCR processing error: image quality too low",
        "Unsupported file format encountered",
        "File size exceeds maximum limit",
        "Document parsing failed: malformed PDF",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=str,
            default=None,
            help="Organization ID to use (must exist)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days of historical data to generate",
        )
        parser.add_argument(
            "--records-per-day",
            type=int,
            default=15,
            help="Average records per day per table",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Remove existing test data before generating",
        )

    def handle(self, *args, **options):
        org_id = options["org_id"]
        days = options["days"]
        records_per_day = options["records_per_day"]
        clean = options["clean"]

        # Get organization
        if org_id:
            try:
                org = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"Organization with id={org_id} not found")
                )
                self.stdout.write("Available organizations:")
                for o in Organization.objects.all()[:10]:
                    self.stdout.write(f"  - {o.id}: {o.display_name}")
                return
        else:
            # Use first available organization
            org = Organization.objects.first()
            if not org:
                self.stderr.write(
                    self.style.ERROR("No organizations found. Create one first.")
                )
                return

        org_id_str = str(org.id)
        self.stdout.write(f"Using organization: {org.display_name} (id={org_id_str})")

        # Get or create a test workflow for this org
        workflow = self._get_or_create_workflow(org)
        self.stdout.write(f"Using workflow: {workflow.workflow_name} (id={workflow.id})")

        if clean:
            self._clean_test_data(org_id_str, workflow)

        # Calculate time range
        end_time = timezone.now()
        start_time = end_time - timedelta(days=days)

        # Generate data
        total_records = days * records_per_day

        self.stdout.write(
            f"\nGenerating {total_records} records per table over {days} days..."
        )

        # 1. Generate WorkflowExecution records
        executions = self._generate_workflow_executions(
            workflow, start_time, end_time, total_records
        )
        self.stdout.write(
            self.style.SUCCESS(f"  Created {len(executions)} WorkflowExecution records")
        )

        # 2. Generate WorkflowFileExecution records (linked to executions)
        file_executions = self._generate_file_executions(executions, start_time, end_time)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Created {len(file_executions)} WorkflowFileExecution records"
            )
        )

        # 3. Generate Usage records
        usage_records = self._generate_usage_records(
            org, executions, start_time, end_time, total_records
        )
        self.stdout.write(
            self.style.SUCCESS(f"  Created {len(usage_records)} Usage records")
        )

        # 4. Generate PageUsage records
        page_usage_records = self._generate_page_usage_records(
            org_id_str, start_time, end_time, total_records
        )
        self.stdout.write(
            self.style.SUCCESS(f"  Created {len(page_usage_records)} PageUsage records")
        )

        self.stdout.write(
            self.style.SUCCESS(
                "\nTest data generation complete!"
                '\nNow run: python manage.py shell -c "'
                "from dashboard_metrics.tasks import aggregate_metrics_from_sources; "
                'print(aggregate_metrics_from_sources())"'
            )
        )

    def _get_or_create_workflow(self, org: Organization) -> Workflow:
        """Get existing workflow or create a test workflow.

        Uses _base_manager to bypass DefaultOrganizationManagerMixin filter
        which returns None in shell/Celery context.
        """
        # Try to find an existing workflow (use _base_manager to bypass org filter)
        workflow = Workflow._base_manager.filter(organization=org).first()
        if workflow:
            return workflow

        # Create a test workflow - use _base_manager for create too
        workflow = Workflow(
            organization=org,
            workflow_name="Test Workflow for Metrics",
            description="Auto-generated workflow for metrics testing",
            is_active=True,
            deployment_type=Workflow.WorkflowType.DEFAULT,
        )
        workflow.save()
        return workflow

    def _clean_test_data(self, org_id_str: str, workflow: Workflow):
        """Remove existing test data."""
        self.stdout.write("Cleaning existing test data...")

        # Delete file executions first (FK constraint)
        file_exec_count = WorkflowFileExecution.objects.filter(
            workflow_execution__workflow=workflow
        ).count()
        WorkflowFileExecution.objects.filter(
            workflow_execution__workflow=workflow
        ).delete()

        # Delete workflow executions
        exec_count = WorkflowExecution.objects.filter(workflow=workflow).count()
        WorkflowExecution.objects.filter(workflow=workflow).delete()

        # Delete usage records
        usage_count = Usage.objects.filter(organization_id=org_id_str).count()
        Usage.objects.filter(organization_id=org_id_str).delete()

        # Delete page usage records
        page_count = PageUsage.objects.filter(organization_id=org_id_str).count()
        PageUsage.objects.filter(organization_id=org_id_str).delete()

        self.stdout.write(
            f"  Deleted: {exec_count} executions, {file_exec_count} file executions, "
            f"{usage_count} usage, {page_count} page usage"
        )

    def _random_timestamp(self, start_time, end_time):
        """Generate a random timestamp between start and end."""
        delta = end_time - start_time
        random_seconds = random.randint(0, int(delta.total_seconds()))
        return start_time + timedelta(seconds=random_seconds)

    def _generate_workflow_executions(
        self, workflow: Workflow, start_time, end_time, count: int
    ) -> list[WorkflowExecution]:
        """Generate WorkflowExecution records."""
        executions = []
        for _ in range(count):
            created_at = self._random_timestamp(start_time, end_time)

            # 90% completed, 10% error (matching staging ratio)
            is_error = random.random() >= 0.9
            status = ExecutionStatus.ERROR if is_error else ExecutionStatus.COMPLETED
            error_message = random.choice(self.EXECUTION_ERRORS) if is_error else ""

            exec_obj = WorkflowExecution(
                workflow=workflow,
                execution_mode=random.choice(
                    [WorkflowExecution.Mode.INSTANT, WorkflowExecution.Mode.QUEUE]
                ),
                execution_method=random.choice(
                    [WorkflowExecution.Method.DIRECT, WorkflowExecution.Method.SCHEDULED]
                ),
                execution_type=WorkflowExecution.Type.COMPLETE,
                status=status,
                total_files=random.randint(1, 10),
                execution_time=random.uniform(5.0, 120.0),
                error_message=error_message,
            )
            exec_obj._target_created_at = created_at  # Store target timestamp
            executions.append(exec_obj)

        # Bulk create
        WorkflowExecution.objects.bulk_create(executions)

        # Refresh to get IDs (needed since bulk_create may not return them)
        created_executions = list(
            WorkflowExecution.objects.filter(workflow=workflow).order_by("-id")[:count]
        )

        # Update created_at timestamps (auto_now_add overrides during bulk_create)
        for i, exec_obj in enumerate(created_executions):
            target_ts = executions[i]._target_created_at if i < len(executions) else None
            if target_ts:
                WorkflowExecution.objects.filter(id=exec_obj.id).update(
                    created_at=target_ts
                )
                exec_obj.created_at = target_ts  # Update in-memory object too

        return created_executions

    def _generate_file_executions(
        self, executions: list[WorkflowExecution], start_time, end_time
    ) -> list[WorkflowFileExecution]:
        """Generate WorkflowFileExecution records linked to executions."""
        file_executions = []

        for exec_obj in executions:
            # 1-3 files per execution
            num_files = random.randint(1, 3)

            for i in range(num_files):
                # Use execution's created_at as base
                created_at = exec_obj.created_at + timedelta(seconds=i * 10)

                # 90% completed, 10% error (matching staging ratio)
                is_error = random.random() >= 0.9
                status = ExecutionStatus.ERROR if is_error else ExecutionStatus.COMPLETED
                execution_error = (
                    random.choice(self.FILE_EXECUTION_ERRORS) if is_error else None
                )

                file_exec = WorkflowFileExecution(
                    workflow_execution=exec_obj,
                    file_name=random.choice(self.FILE_NAMES),
                    file_path=f"/uploads/{uuid.uuid4()}/{random.choice(self.FILE_NAMES)}",
                    file_size=random.randint(100000, 5000000),
                    file_hash=uuid.uuid4().hex,
                    mime_type="application/pdf",
                    status=status,
                    execution_time=random.uniform(5.0, 60.0),
                    execution_error=execution_error,
                )
                file_exec._target_created_at = created_at  # Store target timestamp
                file_executions.append(file_exec)

        WorkflowFileExecution.objects.bulk_create(file_executions)

        # Update created_at timestamps (auto_now_add overrides during bulk_create)
        for file_exec in file_executions:
            WorkflowFileExecution.objects.filter(id=file_exec.id).update(
                created_at=file_exec._target_created_at
            )

        return file_executions

    def _generate_usage_records(
        self,
        org: Organization,
        executions: list[WorkflowExecution],
        start_time,
        end_time,
        count: int,
    ) -> list[Usage]:
        """Generate Usage records for LLM calls."""
        usage_records = []

        # Distribute across reasons: 70% extraction, 20% challenge, 10% summarize
        reason_weights = [
            (LLMUsageReason.EXTRACTION, 0.7),
            (LLMUsageReason.CHALLENGE, 0.2),
            (LLMUsageReason.SUMMARIZE, 0.1),
        ]

        for _ in range(count):
            created_at = self._random_timestamp(start_time, end_time)

            # Pick a reason based on weights
            rand = random.random()
            cumulative = 0
            reason = LLMUsageReason.EXTRACTION
            for r, weight in reason_weights:
                cumulative += weight
                if rand < cumulative:
                    reason = r
                    break

            # Random execution (for linking)
            exec_obj = random.choice(executions) if executions else None

            # Token ranges matching staging data
            prompt_tokens = random.randint(1000, 5000)
            completion_tokens = random.randint(100, 500)
            total_tokens = prompt_tokens + completion_tokens

            # Cost range matching staging: 0.001 - 0.05
            cost = random.uniform(0.001, 0.05)

            usage = Usage(
                organization=org,
                workflow_id=str(exec_obj.workflow_id) if exec_obj else None,
                execution_id=str(exec_obj.id) if exec_obj else None,
                adapter_instance_id=str(uuid.uuid4()),
                run_id=uuid.uuid4(),
                usage_type=UsageType.LLM,
                llm_usage_reason=reason,
                model_name=random.choice(self.MODEL_NAMES),
                embedding_tokens=0,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_in_dollars=round(cost, 6),
            )
            usage._target_created_at = created_at  # Store target timestamp
            usage_records.append(usage)

        Usage.objects.bulk_create(usage_records)

        # Update created_at timestamps (since auto_now_add overrides during bulk_create)
        for usage in usage_records:
            Usage.objects.filter(id=usage.id).update(created_at=usage._target_created_at)

        return usage_records

    def _generate_page_usage_records(
        self, org_id_str: str, start_time, end_time, count: int
    ) -> list[PageUsage]:
        """Generate PageUsage records."""
        page_records = []

        for _ in range(count):
            created_at = self._random_timestamp(start_time, end_time)

            page_usage = PageUsage(
                organization_id=org_id_str,
                file_name=random.choice(self.FILE_NAMES),
                file_type=random.choice(self.FILE_TYPES),
                run_id=str(uuid.uuid4()),
                pages_processed=random.randint(5, 50),  # Matching staging range
                file_size=random.randint(100000, 5000000),
            )
            # Note: created_at is auto_now_add, so we need to update it after creation
            page_records.append(page_usage)

        PageUsage.objects.bulk_create(page_records)

        # Update created_at timestamps (since auto_now_add won't let us set it directly)
        page_ids = [p.id for p in page_records]
        for i, page_id in enumerate(page_ids):
            created_at = self._random_timestamp(start_time, end_time)
            PageUsage.objects.filter(id=page_id).update(created_at=created_at)

        return page_records
