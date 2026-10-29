"""Stuck executions: the ``stuck=true`` list filter and ``stuck-count/`` (UN-4318)."""

from datetime import timedelta
from typing import Any

from django.test import override_settings
from django.utils.dateparse import parse_datetime
from pipeline_v2.models import Pipeline

from workflow_manager.execution.stuck import count_stuck
from workflow_manager.execution.tests.stuck_abort_base import (
    OLD,
    RECENT,
    StuckAbortTestBase,
)
from workflow_manager.execution.views import ExecutionViewSet, StuckExecutionCountView
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

_list = ExecutionViewSet.as_view({"get": "list"})
_count = StuckExecutionCountView.as_view()


class StuckExecutionTests(StuckAbortTestBase):
    def _stuck_rows(self, user: Any) -> dict[str, Any]:
        response = self.call(_list, user, data={"stuck": "true"})
        self.assertEqual(response.status_code, 200)
        return {row["id"]: row for row in response.data["results"]}

    def _count(self, user: Any) -> dict[str, Any]:
        response = self.call(_count, user)
        self.assertEqual(response.status_code, 200)
        data: dict[str, Any] = response.data
        return data

    def test_stuck_run_is_listed_with_stuck_since_and_counted(self) -> None:
        execution = self.execution()
        latest = self.file(
            execution, ExecutionStatus.EXECUTING, idle=OLD - timedelta(minutes=10)
        )
        self.file(execution, ExecutionStatus.COMPLETED, idle=OLD)

        rows = self._stuck_rows(self.owner)

        self.assertEqual(list(rows), [str(execution.id)])
        stuck_since = parse_datetime(rows[str(execution.id)]["stuck_since"])
        self.assertEqual(stuck_since, latest.modified_at)
        self.assertEqual(
            self._count(self.owner),
            {
                "threshold_seconds": 9000,
                "total": 1,
                "counts": {"API": 0, "ETL": 0, "TASK": 0, "WF": 1},
            },
        )

    def test_run_without_files_is_stuck_since_its_own_last_write(self) -> None:
        execution = self.execution(status=ExecutionStatus.PENDING)
        rows = self._stuck_rows(self.owner)
        self.assertEqual(
            parse_datetime(rows[str(execution.id)]["stuck_since"]),
            execution.modified_at,
        )

    def test_recent_file_activity_is_not_stuck(self) -> None:
        execution = self.execution()
        self.file(execution, ExecutionStatus.EXECUTING, idle=RECENT)
        self.assertEqual(self._stuck_rows(self.owner), {})
        self.assertEqual(self._count(self.owner)["total"], 0)

    def test_recently_updated_run_is_not_stuck(self) -> None:
        self.execution(idle=RECENT)
        self.assertEqual(self._stuck_rows(self.owner), {})

    def test_finished_runs_are_not_stuck(self) -> None:
        for status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ERROR,
            ExecutionStatus.STOPPED,
        ):
            self.execution(status=status)
        self.assertEqual(self._stuck_rows(self.owner), {})
        self.assertEqual(self._count(self.owner)["total"], 0)

    def test_runs_the_caller_cannot_see_are_excluded(self) -> None:
        self.execution(self.deployment())
        self.assertEqual(self._stuck_rows(self.outsider), {})
        self.assertEqual(self._count(self.outsider)["total"], 0)
        # Control: the owner does see it.
        self.assertEqual(self._count(self.owner)["total"], 1)

    def test_counts_split_by_entity(self) -> None:
        self.execution(self.deployment())
        self.execution(self.pipeline(Pipeline.PipelineType.ETL))
        self.execution(self.pipeline(Pipeline.PipelineType.ETL))
        self.execution(self.pipeline(Pipeline.PipelineType.TASK))
        self.execution()

        report = self._count(self.owner)

        self.assertEqual(report["total"], 5)
        self.assertEqual(report["counts"], {"API": 1, "ETL": 2, "TASK": 1, "WF": 1})

    def test_count_is_one_query(self) -> None:
        self.execution(self.deployment())
        self.execution()
        with self.assertNumQueries(1):
            report = count_stuck(WorkflowExecution.objects.all())
        self.assertEqual(report.total, 2)
        self.assertEqual(report.counts["API"], 1)

    def test_stuck_combines_with_the_entity_filter(self) -> None:
        api_run = self.execution(self.deployment())
        self.execution()
        response = self.call(
            _list, self.owner, data={"stuck": "true", "execution_entity": "API"}
        )
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(api_run.id)])

    @override_settings(STUCK_EXECUTION_THRESHOLD_SECONDS=30)
    def test_threshold_comes_from_settings(self) -> None:
        execution = self.execution(idle=RECENT)
        self.assertIn(str(execution.id), self._stuck_rows(self.owner))
        report = self._count(self.owner)
        self.assertEqual(report["threshold_seconds"], 30)
        self.assertEqual(report["total"], 1)

    def test_count_requires_authentication(self) -> None:
        request = self.factory.get("/")
        response = _count(request)
        self.assertIn(response.status_code, (401, 403))
