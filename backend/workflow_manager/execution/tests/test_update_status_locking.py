"""Row locking on the workflow-execution status write.

``update_status`` used to take ``SELECT ... FOR UPDATE`` on the execution row twice
(once in the view, again inside ``update_execution()``) and ran the file-row COUNTs
while holding it. ``FOR UPDATE`` conflicts with the ``FOR KEY SHARE`` every child-row
INSERT takes for its foreign-key check, so file-execution inserts for the same
execution queued behind each status write.

These tests pin the fix: ONE ``FOR NO KEY UPDATE`` per call, one COUNT query (taken
after the lock, so it sees what any writer it waited behind committed), child inserts
not blocked — and status writers still serialized against each other,
so the terminal-one-way guard and the attempt counter stay correct under concurrency.
"""

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

# Generous: only a broken lock makes the threads wait at all, and a hang must fail
# the test rather than the CI job.
WAIT_SECONDS = 10


def _update_status(execution_id, data):
    """Call the endpoint the way a worker does, on a fresh instance (as get_object
    would load it).
    """
    view = WorkflowExecutionInternalViewSet()
    req = MagicMock()
    req.data = data
    fresh = WorkflowExecution.objects.get(pk=execution_id)
    with patch.object(view, "get_object", return_value=fresh):
        return view.update_status(req, id=str(execution_id))


def _lock_statements(queries):
    sqls = [q["sql"].upper() for q in queries]
    no_key = [s for s in sqls if "FOR NO KEY UPDATE" in s]
    # A plain FOR UPDATE, i.e. one that is not part of FOR NO KEY UPDATE.
    full = [s for s in sqls if "FOR UPDATE" in s and "FOR NO KEY UPDATE" not in s]
    return sqls, no_key, full


