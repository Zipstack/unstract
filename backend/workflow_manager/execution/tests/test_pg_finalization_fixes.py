"""Backend unit tests for the PG finalization-strand fixes.

- L1: ``update_status`` terminal-one-way guard (flag-gated) — a non-terminal write
  cannot clobber an already-terminal execution.
- L4: ``recover_stuck_pg_executions`` — recompute the correct terminal status from
  files, mark never-dispatched (file-less) stuck execs ERROR, and never touch
  Celery rows.
- N+1: ``active_file_executions`` — one batched dedup query.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_FLAG = "workflow_manager.internal_views.check_feature_flag_status"


def _age(execution, seconds):
    """Backdate modified_at (auto_now) via a direct UPDATE that bypasses auto_now."""
    WorkflowExecution.objects.filter(pk=execution.pk).update(
        modified_at=timezone.now() - timedelta(seconds=seconds)
    )


class RecoverStuckPgExecutionsTests(TestCase):
    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-recover")
        self.view = WorkflowExecutionInternalViewSet()

    def _exec(self, status, pg=True, files=()):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=status,
            queue_message_id=123 if pg else None,
            task_id=None if pg else uuid.uuid4(),
        )
        for fstatus in files:
            WorkflowFileExecution.objects.create(
                workflow_execution=ex, file_name="f", status=fstatus.value
            )
        return ex

    def _call(self, stuck_seconds=60):
        req = MagicMock()
        req.data = {"stuck_seconds": stuck_seconds, "limit": 100}
        return self.view.recover_stuck_pg_executions(req).data

    def test_all_files_completed_recovers_to_completed(self):
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["recovered"] == 1
        assert ex.status == ExecutionStatus.COMPLETED.value
        assert ex.successful_files == 1 and ex.failed_files == 0

    def test_any_file_error_recovers_to_error(self):
        ex = self._exec(
            ExecutionStatus.EXECUTING,
            files=[ExecutionStatus.COMPLETED, ExecutionStatus.ERROR],
        )
        _age(ex, 9999)
        self._call()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.ERROR.value
        assert ex.failed_files == 1 and ex.successful_files == 1

    def test_file_less_stuck_marked_error(self):
        ex = self._exec(ExecutionStatus.PENDING, files=[])
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["recovered"] == 1
        assert ex.status == ExecutionStatus.ERROR.value

    def test_celery_execution_never_scanned(self):
        ex = self._exec(
            ExecutionStatus.EXECUTING, pg=False, files=[ExecutionStatus.COMPLETED]
        )
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["scanned"] == 0  # queue_message_id IS NULL → PG filter excludes it
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_still_processing_is_skipped(self):
        ex = self._exec(
            ExecutionStatus.EXECUTING,
            files=[ExecutionStatus.COMPLETED, ExecutionStatus.EXECUTING],
        )
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["skipped"] == 1
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_recently_modified_not_recovered(self):
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        out = self._call(stuck_seconds=9000)  # exec's modified_at is fresh → past cutoff
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value


class ActiveFileExecutionsTests(TestCase):
    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-dedup")
        self.view = WorkflowExecutionInternalViewSet()

    def _mapping(self):
        req = MagicMock()
        req.query_params = {"workflow_id": str(self.wf.id)}
        return self.view.active_file_executions(req).data["file_executions"]

    def test_returns_only_active_execution_files_in_skip_statuses(self):
        active = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.EXECUTING
        )
        WorkflowFileExecution.objects.create(
            workflow_execution=active,
            file_name="a",
            status=ExecutionStatus.EXECUTING.value,
            provider_file_uuid="uuid-a",
        )
        # A terminal execution's files must NOT appear (not active).
        done = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED
        )
        WorkflowFileExecution.objects.create(
            workflow_execution=done,
            file_name="b",
            status=ExecutionStatus.EXECUTING.value,
            provider_file_uuid="uuid-b",
        )
        assert self._mapping() == {"uuid-a": ExecutionStatus.EXECUTING.value}


class TerminalOneWayGuardTests(TestCase):
    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-guard")
        self.view = WorkflowExecutionInternalViewSet()

    def _update(self, ex, new_status, flag_on):
        req = MagicMock()
        req.data = {"status": new_status.value}
        with patch.object(self.view, "get_object", return_value=ex), patch(
            _FLAG, return_value=flag_on
        ):
            return self.view.update_status(req, id=str(ex.id)).data

    def test_flag_on_rejects_non_terminal_write_over_terminal(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED
        )
        out = self._update(ex, ExecutionStatus.EXECUTING, flag_on=True)
        ex.refresh_from_db()
        assert out.get("reason") == "already_terminal"
        assert ex.status == ExecutionStatus.COMPLETED.value  # not clobbered

    def test_flag_off_keeps_legacy_behavior(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED
        )
        self._update(ex, ExecutionStatus.EXECUTING, flag_on=False)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value  # legacy: overwritten

    def test_flag_on_allows_terminal_write(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.EXECUTING
        )
        self._update(ex, ExecutionStatus.COMPLETED, flag_on=True)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # terminal write allowed
