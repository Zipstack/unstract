"""Backend unit tests for the PG finalization-strand fixes.

- L1: ``update_status`` terminal-one-way guard (PG rows, keyed on queue_message_id)
  — a non-terminal write cannot clobber an already-terminal execution.
- L4: ``recover_stuck_pg_executions`` — recompute the correct terminal status from
  files, skip file-less (possibly-still-queued) execs, and never touch Celery rows.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.db import transaction
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


class ModelStaleWriterGuardTests(TestCase):
    """The terminal-one-way guard at the MODEL layer (update_execution) — where the
    HTTP-endpoint guard can't reach. A stale backend object (created EXECUTING, NULL
    counters, re-saved after the callback set COMPLETED) must not revert a
    protected-terminal (COMPLETED/STOPPED) PG execution back to EXECUTING+NULL."""

    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-stale")

    def _stale(self, ex, status, **fields):
        """A separate in-memory instance of ex with stale field values."""
        stale = WorkflowExecution.objects.get(pk=ex.pk)
        stale.status = status.value
        for k, v in fields.items():
            setattr(stale, k, v)
        return stale

    def test_pg_refuses_stale_revert_of_completed(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=11,
            total_files=1,
            successful_files=1,
            failed_files=0,
        )
        stale = self._stale(
            ex, ExecutionStatus.EXECUTING, successful_files=None, failed_files=None
        )
        stale.update_execution(status=ExecutionStatus.EXECUTING)  # the clobber
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # not reverted
        assert ex.successful_files == 1  # counters not nulled

    def test_pg_refuses_stale_revert_of_stopped(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.STOPPED,
            queue_message_id=12,
            total_files=2,
            successful_files=1,
            failed_files=1,
        )
        self._stale(
            ex, ExecutionStatus.EXECUTING, successful_files=None, failed_files=None
        ).update_execution(status=ExecutionStatus.EXECUTING)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.STOPPED.value
        assert ex.successful_files == 1 and ex.failed_files == 1  # counters preserved

    def test_pg_same_status_does_not_clobber_counters(self):
        # Same-status COMPLETED→COMPLETED: the guard is a no-op, so update_fields must
        # be what stops the stale NULL counters from clobbering the real ones.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=17,
            total_files=1,
            successful_files=1,
            failed_files=0,
        )
        self._stale(
            ex, ExecutionStatus.COMPLETED, successful_files=None, failed_files=None
        ).update_execution(status=ExecutionStatus.COMPLETED)
        ex.refresh_from_db()
        assert ex.successful_files == 1  # not nulled

    def test_pg_stale_null_marker_still_guarded_and_not_nulled(self):
        # A stale object whose in-memory queue_message_id is None (snapshotted before
        # dispatch recorded it) must STILL be guarded (routing reads the persisted
        # marker) AND the marker must not be nulled by the write.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=99,
            successful_files=1,
        )
        self._stale(
            ex, ExecutionStatus.EXECUTING, queue_message_id=None, successful_files=None
        ).update_execution(status=ExecutionStatus.EXECUTING)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # still guarded
        assert ex.queue_message_id == 99  # marker NOT nulled
        assert ex.successful_files == 1

    def test_pg_refused_status_still_applies_error_and_attempt(self):
        # The refused status must NOT silently drop error / increment_attempt.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=16,
            attempts=0,
        )
        self._stale(ex, ExecutionStatus.EXECUTING).update_execution(
            status=ExecutionStatus.EXECUTING,
            error="late failure",
            increment_attempt=True,
        )
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # status refused
        assert ex.error_message == "late failure"  # error applied
        assert ex.attempts == 1  # increment applied

    def test_service_helper_update_execution_is_guarded(self):
        from workflow_manager.workflow_v2.execution import (
            WorkflowExecutionServiceHelper,
        )

        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=18
        )
        helper = WorkflowExecutionServiceHelper.__new__(WorkflowExecutionServiceHelper)
        helper.execution_id = str(ex.id)
        helper.update_execution(status=ExecutionStatus.EXECUTING)  # delegates → guarded
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_update_execution_err_is_guarded(self):
        from workflow_manager.workflow_v2.execution import (
            WorkflowExecutionServiceHelper,
        )

        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=19
        )
        WorkflowExecutionServiceHelper.update_execution_err(str(ex.id), "late error")
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value  # COMPLETED not reverted

    def test_pg_allows_error_corrected_to_completed(self):
        # ERROR is not protected — a premature ERROR must stay correctable.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.ERROR, queue_message_id=13
        )
        WorkflowExecution.objects.get(pk=ex.pk).update_execution(
            status=ExecutionStatus.COMPLETED
        )
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_pg_allows_idempotent_completed_rewrite(self):
        ex = WorkflowExecution.objects.create(
            workflow=self.wf, status=ExecutionStatus.COMPLETED, queue_message_id=14
        )
        WorkflowExecution.objects.get(pk=ex.pk).update_execution(
            status=ExecutionStatus.COMPLETED
        )
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_celery_row_unaffected(self):
        # queue_message_id NULL → legacy behavior, the stale write goes through.
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=None,
            task_id=uuid.uuid4(),
        )
        self._stale(ex, ExecutionStatus.EXECUTING).update_execution(
            status=ExecutionStatus.EXECUTING
        )
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value  # legacy: overwritten

    def test_result_acknowledge_does_not_touch_status_or_counters(self):
        # A stale object acknowledging a result must not rewrite status/counters
        # (update_fields scoping).
        from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.COMPLETED,
            queue_message_id=15,
            total_files=1,
            successful_files=1,
            failed_files=0,
            result_acknowledged=False,
        )
        stale = self._stale(
            ex, ExecutionStatus.EXECUTING, successful_files=None, failed_files=None
        )
        WorkflowHelper._set_result_acknowledge(stale)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value
        assert ex.successful_files == 1
        assert ex.result_acknowledged is True
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


class RateLimitReleaseOnCommitTests(TestCase):
    """The API-deployment rate-limit slot must be released only once the status
    write is DURABLE.

    ``update_execution()`` schedules the release via ``transaction.on_commit`` so a
    caller's OUTER-transaction rollback — ``update_status``'s file-aggregate write
    failing, or the PG reaper's ``_recover_one_stuck_pg_execution`` — can no longer
    free the slot while leaving the status un-persisted (the P1 flagged in review).

    Covers BOTH transports: the release path is shared, so this asserts the Celery
    (``queue_message_id`` NULL) happy path is unchanged — the slot still frees on
    commit — and the PG path behaves identically.
    """

    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-ratelimit")

    def _exec(self, pg):
        # pipeline_id set → an API-deployment execution that holds a rate-limit slot.
        return WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.EXECUTING.value,
            pipeline_id=uuid.uuid4(),
            queue_message_id=123 if pg else None,
            task_id=None if pg else uuid.uuid4(),
        )

    @patch.object(WorkflowExecution, "_release_api_deployment_rate_limit")
    def test_celery_path_release_fires_on_commit(self, release):
        # Regression guard for the existing Celery flow: reaching a terminal status
        # still releases the slot — just on commit rather than mid-transaction.
        ex = self._exec(pg=False)
        with self.captureOnCommitCallbacks(execute=True):
            ex.update_execution(status=ExecutionStatus.COMPLETED)
        release.assert_called_once()

    @patch.object(WorkflowExecution, "_release_api_deployment_rate_limit")
    def test_pg_path_release_fires_on_commit(self, release):
        ex = self._exec(pg=True)
        with self.captureOnCommitCallbacks(execute=True):
            ex.update_execution(status=ExecutionStatus.COMPLETED)
        release.assert_called_once()

    @patch.object(WorkflowExecution, "_release_api_deployment_rate_limit")
    def test_release_suppressed_when_outer_txn_rolls_back(self, release):
        # The fix: an outer transaction that rolls back AFTER the status write must
        # NOT leak the slot. Before on_commit, the Redis release fired inline and
        # survived the rollback (freed slot + un-persisted status).
        ex = self._exec(pg=False)
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    ex.update_execution(status=ExecutionStatus.COMPLETED)
                    raise RuntimeError("outer txn fails after the status write")
            except RuntimeError:
                pass
        release.assert_not_called()
        # And the status write rolled back with it — the execution is still recoverable.
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value

    @patch.object(WorkflowExecution, "_release_api_deployment_rate_limit")
    def test_non_terminal_status_never_releases(self, release):
        # No slot is released for a non-terminal transition, on commit or otherwise.
        ex = self._exec(pg=False)
        with self.captureOnCommitCallbacks(execute=True):
            ex.update_execution(status=ExecutionStatus.EXECUTING)
        release.assert_not_called()
