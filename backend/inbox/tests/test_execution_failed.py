"""Failed runs put one item in the inboxes of the owners of what ran."""

from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, TransactionTestCase
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
from workflow_manager.workflow_v2.models import WorkflowExecution

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
        self.finish(execution, ExecutionStatus.ERROR)
        for user in (self.owner, self.coowner):
            (item,) = _items(user)
            self.assertEqual(item.kind, InboxItem.Kind.EXECUTION_FAILED)
            self.assertIn(pipeline.pipeline_name, item.title)
            self.assertEqual(item.route, _run_route(execution))
        self.assertEqual(_items(self.viewer), [])
        self.assertEqual(_items(self.outsider), [])

    def test_completed_with_failed_files_counts_as_failed(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        self.finish(self.run_of(pipeline), ExecutionStatus.COMPLETED, failed_files=2)
        (item,) = _items(self.owner)
        self.assertIn("2", item.title)

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

    def test_one_item_per_execution(self) -> None:
        pipeline = _build_pipeline(self.org, self.owner)
        self.share(pipeline)
        execution = self.run_of(pipeline)
        self.finish(execution, ExecutionStatus.ERROR)
        self.finish(execution, ExecutionStatus.COMPLETED, failed_files=1)
        self.assertEqual(len(_items(self.owner)), 1)

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
