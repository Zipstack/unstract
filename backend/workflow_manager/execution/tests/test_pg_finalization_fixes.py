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
    """Backdate modified_at (auto_now) via a direct UPDATE that bypasses auto_now.

    Ages the FILE rows too, because that is where ``recover_stuck_pg_executions``
    measures staleness: the execution row's ``modified_at`` is effectively its start
    time (file completions write the file row, not the execution row), so ageing only
    the execution would describe a run that started long ago and finished a moment
    ago — a live execution mid-callback, which the endpoint must NOT touch. A real
    strand has quiet files, and that is what this reproduces. Tests that specifically
    need the two timestamps to diverge override the file rows after calling this.
    """
    stale = timezone.now() - timedelta(seconds=seconds)
    WorkflowExecution.objects.filter(pk=execution.pk).update(modified_at=stale)
    WorkflowFileExecution.objects.filter(workflow_execution=execution).update(
        modified_at=stale
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

    def _call(self, stuck_seconds=60, limit=100):
        req = MagicMock()
        req.data = {"stuck_seconds": stuck_seconds, "limit": limit}
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

    def test_file_less_stuck_is_left_alone_and_no_longer_consumes_the_window(self):
        """A file-less PG exec may still be QUEUED (a backlog/outage can outlast the
        stuck window) — it must NOT be failed, so a delayed worker can still finalize
        it (the one-way guard would otherwise block recovery). That invariant is
        unchanged and is what the status assertion below pins.

        The COUNTER expectation is deliberately updated: this used to assert
        ``skipped == 1``, i.e. the row was selected and then rejected downstream.
        It is now filtered out at selection instead, so it is never scanned. The
        mechanism moved because a downstream skip leaves ``modified_at`` untouched,
        so these rows were re-selected on every sweep forever and crowded genuinely
        recoverable executions out of the window — see the starvation test below.
        """
        ex = self._exec(ExecutionStatus.PENDING, files=[])
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert out["skipped"] == 0
        assert out["failed"] == 0
        assert ex.status == ExecutionStatus.PENDING.value

    def test_celery_execution_IS_now_recovered(self):
        """INVERTED deliberately (UN-3796). This asserted `scanned == 0` — that a
        Celery execution is never touched.

        That exclusion is the bug. A PG cutover removes the Celery workers, and an
        execution whose files all finished but whose chord callback never fired then
        sits EXECUTING forever: the callback is gone, there is no pg_barrier_state to
        recover from, and this endpoint refused to look. Nothing else could close it.

        The finalization logic was always transport-agnostic — it reads file statuses
        and recomputes the terminal status. Only the selection was narrow.
        """
        ex = self._exec(
            ExecutionStatus.EXECUTING, pg=False, files=[ExecutionStatus.COMPLETED]
        )
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["recovered"] == 1
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_a_NEVER_DISPATCHED_execution_is_left_to_the_undispatched_sweep(self):
        """The disjointness guard. Both handles NULL means the request died before
        dispatch — undispatched_sweep.py's row, which marks it ERROR with "did not
        start, safe to re-run".

        Both sweeps run on the same reaper cadence against the same table, so an
        overlap would be live from the first tick: one marking it ERROR while the
        other finalized it from whatever files happened to exist.
        """
        ex = WorkflowExecution.objects.create(
            workflow=self.wf,
            status=ExecutionStatus.EXECUTING.value,
            queue_message_id=None,
            task_id=None,
        )
        WorkflowFileExecution.objects.create(
            workflow_execution=ex, file_name="f", status=ExecutionStatus.COMPLETED.value
        )
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_still_processing_is_never_finalized(self):
        """A non-terminal file means work may still be in flight — finalizing would
        terminalize a live execution, and the one-way guard then blocks any correction.
        That invariant is unchanged.

        Counter expectation updated for the same reason as the file-less case: the row
        is now excluded at selection rather than skipped after being scanned.
        """
        ex = self._exec(
            ExecutionStatus.EXECUTING,
            files=[ExecutionStatus.COMPLETED, ExecutionStatus.EXECUTING],
        )
        _age(ex, 9999)
        out = self._call()
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert out["failed"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_recently_modified_not_recovered(self):
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        out = self._call(stuck_seconds=9000)  # exec's modified_at is fresh → past cutoff
        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_backlog_of_unrecoverable_rows_does_not_starve_a_recoverable_one(self):
        """THE regression. Selection is oldest-first with a hard ``limit``, so any row
        that is selected but never finalized occupies a slot on every future sweep —
        a skip does not advance ``modified_at``, so the same rows come back forever.
        A recoverable execution behind them is never reached: not scanned, not
        skipped, invisible.

        Found live during the UN-3796 cutover rehearsal: 1964 candidates, 1122 of them
        permanently unrecoverable (476 file-less, 646 with a non-terminal file), and a
        freshly stranded execution at rank 1964 that every sweep failed to see while
        logging a healthy-looking "scanned 100, recovered 0".

        Mutation check: drop either ``Exists`` clause from the selection query and this
        fails — the backlog fills the window and ``recovered`` is 0.
        """
        limit = 3
        # Older than the victim, and permanently unrecoverable: the two shapes that
        # made up the real backlog.
        for i in range(limit * 2):
            junk = self._exec(
                ExecutionStatus.EXECUTING,
                files=[] if i % 2 else [ExecutionStatus.EXECUTING],
            )
            _age(junk, 9000)
        victim = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        _age(victim, 100)  # NEWEST → last in oldest-first order

        out = self._call(limit=limit)

        victim.refresh_from_db()
        assert out["recovered"] == 1
        assert victim.status == ExecutionStatus.COMPLETED.value

    def test_window_is_spent_only_on_rows_that_can_finalize(self):
        """The drain property that makes oldest-first safe: everything scanned is
        finalized, so it leaves the candidate set and the backlog shrinks. If skips
        can consume the window the queue stops moving and FIFO stops being fair.
        """
        for _ in range(5):
            _age(self._exec(ExecutionStatus.EXECUTING, files=[]), 9000)
            _age(
                self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.EXECUTING]),
                9000,
            )
        _age(
            self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED]), 9000
        )

        out = self._call()

        assert out["scanned"] == 1
        assert out["recovered"] == 1
        assert out["skipped"] == 0

    def test_execution_time_comes_from_the_last_file_not_from_now(self):
        """``update_execution()`` stamps ``execution_time = now - created_at`` on any
        terminal transition. Correct for a live finalization; wrong here, where the
        sweep may finalize work that ended long ago — it would record how late the
        reaper was, not how long the run took. The integration backlog would have
        written multi-day runtimes onto executions that ran for minutes.
        """
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        _age(ex, 9000)
        # Set the timestamps AFTER _age — it backdates the file rows too, so doing this
        # first would have them overwritten and the assertion would read 0.0.
        created = timezone.now() - timedelta(seconds=9000)
        # modified_at MUST be passed explicitly here. BaseModelManager.update() does
        # `kwargs.setdefault("modified_at", timezone.now())`, so updating created_at
        # alone silently re-stamps modified_at to NOW and un-ages the row _age() just
        # aged — the execution then fails `modified_at__lt=cutoff`, the endpoint reports
        # scanned=0, and the test fails on STATUS with no hint that a timestamp moved.
        # That cost a CI round trip; the manager's docstring documents the override.
        WorkflowExecution.objects.filter(pk=ex.pk).update(
            created_at=created,
            modified_at=timezone.now() - timedelta(seconds=9000),
        )
        WorkflowFileExecution.objects.filter(workflow_execution=ex).update(
            modified_at=created + timedelta(seconds=42)
        )

        self._call()

        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value
        assert ex.execution_time == 42.0

    def test_execution_time_left_alone_when_no_file_timestamp(self):
        """No usable timestamp → keep whatever is there rather than write a worse
        guess. Pins the early return, which a refactor could silently drop.

        Exercised directly rather than through the endpoint: ``modified_at`` is
        ``auto_now`` and never NULL in practice, and a row with no file timestamp can
        no longer be SELECTED anyway (staleness is measured on the files now, and NULL
        does not satisfy ``< cutoff``). Driving it through the endpoint would assert
        the selection filter, not the early return this test exists to pin.
        """
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        # modified_at is NOT NULL at the database level, so it cannot be forced to NULL
        # to reach the early return — an earlier version of this test tried and died on
        # an IntegrityError. Patch the aggregate instead, which is the only way the
        # helper can legitimately see a missing timestamp.
        ex.execution_time = 7.5
        ex.save(update_fields=["execution_time"])

        with patch(
            "workflow_manager.file_execution.models.WorkflowFileExecution.objects"
        ) as objects:
            objects.filter.return_value.aggregate.return_value = {"last": None}
            self.view._restamp_execution_time_from_files(ex)

        ex.refresh_from_db()
        assert ex.execution_time == 7.5

    def test_execution_whose_files_JUST_finished_is_not_recovered(self):
        """The callback's window. ``workflow_execution.modified_at`` is effectively the
        START time — file completions write the file row, not the execution row — so any
        run longer than ``stuck_seconds`` is formally "stuck" while still running.

        The all-files-terminal filter stops that being catastrophic, but on its own it
        leaves a live race: between the last file going terminal and the callback
        finalizing, a perfectly healthy execution passes every other check. A sweep
        landing in that window finalizes it first, the terminal-one-way guard then
        refuses the callback's write, and the notification is silently lost.

        Measuring staleness on the files closes it. Mutation check: drop the
        ``last_file_at__lt=cutoff`` filter and this fails.
        """
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        _age(ex, 9000)  # execution row looks ancient (it is just the start time)
        WorkflowFileExecution.objects.filter(workflow_execution=ex).update(
            modified_at=timezone.now()  # ...but the work finished a moment ago
        )

        out = self._call(stuck_seconds=600)

        ex.refresh_from_db()
        assert out["scanned"] == 0
        assert ex.status == ExecutionStatus.EXECUTING.value

    def test_execution_whose_files_went_quiet_long_ago_IS_recovered(self):
        """The other half of the same predicate — moving staleness onto the files must
        not stop genuinely abandoned work from being recovered.
        """
        ex = self._exec(ExecutionStatus.EXECUTING, files=[ExecutionStatus.COMPLETED])
        _age(ex, 9000)
        WorkflowFileExecution.objects.filter(workflow_execution=ex).update(
            modified_at=timezone.now() - timedelta(seconds=3600)
        )

        out = self._call(stuck_seconds=600)

        ex.refresh_from_db()
        assert out["recovered"] == 1
        assert ex.status == ExecutionStatus.COMPLETED.value


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

    def test_retrieve_existence_check_db_error_returns_structured_500(self):
        # A DatabaseError from the unscoped exists-check is raised INSIDE the
        # Http404 except block, so the sibling `except Exception` cannot catch it;
        # without its own guard it would escape as Django's unstructured 500.
        # Assert we fail closed to a STRUCTURED 500 (retain the claim) and never
        # propagate — the reaper depends on the structured shape.
        from django.db import DatabaseError
        from django.http import Http404

        req = MagicMock()
        req.GET = {}
        with (
            patch.object(self.view, "get_object", side_effect=Http404("scoped out")),
            patch.object(
                WorkflowExecution.objects, "filter", side_effect=DatabaseError("db down")
            ),
        ):
            resp = self.view.retrieve(req, id=str(uuid.uuid4()))
        assert resp.status_code == 500
        assert resp.data.get("error") == "Failed to retrieve workflow execution"
        # No "detail" → this is the guarded structured 500, not the catch-all path.
        assert "detail" not in resp.data


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