class SingleLockTests(TestCase):
    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-lock")

    def _exec(self, status=ExecutionStatus.EXECUTING, pg=True, files=()):
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

    def _assert_one_no_key_lock(self, queries):
        sqls, no_key, full = _lock_statements(queries)
        assert len(no_key) == 1, sqls
        assert full == [], full
        return sqls

    def test_pg_update_status_takes_exactly_one_no_key_lock(self):
        ex = self._exec(files=[ExecutionStatus.COMPLETED])
        with CaptureQueriesContext(connection) as ctx:
            out = _update_status(
                ex.id,
                {
                    "status": ExecutionStatus.COMPLETED.value,
                    "total_files": 1,
                    "successful_files": 1,
                    "failed_files": 0,
                },
            )
        assert out.data["status"] == "updated"
        self._assert_one_no_key_lock(ctx.captured_queries)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_celery_update_status_takes_exactly_one_no_key_lock(self):
        ex = self._exec(pg=False, files=[ExecutionStatus.COMPLETED])
        with CaptureQueriesContext(connection) as ctx:
            _update_status(
                ex.id,
                {"status": ExecutionStatus.COMPLETED.value, "total_files": 1},
            )
        self._assert_one_no_key_lock(ctx.captured_queries)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_file_row_count_runs_once_and_after_the_lock(self):
        ex = self._exec(files=[ExecutionStatus.COMPLETED, ExecutionStatus.ERROR])
        with CaptureQueriesContext(connection) as ctx:
            _update_status(
                ex.id,
                {
                    "status": ExecutionStatus.ERROR.value,
                    "total_files": 1,
                    "failed_files": 0,
                },
            )
        sqls = self._assert_one_no_key_lock(ctx.captured_queries)
        lock_at = next(i for i, s in enumerate(sqls) if "FOR NO KEY UPDATE" in s)
        counts = [
            i
            for i, s in enumerate(sqls)
            if "COUNT(" in s and "WORKFLOW_FILE_EXECUTION" in s
        ]
        assert len(counts) == 1, sqls
        assert counts[0] > lock_at
        # The floor still applies: the rows say 2 total / 1 errored.
        ex.refresh_from_db()
        assert ex.total_files == 2
        assert ex.failed_files == 1

    def test_no_count_when_no_floored_counter_is_written(self):
        ex = self._exec(files=[ExecutionStatus.COMPLETED])
        with CaptureQueriesContext(connection) as ctx:
            _update_status(ex.id, {"status": ExecutionStatus.EXECUTING.value})
        assert not any("COUNT(" in q["sql"].upper() for q in ctx.captured_queries)

    def test_refused_pg_write_still_takes_one_lock(self):
        ex = self._exec(status=ExecutionStatus.COMPLETED)
        with CaptureQueriesContext(connection) as ctx:
            out = _update_status(ex.id, {"status": ExecutionStatus.EXECUTING.value})
        assert out.data.get("reason") == "already_final"
        self._assert_one_no_key_lock(ctx.captured_queries)

    def test_count_failure_writes_counters_as_given(self):
        ex = self._exec(files=[ExecutionStatus.ERROR])
        with patch.object(
            WorkflowExecutionInternalViewSet,
            "_count_file_rows",
            staticmethod(lambda execution: None),
        ):
            out = _update_status(
                ex.id,
                {
                    "status": ExecutionStatus.ERROR.value,
                    "total_files": 0,
                    "failed_files": 0,
                },
            )
        assert out.data["status"] == "updated"
        ex.refresh_from_db()
        assert ex.total_files == 0 and ex.failed_files == 0

    def test_failed_count_query_fails_the_request_and_commits_nothing(self):
        """As on main: a statement error in the count aborts the transaction, so the
        request fails (500, retried by the worker) instead of committing counters
        the floor never checked. Nothing is half-written.
        """
        ex = self._exec(files=[ExecutionStatus.ERROR])
        calls = []

        def broken_aggregate(*args, **kwargs):
            calls.append(1)
            with connection.cursor() as cur:
                cur.execute("SELECT 1/0")

        with patch(
            "django.db.models.query.QuerySet.aggregate",
            side_effect=broken_aggregate,
            autospec=True,
        ):
            out = _update_status(
                ex.id,
                {
                    "status": ExecutionStatus.ERROR.value,
                    "total_files": 0,
                    "failed_files": 0,
                },
            )
        assert out.status_code == 500, out.data
        assert len(calls) == 1  # tried once, not retried under the lock
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value
        assert ex.total_files == 0  # the floor would have made it 1
        assert not ex.failed_files

    def test_reaper_recovery_takes_one_no_key_lock(self):
        from datetime import timedelta

        from django.utils import timezone

        ex = self._exec(files=[ExecutionStatus.COMPLETED, ExecutionStatus.ERROR])
        stale = timezone.now() - timedelta(seconds=9999)
        WorkflowExecution.objects.filter(pk=ex.pk).update(modified_at=stale)
        WorkflowFileExecution.objects.filter(workflow_execution=ex).update(
            modified_at=stale
        )
        view = WorkflowExecutionInternalViewSet()
        req = MagicMock()
        req.data = {"stuck_seconds": 60, "limit": 10}
        with CaptureQueriesContext(connection) as ctx:
            out = view.recover_stuck_pg_executions(req).data
        assert out["recovered"] == 1
        sqls, no_key, full = _lock_statements(ctx.captured_queries)
        assert len(no_key) == 1 and full == [], sqls
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.ERROR.value
        assert ex.total_files == 2 and ex.failed_files == 1

    def test_update_execution_locks_once_by_itself(self):
        ex = self._exec()
        with CaptureQueriesContext(connection) as ctx:
            ex.update_execution(status=ExecutionStatus.COMPLETED)
        self._assert_one_no_key_lock(ctx.captured_queries)

    def test_row_locked_skips_the_second_lock(self):
        ex = self._exec()
        with transaction.atomic():
            locked = WorkflowExecution.objects.select_for_update(no_key=True).get(
                pk=ex.pk
            )
            with CaptureQueriesContext(connection) as ctx:
                locked.update_execution(
                    status=ExecutionStatus.COMPLETED,
                    row_locked=True,
                )
        _, no_key, full = _lock_statements(ctx.captured_queries)
        assert no_key == [] and full == []
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_row_locked_outside_a_transaction_is_rejected(self):
        ex = self._exec()
        # TestCase wraps each test in a transaction; step outside it the way a
        # real autocommit caller would be.
        with patch.object(connections["default"], "in_atomic_block", False):
            with pytest.raises(RuntimeError, match="row_locked"):
                ex.update_execution(status=ExecutionStatus.COMPLETED, row_locked=True)
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.EXECUTING.value


