"""Failed runs put one item in the inboxes of the owners of what ran."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from permissions.roles import ResourceRole
from permissions.tests.base import (
    CoOwnerOrgTestMixin,
    _build_api_deployment,
    _build_pipeline,
    _build_workflow,
)
from utils.user_context import UserContext
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

from inbox.models import InboxItem


def _items(user) -> list[InboxItem]:
    return list(InboxItem.objects.filter(user=user))


def _run_route(execution) -> dict:
    return {"key": "execution.detail", "params": {"id": str(execution.pk)}}


class _Runs(CoOwnerOrgTestMixin):
    def setUp(self) -> None:
        self._seed_org()
        self.addCleanup(UserContext.set_organization_identifier, None)

    def share(self, resource) -> None:
        resource.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        resource.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        resource.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)

    def run_of(self, resource=None, workflow=None) -> WorkflowExecution:
        return WorkflowExecution.objects.create(
            workflow=workflow or resource.workflow,
            pipeline_id=resource.pk if resource else None,
            status=ExecutionStatus.EXECUTING.value,
        )

    def finish(self, execution, status, failed_files=None) -> None:
        # As the worker's update_status does: status and counts in one transaction.
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                execution.update_execution(status=status)
                if failed_files is not None:
                    execution.failed_files = failed_files
                    execution.save(update_fields=["failed_files"])


class ExecutionFailedTests(_Runs, TestCase):
    def test_pipeline_error_notifies_owners_and_co_owners_only(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        execution.error_message = "boom"
        self.finish(execution, ExecutionStatus.ERROR)
        for user in (self.owner, self.coowner):
            (item,) = _items(user)
            self.assertEqual(item.kind, InboxItem.Kind.EXECUTION_FAILED)
            self.assertEqual(
                item.title, f"A run of the pipeline {pipeline.pipeline_name} failed"
            )
            self.assertEqual(item.body, "boom")
            self.assertEqual(item.route, _run_route(execution))
        self.assertEqual(_items(self.viewer), [])
        self.assertEqual(_items(self.outsider), [])

    def test_completed_with_failed_files_counts_as_failed(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        self.finish(self.run_of(pipeline), ExecutionStatus.COMPLETED, failed_files=2)
        (item,) = _items(self.owner)
        self.assertEqual(
            item.title,
            f"A run of the pipeline {pipeline.pipeline_name} finished with 2 failed files",
        )

    def test_clean_run_creates_nothing(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        self.finish(self.run_of(pipeline), ExecutionStatus.COMPLETED, failed_files=0)
        self.assertEqual(_items(self.owner), [])

    def test_non_terminal_status_creates_nothing(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        with patch("inbox.events.notify_execution_failed") as hook:
            self.finish(self.run_of(pipeline), ExecutionStatus.EXECUTING)
        hook.assert_not_called()

    def test_repeated_failures_refresh_one_item_per_resource(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        first, second = self.run_of(pipeline), self.run_of(pipeline)
        self.finish(first, ExecutionStatus.ERROR)
        earlier = timezone.now() - timedelta(days=1)
        InboxItem.objects.filter(user=self.owner).update(
            read_at=timezone.now(), created_at=earlier
        )
        self.finish(second, ExecutionStatus.ERROR)
        (item,) = _items(self.owner)
        self.assertEqual(item.route, _run_route(second))
        self.assertIsNone(item.read_at)
        self.assertGreater(item.created_at, earlier)

    def test_clean_retry_of_an_older_run_keeps_the_newer_failure(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        first, second = self.run_of(pipeline), self.run_of(pipeline)
        self.finish(first, ExecutionStatus.ERROR)
        self.finish(second, ExecutionStatus.ERROR)
        self.finish(first, ExecutionStatus.COMPLETED, failed_files=0)
        (item,) = _items(self.owner)
        self.assertEqual(item.route, _run_route(second))

    def test_same_run_failing_again_leaves_a_read_item_read(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        self.finish(execution, ExecutionStatus.ERROR)
        InboxItem.objects.filter(user=self.owner).update(read_at=timezone.now())
        self.finish(execution, ExecutionStatus.ERROR)
        self.assertIsNotNone(_items(self.owner)[0].read_at)

    def test_late_failure_of_an_older_run_keeps_the_newer_one(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        older, newer = self.run_of(pipeline), self.run_of(pipeline)
        WorkflowExecution.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        older.refresh_from_db()
        self.finish(newer, ExecutionStatus.ERROR)
        self.finish(older, ExecutionStatus.ERROR)
        (item,) = _items(self.owner)
        self.assertEqual(item.route, _run_route(newer))

    def test_workflow_without_an_organization_is_skipped(self) -> None:
        workflow = _build_workflow(self.org, self.owner)
        self.share(workflow)
        Workflow.objects.filter(pk=workflow.pk).update(organization=None)
        with self.assertLogs("inbox.events", "WARNING"):
            self.finish(self.run_of(workflow=workflow), ExecutionStatus.ERROR)
        self.assertFalse(InboxItem._base_manager.exists())

    def test_one_item_per_execution(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        self.finish(execution, ExecutionStatus.ERROR)
        self.finish(execution, ExecutionStatus.COMPLETED, failed_files=1)
        self.assertEqual(len(_items(self.owner)), 1)

    def test_error_corrected_to_a_clean_run_withdraws_the_item(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        self.finish(execution, ExecutionStatus.ERROR)
        self.finish(execution, ExecutionStatus.COMPLETED, failed_files=0)
        self.assertEqual(_items(self.owner), [])

    def test_error_restarted_then_clean_withdraws_the_item(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        self.finish(execution, ExecutionStatus.ERROR)
        self.finish(execution, ExecutionStatus.EXECUTING)
        self.finish(execution, ExecutionStatus.COMPLETED, failed_files=0)
        self.assertEqual(_items(self.owner), [])

    def test_pg_transport_run_is_notified(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        WorkflowExecution.objects.filter(pk=execution.pk).update(queue_message_id=1)
        execution.refresh_from_db()
        self.finish(execution, ExecutionStatus.ERROR)
        self.assertEqual(len(_items(self.owner)), 1)

    def test_failed_run_does_not_push_over_the_socket(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        with patch("inbox.service._submit") as submit:
            self.finish(self.run_of(pipeline), ExecutionStatus.ERROR)
        submit.assert_not_called()
        self.assertEqual(len(_items(self.owner)), 1)

    def test_stopped_run_says_stopped(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        self.finish(self.run_of(pipeline), ExecutionStatus.STOPPED)
        (item,) = _items(self.owner)
        self.assertIn("was stopped", item.title)

    def test_run_of_a_deleted_pipeline_falls_back_to_the_workflow(self) -> None:
        workflow = _build_workflow(self.org, self.owner)
        self.share(workflow)
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            pipeline_id=uuid.uuid4(),
            status=ExecutionStatus.EXECUTING.value,
        )
        self.finish(execution, ExecutionStatus.ERROR)
        (item,) = _items(self.owner)
        self.assertIn(workflow.workflow_name, item.title)

    def test_api_deployment_run_notifies_its_owners(self) -> None:
        api = _build_api_deployment(self.org, self.owner)
        self.share(api)
        execution = self.run_of(api)
        self.finish(execution, ExecutionStatus.ERROR)
        (item,) = _items(self.coowner)
        self.assertIn(api.api_name, item.title)
        self.assertEqual(item.route, _run_route(execution))

    def test_workflow_run_notifies_workflow_owners(self) -> None:
        workflow = _build_workflow(self.org, self.owner)
        self.share(workflow)
        execution = self.run_of(workflow=workflow)
        self.finish(execution, ExecutionStatus.ERROR)
        (item,) = _items(self.owner)
        self.assertIn(workflow.workflow_name, item.title)
        self.assertEqual(item.route, _run_route(execution))

    def test_organization_comes_from_the_workflow_not_the_request(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        UserContext.set_organization_identifier(None)
        self.finish(execution, ExecutionStatus.ERROR)
        UserContext.set_organization_identifier(self.org.organization_id)
        (item,) = _items(self.owner)
        self.assertEqual(item.organization, self.org)

    def test_inbox_failure_does_not_fail_the_status_update(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        with patch("inbox.events.notify", side_effect=RuntimeError("boom")):
            with self.assertLogs("inbox.events", "ERROR"):
                self.finish(execution, ExecutionStatus.ERROR)
        execution.refresh_from_db()
        self.assertEqual(execution.status, ExecutionStatus.ERROR.value)


class RealCommitTests(_Runs, TransactionTestCase):
    """Real commits: TestCase defers on-commit hooks past every write."""

    def test_run_finished_with_nothing_to_dispatch_and_rejected_files(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        WorkflowExecutionServiceHelper.update_execution_completed(
            str(execution.pk), total_files=3, failed_files=3
        )
        self.assertEqual(len(_items(self.owner)), 1)


class LockTests(_Runs, TestCase):
    def test_both_paths_serialise_on_the_item(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        for status in (ExecutionStatus.ERROR, ExecutionStatus.COMPLETED):
            with self.subTest(status=status):
                with CaptureQueriesContext(connection) as queries:
                    self.finish(execution, status, failed_files=0)
                sql = " ".join(q["sql"] for q in queries.captured_queries)
                self.assertIn("pg_advisory_xact_lock", sql)
