"""Abort on real transactions: the row lock and one commit per id (UN-4318)."""

import threading
from typing import Any
from unittest.mock import patch

from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.db import transaction
from django.test import TransactionTestCase
from permissions.roles import ResourceRole
from platform_audit.models import PlatformAuditEvent
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.tests import _make_user
from utils.user_context import UserContext

from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.execution.tests import test_update_status_locking as locking
from workflow_manager.execution.views import ExecutionAbortView
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_ABORT = "workflow_manager.execution.abort"
_abort = ExecutionAbortView.as_view()


class AbortTransactionTests(TransactionTestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.owner = _make_user("owner@example.com")
        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)

    def _execution(self, pipeline_id: Any = None) -> WorkflowExecution:
        execution: WorkflowExecution = WorkflowExecution.objects.create(
            workflow=self.workflow,
            pipeline_id=pipeline_id,
            execution_mode=WorkflowExecution.Mode.QUEUE,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.EXECUTING.value,
            queue_message_id=1,
        )
        return execution

    def _post(self, *ids: Any) -> dict[str, tuple[str, str | None]]:
        body = {"ids": [str(i) for i in ids]}
        request = APIRequestFactory().post("/", body, format="json")
        force_authenticate(request, user=self.owner)
        response = _abort(request)
        response.render()
        self.assertEqual(response.status_code, 200, response.data)
        return {r["id"]: (r["outcome"], r["status"]) for r in response.data["results"]}

    def _status(self, execution: WorkflowExecution) -> str:
        execution.refresh_from_db()
        status: str = execution.status
        return status

    def test_abort_outside_any_transaction_succeeds(self) -> None:
        execution = self._execution()
        self.assertEqual(
            self._post(execution.id), {str(execution.id): ("aborted", "STOPPED")}
        )
        self.assertEqual(self._status(execution), ExecutionStatus.STOPPED.value)

    def test_a_failure_part_way_keeps_the_others_and_rolls_back_its_own(self) -> None:
        first, bad, last = self._execution(), self._execution(), self._execution()

        def stop(execution: WorkflowExecution) -> None:
            if execution.pk == bad.pk:
                raise RuntimeError("boom")

        with (
            patch(f"{_ABORT}._stop_open_files", side_effect=stop),
            patch(f"{_ABORT}._report_abort") as report,
        ):
            outcomes = self._post(first.id, bad.id, last.id)

        self.assertEqual(
            outcomes,
            {
                str(first.id): ("aborted", "STOPPED"),
                str(bad.id): ("failed", None),
                str(last.id): ("aborted", "STOPPED"),
            },
        )
        self.assertEqual(self._status(first), ExecutionStatus.STOPPED.value)
        self.assertEqual(self._status(bad), ExecutionStatus.EXECUTING.value)
        self.assertEqual(self._status(last), ExecutionStatus.STOPPED.value)
        self.assertEqual(PlatformAuditEvent.objects.count(), 2)
        self.assertEqual(report.call_count, 2)

    def test_a_rolled_back_abort_leaves_the_stored_status_cached(self) -> None:
        execution = self._execution()

        with patch(f"{_ABORT}._stop_open_files", side_effect=RuntimeError("boom")):
            outcomes = self._post(execution.id)

        self.assertEqual(outcomes, {str(execution.id): ("failed", None)})
        cached = ExecutionCacheUtils.get_execution(
            workflow_id=str(self.workflow.id), execution_id=str(execution.id)
        )
        self.assertEqual(getattr(cached, "status", None), ExecutionStatus.EXECUTING)

    def test_a_failing_report_keeps_the_abort_and_its_audit_event(self) -> None:
        deployment = APIDeployment.objects.create(
            api_name="api-1",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
        )
        deployment.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        execution = self._execution(deployment.id)

        with (
            patch(
                f"{_ABORT}.APIDeploymentUtils.send_notification",
                side_effect=RuntimeError("boom"),
            ) as send,
            self.assertLogs(_ABORT, level="ERROR") as logs,
        ):
            outcomes = self._post(execution.id)

        send.assert_called_once()
        self.assertIn(str(execution.id), logs.output[0])
        self.assertEqual(outcomes, {str(execution.id): ("aborted", "STOPPED")})
        self.assertEqual(self._status(execution), ExecutionStatus.STOPPED.value)
        self.assertEqual(PlatformAuditEvent.objects.count(), 1)

    def test_a_run_finishing_during_the_abort_is_not_overwritten(self) -> None:
        execution = self._execution()
        locked, release = threading.Event(), threading.Event()
        concurrent: Any = locking.ConcurrentStatusWriteTests

        def finish_the_run() -> None:
            with transaction.atomic():
                WorkflowExecution.objects.select_for_update().get(pk=execution.pk)
                locked.set()
                release.wait(locking.WAIT_SECONDS)
                WorkflowExecution.objects.filter(pk=execution.pk).update(
                    status=ExecutionStatus.COMPLETED.value
                )

        def abort() -> dict[str, tuple[str, str | None]]:
            UserContext.set_organization_identifier(self.org.organization_id)
            return self._post(execution.id)

        holder, _ = concurrent._run(finish_the_run)
        self.assertTrue(locked.wait(locking.WAIT_SECONDS))
        thread, box = concurrent._run(abort)
        concurrent._wait_until_a_backend_waits_on_a_lock(thread, box)
        release.set()
        holder.join(locking.WAIT_SECONDS)
        thread.join(locking.WAIT_SECONDS)

        self.assertFalse(thread.is_alive())
        self.assertEqual(
            box.get("result"), {str(execution.id): ("already_finished", "COMPLETED")}
        )
        self.assertEqual(self._status(execution), ExecutionStatus.COMPLETED.value)
        self.assertFalse(PlatformAuditEvent.objects.exists())