class ConcurrentStatusWriteTests(TransactionTestCase):
    """Real concurrent transactions on separate connections."""

    def setUp(self):
        self.wf = Workflow.objects.create(workflow_name="wf-lock-concurrent")

    def _exec(self, status=ExecutionStatus.EXECUTING, pg=True):
        return WorkflowExecution.objects.create(
            workflow=self.wf,
            status=status,
            queue_message_id=123 if pg else None,
            task_id=None if pg else uuid.uuid4(),
        )

    @staticmethod
    def _run(target, *args):
        """Run *target* on its own thread (own DB connection); collect its result
        or exception.
        """
        box = {}

        def runner():
            try:
                box["result"] = target(*args)
            except BaseException as e:  # noqa: BLE001 — surfaced by the test
                box["error"] = e
            finally:
                connections.close_all()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        return t, box

    def _hold_lock_inside_update_status(self, execution_id, data):
        """Start an update_status that pauses while it holds the row lock.

        Returns (thread, box, locked_event, release_event). The pause is inside
        ``_update_file_aggregates`` — after the status write, before commit.
        """
        locked, release = threading.Event(), threading.Event()
        original = WorkflowExecutionInternalViewSet._update_file_aggregates
        state = {"thread": None}

        def paused(execution, validated_data):
            if threading.get_ident() == state["thread"]:
                locked.set()
                assert release.wait(WAIT_SECONDS), "holder was never released"
            return original(execution, validated_data)

        patcher = patch.object(
            WorkflowExecutionInternalViewSet,
            "_update_file_aggregates",
            staticmethod(paused),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        def target():
            state["thread"] = threading.get_ident()
            return _update_status(execution_id, data)

        t, box = self._run(target)
        assert locked.wait(WAIT_SECONDS), f"holder never reached the lock: {box}"
        return t, box, release

    def test_child_insert_is_not_blocked_by_a_status_write(self):
        """The fix itself: a file-execution INSERT (FK check → FOR KEY SHARE on the
        execution row) must not wait for an in-flight status write.
        """
        for pg in (True, False):
            ex = self._exec(pg=pg)
            t, box, release = self._hold_lock_inside_update_status(
                ex.id, {"status": ExecutionStatus.COMPLETED.value, "total_files": 1}
            )
            try:

                def insert(execution_id=ex.id):
                    with transaction.atomic():
                        with connection.cursor() as cur:
                            # Fail fast instead of hanging if the insert queues.
                            cur.execute("SET LOCAL lock_timeout = '2s'")
                        WorkflowFileExecution.objects.create(
                            workflow_execution_id=execution_id,
                            file_name="child",
                            status=ExecutionStatus.PENDING.value,
                        )
                    return True

                it, ibox = self._run(insert)
                it.join(WAIT_SECONDS)
                assert (
                    ibox.get("result") is True
                ), f"child insert blocked by the status lock (pg={pg}): {ibox}"
            finally:
                release.set()
                t.join(WAIT_SECONDS)
            assert box.get("result") is not None, box
            assert box["result"].data["status"] == "updated"
            ex.refresh_from_db()
            assert ex.status == ExecutionStatus.COMPLETED.value
            assert (
                WorkflowFileExecution.objects.filter(workflow_execution=ex).count() == 1
            )

    def test_count_sees_file_errors_committed_while_waiting_for_the_lock(self):
        """A callback that waited behind another writer must floor its counters at
        what that writer committed. Here the holder (reaper-style) cascades the
        files to ERROR; the waiting success callback corrects the status to
        COMPLETED (ERROR is correctable) but must not write failed_files=0.
        """
        ex = self._exec()
        WorkflowFileExecution.objects.create(
            workflow_execution=ex,
            file_name="f",
            status=ExecutionStatus.EXECUTING.value,
        )
        t, box, release = self._hold_lock_inside_update_status(
            ex.id,
            {
                "status": ExecutionStatus.ERROR.value,
                "cascade_terminal_files": True,
                "error_message": "reaper",
            },
        )
        st, sbox = self._run(
            _update_status,
            ex.id,
            {
                "status": ExecutionStatus.COMPLETED.value,
                "total_files": 1,
                "successful_files": 1,
                "failed_files": 0,
            },
        )
        try:
            st.join(1.0)
            assert st.is_alive(), f"callback did not wait for the row lock: {sbox}"
        finally:
            release.set()
            t.join(WAIT_SECONDS)
            st.join(WAIT_SECONDS)
        assert box["result"].data["status"] == "updated", box
        assert sbox["result"].data["status"] == "updated", sbox
        ex.refresh_from_db()
        assert ex.failed_files == 1, "count missed rows committed during the wait"

    def test_uncommitted_file_insert_holds_no_lock_on_the_execution_row(self):
        """Why counting after the lock can't "wait for" in-flight file inserts, under
        either lock mode: Django's foreign keys are DEFERRABLE INITIALLY DEFERRED,
        so an open INSERT takes its FOR KEY SHARE only at commit. Even main's plain
        FOR UPDATE is granted at once, and the open row is invisible to the count.
        """
        ex = self._exec()
        inserted, release = threading.Event(), threading.Event()

        def insert_batch(execution_id=ex.id):
            with transaction.atomic():
                WorkflowFileExecution.objects.create(
                    workflow_execution_id=execution_id,
                    file_name="new",
                    status=ExecutionStatus.PENDING.value,
                )
                inserted.set()
                assert release.wait(WAIT_SECONDS), "inserter was never released"
            return True

        it, ibox = self._run(insert_batch)
        assert inserted.wait(WAIT_SECONDS), ibox

        def lock_and_count(execution_id=ex.id):
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute("SET LOCAL lock_timeout = '2s'")
                WorkflowExecution.objects.select_for_update().get(pk=execution_id)
                return WorkflowFileExecution.objects.filter(
                    workflow_execution_id=execution_id
                ).count()

        try:
            lt, lbox = self._run(lock_and_count)
            lt.join(WAIT_SECONDS)
            assert lbox.get("result") == 0, lbox
        finally:
            release.set()
            it.join(WAIT_SECONDS)
        assert ibox.get("result") is True, ibox

    def test_status_writers_still_exclude_each_other(self):
        """A second writer must wait for the first to commit, then see its result:
        here the straggler's EXECUTING is refused over the committed COMPLETED.
        """
        ex = self._exec()
        t, box, release = self._hold_lock_inside_update_status(
            ex.id, {"status": ExecutionStatus.COMPLETED.value}
        )
        st, sbox = self._run(
            _update_status, ex.id, {"status": ExecutionStatus.EXECUTING.value}
        )
        try:
            st.join(1.0)
            assert st.is_alive(), f"second writer did not wait for the row lock: {sbox}"
        finally:
            release.set()
            t.join(WAIT_SECONDS)
            st.join(WAIT_SECONDS)
        assert box["result"].data["status"] == "updated", box
        assert sbox["result"].data.get("reason") == "already_final", sbox
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.COMPLETED.value

    def test_racing_writers_never_revert_completed(self):
        """Many concurrent writers, one COMPLETED among stale EXECUTINGs: whatever
        the interleaving, COMPLETED is the final status.
        """
        for _ in range(3):
            ex = self._exec()
            start = threading.Barrier(8)

            def write(status, start=start, execution_id=ex.id):
                start.wait(WAIT_SECONDS)
                return _update_status(execution_id, {"status": status.value})

            runs = [self._run(write, ExecutionStatus.COMPLETED)] + [
                self._run(write, ExecutionStatus.EXECUTING) for _ in range(7)
            ]
            for t, _ in runs:
                t.join(WAIT_SECONDS)
            for _, b in runs:
                assert "error" not in b, b
            ex.refresh_from_db()
            assert ex.status == ExecutionStatus.COMPLETED.value

    def test_concurrent_attempt_increments_are_not_lost(self):
        """PG path increments from the locked value, so N racing increments land
        as N — only true if the single lock still serializes the writers.
        """
        ex = self._exec()
        n = 6
        start = threading.Barrier(n)

        def bump():
            start.wait(WAIT_SECONDS)
            # attempts=99 > any snapshot → increment_attempt is True every time.
            return _update_status(
                ex.id, {"status": ExecutionStatus.EXECUTING.value, "attempts": 99}
            )

        runs = [self._run(bump) for _ in range(n)]
        for t, _ in runs:
            t.join(WAIT_SECONDS)
        for _, b in runs:
            assert "error" not in b and b["result"].data["status"] == "updated", b
        ex.refresh_from_db()
        assert ex.attempts == n
