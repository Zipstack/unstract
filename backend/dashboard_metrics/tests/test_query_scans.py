"""UN-4672: documents_processed stops scanning other orgs' rows.

It is read for every active org in one grouped query per run, not one query per org.
The rows must be exactly what the per-org query returns.

DB-backed Django ``TestCase`` → auto-marked ``integration`` by ``backend/conftest.py``.
"""

import uuid
from datetime import timedelta
from unittest import mock

from account_v2.models import Organization
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics import tasks
from dashboard_metrics.models import EventMetricsDaily, EventMetricsHourly, Granularity
from dashboard_metrics.services import MetricsQueryService

COMPLETED = ExecutionStatus.COMPLETED.value
ERROR = ExecutionStatus.ERROR.value


class _Seed:
    def setUp(self) -> None:
        self.now = timezone.now().replace(microsecond=0)
        self.org_a = self._org("a")
        self.org_b = self._org("b")

    def _org(self, suffix: str) -> Organization:
        tag = f"{suffix}-{uuid.uuid4().hex[:6]}"
        return Organization.objects.create(
            organization_id=f"org-{tag}", name=tag, display_name=tag
        )

    def _workflow(self, org: Organization) -> Workflow:
        return Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:6]}", organization=org
        )

    def _execution(self, workflow: Workflow, hours_ago: float) -> WorkflowExecution:
        execution = WorkflowExecution.objects.create(workflow=workflow, status=COMPLETED)
        WorkflowExecution.objects.filter(pk=execution.pk).update(
            created_at=self.now - timedelta(hours=hours_ago)
        )
        return execution

    def _file(
        self, execution: WorkflowExecution, hours_ago: float, status: str = COMPLETED
    ) -> WorkflowFileExecution:
        file_execution = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name=f"{uuid.uuid4().hex[:6]}.pdf",
            status=status,
        )
        WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
            created_at=self.now - timedelta(hours=hours_ago)
        )
        return file_execution


class DocumentsProcessedByOrgTests(_Seed, TestCase):
    def setUp(self) -> None:
        super().setUp()
        # Two orgs with completed files in several hours and days, plus rows each
        # filter must drop: another status, and outside the window.
        for org, hours in ((self.org_a, (1, 1, 3, 30)), (self.org_b, (2, 26, 27))):
            workflow = self._workflow(org)
            for h in hours:
                self._file(self._execution(workflow, h + 0.5), h)
            self._file(self._execution(workflow, 1.5), 1, status=ERROR)
            self._file(self._execution(workflow, 100), 99)

    def _org_ids(self) -> list[str]:
        return [str(self.org_a.id), str(self.org_b.id)]

    def test_matches_the_per_org_query_at_every_granularity(self) -> None:
        start = self.now - timedelta(days=2)
        for granularity in (Granularity.HOUR, Granularity.DAY, Granularity.WEEK):
            with self.subTest(granularity=granularity):
                by_org = MetricsQueryService.get_documents_processed_by_org(
                    self._org_ids(), start, self.now, granularity=granularity
                )
                for org_id in self._org_ids():
                    expected = MetricsQueryService.get_documents_processed(
                        org_id, start, self.now, granularity=granularity
                    )
                    self.assertTrue(expected, "fixture must give each org rows")
                    self.assertEqual(by_org.get(org_id, []), expected)

    def test_leaves_out_orgs_not_asked_for(self) -> None:
        by_org = MetricsQueryService.get_documents_processed_by_org(
            [str(self.org_a.id)], self.now - timedelta(days=2), self.now
        )
        self.assertEqual(set(by_org), {str(self.org_a.id)})

    def test_no_orgs_issues_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(
                MetricsQueryService.get_documents_processed_by_org(
                    [], self.now - timedelta(days=2), self.now
                ),
                {},
            )

    def _stored_documents(self) -> dict[str, set]:
        return {
            "hourly": set(
                EventMetricsHourly._base_manager.filter(
                    metric_name="documents_processed"
                ).values_list("organization_id", "timestamp", "metric_value")
            ),
            "daily": set(
                EventMetricsDaily._base_manager.filter(
                    metric_name="documents_processed"
                ).values_list("organization_id", "date", "metric_value")
            ),
        }

    def _run(self) -> dict[str, set]:
        with mock.patch("dashboard_metrics.tasks.timezone.now", return_value=self.now):
            tasks._run_aggregation(tasks.AggregationTier.ALL)
        return self._stored_documents()

    def test_aggregation_queries_documents_once_per_granularity(self) -> None:
        with (
            mock.patch.object(
                MetricsQueryService,
                "get_documents_processed",
                wraps=MetricsQueryService.get_documents_processed,
            ) as per_org,
            mock.patch.object(
                MetricsQueryService,
                "get_documents_processed_by_org",
                wraps=MetricsQueryService.get_documents_processed_by_org,
            ) as cross_org,
        ):
            stored = self._run()
        per_org.assert_not_called()
        self.assertEqual(
            sorted(c.kwargs["granularity"] for c in cross_org.call_args_list),
            sorted([Granularity.HOUR, Granularity.DAY]),
        )
        self.assertTrue(stored["hourly"] and stored["daily"])

    def test_aggregation_writes_what_the_per_org_path_writes(self) -> None:
        cross_org = self._run()
        EventMetricsHourly._base_manager.all().delete()
        EventMetricsDaily._base_manager.all().delete()
        with mock.patch.object(tasks, "_prefetch_cross_org_metrics", return_value={}):
            per_org = self._run()
        self.assertEqual(cross_org, per_org)

    def test_a_failed_prefetch_falls_back_to_the_per_org_queries(self) -> None:
        expected = self._run()
        EventMetricsHourly._base_manager.all().delete()
        EventMetricsDaily._base_manager.all().delete()
        with mock.patch.object(
            MetricsQueryService,
            "get_documents_processed_by_org",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(self._run(), expected)

    def test_a_database_error_in_the_prefetch_does_not_abort_the_run(self) -> None:
        # Inside a request transaction (DJANGO_ATOMIC_REQUESTS) a failed statement
        # aborts the transaction; the fallback must still be able to query.
        expected = self._run()
        EventMetricsHourly._base_manager.all().delete()
        EventMetricsDaily._base_manager.all().delete()

        def fail_in_the_database(*_args, **_kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0")

        with mock.patch.object(
            MetricsQueryService,
            "get_documents_processed_by_org",
            side_effect=fail_in_the_database,
        ):
            self.assertEqual(self._run(), expected)
