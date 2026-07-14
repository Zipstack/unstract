"""Backend unit tests for the PG finalization-strand fixes.

- L1: ``update_status`` terminal-one-way guard (PG rows, keyed on queue_message_id)
  — a non-terminal write cannot clobber an already-terminal execution.
- L4: ``recover_stuck_pg_executions`` — recompute the correct terminal status from
  files, skip file-less (possibly-still-queued) execs, and never touch Celery rows.
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

    def test_stopped_files_recover_to_stopped_not_error(self):
        # A cancelled run (STOPPED files, no errors) must not be turned into ERROR.
        ex = self._exec(
            ExecutionStatus.EXECUTING,
            files=[ExecutionStatus.COMPLETED, ExecutionStatus.STOPPED],
        )
        _age(ex, 9999)
        self._call()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.STOPPED.value
        assert ex.failed_files == 0 and ex.successful_files == 1

    def test_error_takes_priority_over_stopped(self):
        ex = self._exec(
            ExecutionStatus.EXECUTING,
            files=[ExecutionStatus.ERROR, ExecutionStatus.STOPPED],
        )
        _age(ex, 9999)
        self._call()
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.ERROR.value

    def test_negative_stuck_seconds_does_not_match_live_execution(self):
        # A negative stuck_seconds must be clamped so the cutoff can't move into the
        # future and finalize currently-running work.
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        out = self._call(stuck_seconds=-100000)
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_file_less_stuck_is_skipped_not_failed(self):
        # A file-less PG exec may still be QUEUED (a backlog/outage can outlast the
        # stuck window) — it must NOT be failed, so a delayed worker can still
        # finalize it (the one-way guard would otherwise block recovery).
        ex = self._exec(ExecutionStatus.PENDING, files=[])
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["skipped"] == 1
        assert ex.status == ExecutionStatus.PENDING.value

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




class TerminalOneWayGuardTests(TestCase):
    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-guard")
        self.view = WorkflowExecutionInternalViewSet()

    def _update(self, ex, new_status):
        req = MagicMock()
        req.data = {"status": new_status.value}
        with patch.object(self.view, "get_object", return_value=ex):
            return self.view.update_status(req, id=str(ex.id)).data

    def test_pg_rejects_non_terminal_write_over_terminal(self):
        # PG execution (queue_message_id set) → guard active regardless of any flag.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.EXECUTING)
        ex.refresh_from_db()
        assert out.get("reason") == "already_terminal"
        assert ex.status == ExecutionStatus.COMPLETED.value  # not clobbered

    def test_celery_keeps_legacy_behavior(self):
        # No queue_message_id → not a PG execution → legacy (unguarded) path.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=None,
            task_id=uuid.uuid4(),
        )
        self._update(ex, ExecutionStatus.EXECUTING)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value  # legacy: overwritten

    def test_pg_allows_terminal_write(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.EXECUTING, queue_message_id=123
        )
        self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # terminal write allowed

    def test_pg_rejects_different_terminal_over_terminal(self):
        # terminal→a DIFFERENT terminal must be rejected too — a late ERROR callback
        # must not overwrite an earlier COMPLETED (final status stays deterministic,
        # not commit-order dependent).
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.ERROR)
        ex.refresh_from_db()
        assert out.get("reason") == "already_terminal"
        assert ex.status == ExecutionStatus.COMPLETED.value  # first terminal wins

    def test_pg_late_completed_does_not_erase_stopped_abort(self):
        # A user's STOPPED abort must survive a late COMPLETED from a file that
        # finished after the abort.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.STOPPED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert out.get("reason") == "already_terminal"
        assert ex.status == ExecutionStatus.STOPPED.value  # abort preserved

    def test_pg_allows_idempotent_same_terminal_rewrite(self):
        # terminal→SAME terminal is a no-op rewrite and must still be allowed (a
        # duplicate/redelivered callback re-writing its own COMPLETED).
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert out.get("status") == "updated"
        assert ex.status == ExecutionStatus.COMPLETED.value
