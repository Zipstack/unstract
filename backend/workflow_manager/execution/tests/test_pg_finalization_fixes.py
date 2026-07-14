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

    def test_pg_rejects_non_completed_write_over_completed(self):
        # PG execution (queue_message_id set) → guard active regardless of any flag.
        # A stale non-terminal write must not clobber the callback's COMPLETED (the
        # strand bug).
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.EXECUTING)
        ex.refresh_from_db()
        assert out.get("reason") == "already_final"
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

    def test_pg_rejects_error_write_over_completed(self):
        # COMPLETED→ERROR is the genuinely confusing/wrong flip (a success suddenly
        # shows failed) and never happens legitimately (COMPLETED is only ever set by
        # a successful callback, whose redelivery is skipped). Must be rejected.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.ERROR)
        ex.refresh_from_db()
        assert out.get("reason") == "already_final"
        assert ex.status == ExecutionStatus.COMPLETED.value  # success protected

    def test_pg_allows_error_corrected_to_completed(self):
        # ERROR is NOT final — a premature ERROR (upstream error / external stop /
        # reaper) set before the first real callback must be correctable to COMPLETED
        # when the files actually succeeded. Blocking this would freeze a successful
        # run at a wrong ERROR.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.ERROR, queue_message_id=123
        )
        self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # correction allowed

    def test_pg_rejects_completed_over_stopped(self):
        # STOPPED is an explicit user/operator stop — a straggler callback that
        # finishes after the stop must not silently erase it back to COMPLETED.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.STOPPED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert out.get("reason") == "already_final"
        assert ex.status == ExecutionStatus.STOPPED.value  # user stop preserved

    def test_pg_allows_idempotent_completed_rewrite(self):
        # COMPLETED→SAME COMPLETED is a no-op rewrite and must still be allowed (a
        # duplicate/redelivered callback re-writing its own COMPLETED).
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=123
        )
        out = self._update(ex, ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert out.get("status") == "updated"
        assert ex.status == ExecutionStatus.COMPLETED.value


class RetrieveNotFoundTests(TestCase):
    """A missing execution must return 404, not 500 (UN-3719). The reaper's
    orphan-claim sweep relies on the deterministic 404 to GC claims for deleted
    executions; a 500 made it retry forever and never clean them up."""

    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-retrieve")
        self.view = WorkflowExecutionInternalViewSet()

    def test_retrieve_returns_404_for_missing_execution(self):
        from django.http import Http404

        req = MagicMock()
        req.GET = {}
        # get_object() raises Http404 for a missing row; the id genuinely doesn't
        # exist (unscoped) → 404 so the reaper GC's the orphan claim.
        with patch.object(self.view, "get_object", side_effect=Http404("not found")):
            resp = self.view.retrieve(req, id=str(uuid.uuid4()))
        assert resp.status_code == 404
        assert resp.data.get("error") == "WorkflowExecution not found"

    def test_retrieve_returns_500_when_execution_exists_but_scoped_out(self):
        # get_object() is org-scoped, so an Http404 can mean "exists but scoped out"
        # (or a nested Http404). The row DOES exist (unscoped) → 500, so the reaper
        # retains the claim instead of GC-ing a live execution's recovery handle.
        from django.http import Http404

        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.EXECUTING, queue_message_id=7
        )
        req = MagicMock()
        req.GET = {}
        with patch.object(self.view, "get_object", side_effect=Http404("scoped out")):
            resp = self.view.retrieve(req, id=str(ex.id))
        assert resp.status_code == 500
