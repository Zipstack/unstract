"""Tests for :class:`queue_backend.pg_barrier.PgBarrier`.

Three layers:

1. **Protocol / TTL** — no DB, no Celery.
2. **Enqueue + link/abort tasks** — a real autocommit Postgres connection is
   injected into the module thread-local (the barrier's SQL runs for real); the
   Celery header-task dispatch + callback are mocked. Skips if Postgres is
   unreachable or the ``pg_barrier_state`` migration is unapplied.
3. **Atomicity** — two real connections race the decrement SQL directly.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import psycopg2
import psycopg2.extensions
import pytest
from queue_backend import barrier as barrier_mod
from queue_backend import pg_barrier
from queue_backend.fairness import FAIRNESS_HEADER_NAME, FairnessKey, WorkloadType
from queue_backend.handle import BarrierHandle
from queue_backend.pg_barrier import (
    PgBarrier,
    _barrier_pg_decrement,
    _fire_barrier_callback,
    barrier_pg_abort,
    barrier_pg_decr_and_check,
    claim_batch,
    run_batch_with_barrier,
    try_claim_orchestration,
)
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.routing import QueueBackend


def _pg_header(task_name="process_file_batch", args=None, queue="file_processing"):
    """A Celery-Signature-shaped stub for the PG-fan-out path (.task/.args/.kwargs/.options)."""
    sig = MagicMock(name="pg_header_signature")
    sig.task = task_name
    sig.args = args if args is not None else [{"file": "f1"}]
    sig.kwargs = {}
    sig.options = {"queue": queue}
    return sig


_CALLBACK = {
    "task_name": "process_batch_callback_api",
    "kwargs": {"execution_id": "exec-1", "pipeline_id": "pipe-1"},
    "queue": "general",
    "fairness_headers": None,
}


def _mock_header_task():
    """A header-task Signature whose clone() records link/link_error/apply_async."""
    cloned = MagicMock(name="cloned_signature")
    task = MagicMock(name="header_signature")
    task.clone.return_value = cloned
    return task, cloned


# --- Layer 1: protocol shape + TTL (no DB) ---


class TestPgBarrierProtocolShape:
    def test_satisfies_barrier_protocol(self):
        barrier: barrier_mod.Barrier = PgBarrier()
        assert callable(getattr(barrier, "enqueue", None))

    def test_handle_satisfies_barrier_handle(self):
        handle: BarrierHandle = pg_barrier._PgBarrierHandle(id="exec-1")
        assert handle.id == "exec-1"
        assert isinstance(handle.id, str)


class TestTtlEnv:
    # PgBarrier shares barrier.barrier_ttl_seconds() with the Redis backend.
    def test_default_is_six_hours(self, monkeypatch):
        monkeypatch.delenv("WORKER_BARRIER_KEY_TTL_SECONDS", raising=False)
        assert barrier_mod.barrier_ttl_seconds() == 6 * 60 * 60

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "120")
        assert barrier_mod.barrier_ttl_seconds() == 120

    @pytest.mark.parametrize("bad", ["abc", "0", "-5"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", bad)
        with pytest.raises(ValueError, match="WORKER_BARRIER_KEY_TTL_SECONDS"):
            barrier_mod.barrier_ttl_seconds()


class TestStuckTimeoutEnv:
    # The PG barrier's sliding last_progress_at window (UN-3661) — distinct from the
    # Redis-shared TTL above. Default 2.5h, in Celery's FILE_PROCESSING band (2h–3h).
    def test_default_is_two_and_half_hours(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS", raising=False)
        assert barrier_mod.barrier_stuck_timeout_seconds() == 9000

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS", "120")
        assert barrier_mod.barrier_stuck_timeout_seconds() == 120

    @pytest.mark.parametrize("bad", ["abc", "0", "-5"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS", bad)
        with pytest.raises(ValueError, match="WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS"):
            barrier_mod.barrier_stuck_timeout_seconds()


class TestEnqueueShortCircuits:
    def test_empty_header_returns_none(self):
        # Returns before any DB / dispatch.
        assert (
            PgBarrier().enqueue(
                [],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "e"},
                callback_queue="general",
                app_instance=None,
            )
            is None
        )

    def test_missing_execution_id_raises(self):
        with pytest.raises(ValueError, match="execution_id"):
            PgBarrier().enqueue(
                [_mock_header_task()[0]],
                callback_task_name="cb",
                callback_kwargs={},  # no execution_id
                callback_queue="general",
                app_instance=None,
            )


# --- Idempotent-write reconnect-retry (no DB) ---


_UNSET = object()


class _FakeCursorCtx:
    def __init__(self, on_execute, fetchone_result=_UNSET):
        self._on_execute = on_execute
        self._fetchone_result = fetchone_result

    def __enter__(self):
        cur = MagicMock(name="cursor")
        cur.execute.side_effect = self._on_execute
        # Default (unset): fetchone() returns a truthy MagicMock (claim won). Pass
        # fetchone_result=None to exercise the "lost" answer (claim already held).
        if self._fetchone_result is not _UNSET:
            cur.fetchone.return_value = self._fetchone_result
        return cur

    def __exit__(self, *exc):
        return False


class _FakeConn:
    """Minimal psycopg2-connection stub. ``execute_error`` (if set) is raised by
    every cursor.execute on this connection — simulating a stale/dead socket.
    ``commit_error`` (if set) is raised by ``commit()`` after the execute lands —
    the ambiguous "reaped during commit" case the decrement must NOT retry.
    """

    def __init__(self, *, execute_error=None, commit_error=None, fetchone_result=_UNSET):
        self.closed = False
        self._execute_error = execute_error
        self._commit_error = commit_error
        self._fetchone_result = fetchone_result
        self.commits = 0
        self.rollbacks = 0
        self.executes = 0

    def cursor(self):
        def _on_execute(*_a, **_k):
            self.executes += 1
            if self._execute_error is not None:
                raise self._execute_error

        return _FakeCursorCtx(_on_execute, self._fetchone_result)

    def commit(self):
        self.commits += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def get_transaction_status(self):
        # The decrement entry-guard checks this; a stub conn is always idle (each
        # _cursor use commits), so it never trips the open-transaction guard.
        return psycopg2.extensions.TRANSACTION_STATUS_IDLE


@pytest.fixture
def _clean_local():
    """Ensure the module thread-local connection is reset around each test."""
    pg_barrier._local.conn = None
    yield
    pg_barrier._local.conn = None


class TestIdempotentWriteRetry:
    """`_run_idempotent_pre_dispatch_write` self-heals a stale cached connection
    with ONE retry — the fix for the `server closed the connection unexpectedly`
    abort at barrier enqueue. It must retry ONLY on connection errors, stay
    bounded, and never silently swallow a real (non-connection) failure.
    """

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        # The retry backoff is real (0.5s); skip the wall-clock wait in tests.
        monkeypatch.setattr(pg_barrier.time, "sleep", lambda *_a, **_k: None)

    @pytest.mark.parametrize(
        "exc",
        [
            psycopg2.OperationalError("server closed the connection unexpectedly"),
            psycopg2.InterfaceError("connection already closed"),
        ],
        ids=["OperationalError", "InterfaceError"],
    )
    def test_retries_once_on_dead_connection_then_succeeds(
        self, _clean_local, monkeypatch, caplog, exc
    ):
        # InterfaceError is the more common stale-socket symptom, so both arms of
        # the (OperationalError, InterfaceError) catch must self-heal.
        dead = _FakeConn(execute_error=exc)
        healthy = _FakeConn()
        pg_barrier._local.conn = dead
        # On reconnect (_cursor discarded the dead conn), hand back the healthy one.
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        attempts = []

        def op(cur):
            attempts.append(1)
            cur.execute("UPSERT ...", ("x",))

        with caplog.at_level("WARNING"):
            pg_barrier._run_idempotent_pre_dispatch_write(op, what="test")

        assert len(attempts) == 2  # first failed mid-execute, retry succeeded
        assert dead.executes == 1 and healthy.executes == 1  # exactly one extra try
        assert dead.commits == 0  # no partial commit on the failed attempt
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed exactly once, on the retry
        assert pg_barrier._local.conn is healthy
        # logs on retry (not on success) and names the real error, not a guess.
        assert "reconnecting and retrying" in caplog.text
        assert type(exc).__name__ in caplog.text

    def test_does_not_retry_non_connection_error(self, _clean_local, monkeypatch):
        healthy = _FakeConn()
        pg_barrier._local.conn = healthy
        reconnects = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: reconnects.append(1) or _FakeConn(),
        )

        def op(cur):
            raise ValueError("not a connection problem")

        with pytest.raises(ValueError, match="not a connection problem"):
            pg_barrier._run_idempotent_pre_dispatch_write(op, what="test")
        assert reconnects == []  # a real error must surface immediately, no retry

    def test_reraises_after_exhausting_attempts(self, _clean_local, monkeypatch):
        err = psycopg2.OperationalError("still down")
        # Every connection (initial + reconnect) is dead → both attempts fail.
        monkeypatch.setattr(
            pg_barrier, "create_pg_connection", lambda **_k: _FakeConn(execute_error=err)
        )

        with pytest.raises(psycopg2.OperationalError, match="still down"):
            pg_barrier._run_idempotent_pre_dispatch_write(
                lambda cur: cur.execute("X"), what="test"
            )


class TestDecrementPhaseSplitRetry:
    """`_apply_decrement` is the NON-idempotent barrier decrement, so unlike the
    idempotent pre-dispatch write it CANNOT retry freely. It self-heals exactly
    one provably-safe case — an execute-phase failure on a *cached* connection
    (the PgBouncer idle-reap: the statement never reached the server, so nothing
    committed) — and refuses every other: a commit-phase failure is ambiguous
    (the server may have applied it) and a fresh-conn failure is a real DB error.
    The count is therefore never double-applied. (UN-3660)
    """

    @pytest.fixture
    def sleeps(self, monkeypatch):
        # Record (and skip) the retry backoff so a test can assert it fired exactly
        # when — and only when — a retry happens. Deleting the time.sleep in
        # _apply_decrement, or a refactor that starts hammering a struggling DB,
        # changes this list.
        calls: list[float] = []
        monkeypatch.setattr(pg_barrier.time, "sleep", calls.append)
        return calls

    @pytest.mark.parametrize(
        "exc",
        [
            psycopg2.OperationalError("server closed the connection unexpectedly"),
            psycopg2.InterfaceError("connection already closed"),
        ],
        ids=["OperationalError", "InterfaceError"],
    )
    def test_execute_phase_reaped_cached_conn_retries_once(
        self, _clean_local, monkeypatch, caplog, sleeps, exc
    ):
        # The idle-reap: a cached conn fails mid-execute (never committed), so the
        # decrement reconnects and re-applies exactly once on a healthy conn.
        dead = _FakeConn(execute_error=exc)
        healthy = _FakeConn()
        pg_barrier._local.conn = dead  # cached → "reused"
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        with caplog.at_level("WARNING"):
            pg_barrier._apply_decrement("exec-1", '{"ok": true}', reused=True)

        assert dead.executes == 1 and healthy.executes == 1  # exactly one extra try
        assert dead.commits == 0  # the reaped attempt never committed
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed exactly once, on the retry
        assert pg_barrier._local.conn is healthy
        assert sleeps == [pg_barrier._BARRIER_RETRY_BACKOFF_SECONDS]  # backoff fired once
        assert "execute failed on a cached connection" in caplog.text
        assert type(exc).__name__ in caplog.text

    def test_commit_phase_failure_is_not_retried(self, _clean_local, monkeypatch, sleeps):
        # A commit failure is AMBIGUOUS (the server may have applied it) → must
        # NOT retry, or the decrement could land twice. It propagates; the dead
        # conn is discarded; no reconnect is attempted.
        commit_err = psycopg2.OperationalError("server closed during commit")
        conn = _FakeConn(commit_error=commit_err)
        pg_barrier._local.conn = conn
        reconnects = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: reconnects.append(1) or _FakeConn(),
        )

        with pytest.raises(psycopg2.OperationalError, match="during commit"):
            pg_barrier._apply_decrement("exec-2", '{"ok": true}', reused=True)

        assert conn.executes == 1  # the UPDATE ran exactly once
        assert conn.commits == 1  # commit was attempted exactly once
        assert reconnects == []  # NEVER reconnected/retried after a commit failure
        assert conn.closed is True  # the dead conn was discarded
        assert sleeps == []  # no backoff — a commit failure is not retried

    def test_fresh_conn_execute_failure_is_not_retried(
        self, _clean_local, monkeypatch, sleeps
    ):
        # reused=False (the production wrapper passes this when no conn was cached
        # before the entry guard). A failure on a fresh conn is a genuine DB error,
        # not an idle-reap, so the reused-guard skips the retry — even though it is
        # a connection-dead error — and it surfaces immediately.
        err = psycopg2.OperationalError("db down")
        conn = _FakeConn(execute_error=err)
        pg_barrier._local.conn = conn
        reconnects = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: reconnects.append(1) or _FakeConn(),
        )

        with pytest.raises(psycopg2.OperationalError, match="db down"):
            pg_barrier._apply_decrement("exec-3", '{"ok": true}', reused=False)

        assert reconnects == []  # fresh-conn death is not retried
        assert sleeps == []  # …so no backoff either

    def test_non_connection_error_is_not_retried(self, _clean_local, monkeypatch, sleeps):
        # A DataError (e.g. a NUL byte rejected by the jsonb cast) is not a
        # connection death → propagate immediately so the caller tears the barrier
        # down. A live conn after a logical error is NOT discarded.
        conn = _FakeConn(execute_error=psycopg2.DataError("invalid byte 0x00"))
        pg_barrier._local.conn = conn
        reconnects = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: reconnects.append(1) or _FakeConn(),
        )

        with pytest.raises(psycopg2.DataError):
            pg_barrier._apply_decrement("exec-4", '{"ok": true}', reused=True)

        assert reconnects == []  # no retry on a logical/data error
        assert conn.closed is False  # a live conn after a data error is kept
        assert sleeps == []  # not retried → no backoff

    def test_reraises_after_one_retry(self, _clean_local, monkeypatch, sleeps):
        # The one-shot bound: a reused-conn idle-reap retries ONCE; if the
        # reconnect target also dies on execute, re-raise rather than loop. On
        # attempt 2 the attempt bound (attempt < _BARRIER_DECREMENT_ATTEMPTS) is
        # what refuses the next retry — note reused is still True (the caller's
        # entry-time value), so bumping the attempt constant would NOT add
        # self-heals unless the reconnect logic also re-evaluated freshness.
        err = psycopg2.OperationalError("still down")
        pg_barrier._local.conn = _FakeConn(execute_error=err)
        reconnects = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: reconnects.append(1) or _FakeConn(execute_error=err),
        )

        with pytest.raises(psycopg2.OperationalError, match="still down"):
            pg_barrier._apply_decrement("exec-5", '{"ok": true}', reused=True)

        assert len(reconnects) == 1  # exactly one reconnect, then gave up
        assert sleeps == [pg_barrier._BARRIER_RETRY_BACKOFF_SECONDS]  # one backoff

    def test_wrapper_fresh_conn_not_retried_end_to_end(
        self, _clean_local, monkeypatch, sleeps
    ):
        # Through the PRODUCTION entry (_barrier_pg_decrement), not _apply_decrement
        # directly: with no cached conn, the entry-guard's _get_conn() creates a
        # fresh one — but _barrier_pg_decrement samples `reused` BEFORE the guard,
        # so it threads reused=False and a genuine fresh-conn DB error is NOT
        # retried. Pins the sample-before-the-guard wiring the direct-call tests
        # can't see (the guard would otherwise leave _local.conn always populated).
        err = psycopg2.OperationalError("db down")
        creates = []
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: creates.append(c := _FakeConn(execute_error=err)) or c,
        )
        pg_barrier._local.conn = None  # nothing cached → wrapper samples reused=False

        with pytest.raises(psycopg2.OperationalError, match="db down"):
            _barrier_pg_decrement(
                {"f": 1}, execution_id="exec-FRESH", callback_descriptor=_CALLBACK
            )

        assert len(creates) == 1  # the guard created one; NO retry reconnect
        assert sleeps == []  # a fresh-conn death is not retried → no backoff


@pytest.mark.integration
def test_create_pg_connection_is_non_autocommit():
    """The decrement phase-split's exactly-once safety rests on the connection
    being non-autocommit (an uncommitted UPDATE rolls back on disconnect, so an
    execute-phase failure is never durable). Pin that at its SOURCE — a future
    ``conn.autocommit = True`` in ``create_pg_connection`` would silently
    reintroduce the double-count the split exists to prevent, and no other test
    would catch it (the barrier_db fixture sets autocommit itself).

    Opens a real connection inline (no fixture), so it's marked ``integration``
    explicitly — the collection hook keys off fixture names and wouldn't catch
    it, which would otherwise leave it in the DB-free unit lane.
    """
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    try:
        conn = create_pg_connection(env_prefix="TEST_DB_")
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    try:
        assert conn.autocommit is False
    finally:
        conn.close()


class TestClaimOrchestrationRetry:
    """``try_claim_orchestration`` is a RETURNING claim, so — like the decrement,
    and unlike the idempotent pre-dispatch write — it self-heals ONLY the
    provably-safe case: an execute-phase failure on a *cached* connection (idle
    reap; the INSERT never committed, so the retry's win/lost answer is
    authoritative). A commit-phase failure is ambiguous and a fresh-conn failure
    is a real error — neither is retried, so a real winner is never flipped to a
    loser (which would strand the execution). Guards UN-3671's PR-review fix.
    """

    @pytest.fixture
    def sleeps(self, monkeypatch):
        calls: list[float] = []
        monkeypatch.setattr(pg_barrier.time, "sleep", calls.append)
        return calls

    def test_execute_phase_reaped_cached_conn_retries_once(
        self, _clean_local, monkeypatch, caplog, sleeps
    ):
        dead = _FakeConn(
            execute_error=psycopg2.OperationalError("server closed the connection")
        )
        healthy = _FakeConn()
        pg_barrier._local.conn = dead  # cached → "reused"
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        with caplog.at_level("WARNING"):
            try_claim_orchestration("exec-1", "org-1")

        assert dead.executes == 1 and healthy.executes == 1  # exactly one extra try
        assert dead.commits == 0  # the reaped attempt never committed
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed exactly once, on the retry
        assert pg_barrier._local.conn is healthy
        assert sleeps == [pg_barrier._BARRIER_RETRY_BACKOFF_SECONDS]
        assert "execute failed on a cached connection" in caplog.text

    def test_commit_phase_failure_is_not_retried(self, _clean_local, monkeypatch, sleeps):
        # Ambiguous commit (the server may have committed) → NOT retried, or a real
        # winner could be flipped to a loser. Propagates; no reconnect.
        conn = _FakeConn(
            commit_error=psycopg2.OperationalError("server closed during commit")
        )
        pg_barrier._local.conn = conn
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: pytest.fail("must not reconnect on a commit-phase failure"),
        )
        with pytest.raises(psycopg2.OperationalError):
            try_claim_orchestration("exec-1", "org-1")
        assert conn.executes == 1 and conn.commits == 1  # tried once, no retry
        assert sleeps == []  # no backoff → no retry

    def test_fresh_conn_execute_failure_is_not_retried(
        self, _clean_local, monkeypatch, sleeps
    ):
        # A freshly-created connection failing is a real DB error, not an idle reap
        # (reused is False when _local.conn starts empty) → not retried.
        dead = _FakeConn(execute_error=psycopg2.OperationalError("connection refused"))
        pg_barrier._local.conn = None  # → reused False
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: dead)
        with pytest.raises(psycopg2.OperationalError):
            try_claim_orchestration("exec-1", "org-1")
        assert dead.executes == 1  # no retry
        assert sleeps == []

    @pytest.mark.parametrize(
        "exc_cls",
        [psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn],
        ids=["table-missing (0012)", "column-missing (0013)"],
    )
    def test_schema_behind_raises_actionable_error(self, _clean_local, exc_cls):
        # A schema behind the code — 0012 not run (no table) OR 0012-but-not-0013
        # (table, no organization_id column) — must fail fast with an actionable
        # message, NOT the generic per-execution stack trace, and NOT proceed.
        pg_barrier._local.conn = _FakeConn(execute_error=exc_cls("schema behind"))
        with pytest.raises(RuntimeError, match="schema is out of date"):
            try_claim_orchestration("exec-1", "org-1")


class TestClaimBatchRetry:
    """``claim_batch`` is a RETURNING claim (via the shared
    ``_run_returning_claim_with_reconnect``), so it self-heals ONLY the
    provably-safe case: an execute-phase failure on a *cached* connection — the idle
    reap that stranded scheduled ETL batches (UN-3684: a barrier connection idle
    ~30 min between pipeline runs, past ``server_idle_timeout``; the INSERT never
    committed, so the retry's claim answer is authoritative). NOT retried, for two
    distinct reasons: a **commit-phase** failure is ambiguous — a re-run could flip
    ``True``→``False`` and strand the barrier; a **fresh-conn** failure is a real DB
    error — reconnecting buys nothing.
    """

    @pytest.fixture
    def sleeps(self, monkeypatch):
        calls: list[float] = []
        monkeypatch.setattr(pg_barrier.time, "sleep", calls.append)
        return calls

    def test_execute_phase_reaped_cached_conn_retries_once(
        self, _clean_local, monkeypatch, caplog, sleeps
    ):
        dead = _FakeConn(
            execute_error=psycopg2.OperationalError("server closed the connection")
        )
        healthy = _FakeConn()
        pg_barrier._local.conn = dead  # cached → "reused"
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        with caplog.at_level("WARNING"):
            claimed = claim_batch("exec-1", 0)

        assert claimed is True  # authoritative answer taken from the retry
        assert dead.executes == 1 and healthy.executes == 1  # exactly one extra try
        assert dead.commits == 0  # the reaped attempt never committed
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed exactly once, on the retry
        assert pg_barrier._local.conn is healthy
        assert sleeps == [pg_barrier._BARRIER_RETRY_BACKOFF_SECONDS]
        assert "execute failed on a cached connection" in caplog.text

    def test_commit_phase_failure_is_not_retried(self, _clean_local, monkeypatch, sleeps):
        # Ambiguous commit (server may have committed) → NOT retried, or a re-run
        # could flip the claim and strand the barrier. Propagates; no reconnect.
        conn = _FakeConn(
            commit_error=psycopg2.OperationalError("server closed during commit")
        )
        pg_barrier._local.conn = conn
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: pytest.fail("must not reconnect on a commit-phase failure"),
        )
        with pytest.raises(psycopg2.OperationalError):
            claim_batch("exec-1", 0)
        assert conn.executes == 1 and conn.commits == 1  # tried once, no retry
        assert sleeps == []  # no backoff → no retry

    def test_fresh_conn_execute_failure_is_not_retried(
        self, _clean_local, monkeypatch, sleeps
    ):
        # A freshly-created connection failing is a real DB error, not an idle reap
        # (reused is False when _local.conn starts empty) → not retried.
        dead = _FakeConn(execute_error=psycopg2.OperationalError("connection refused"))
        pg_barrier._local.conn = None  # → reused False
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: dead)
        with pytest.raises(psycopg2.OperationalError):
            claim_batch("exec-1", 0)
        assert dead.executes == 1  # no retry
        assert sleeps == []

    def test_second_conn_dead_failure_propagates(self, _clean_local, monkeypatch, sleeps):
        # Retry is bounded to ONE: a cached reap retries onto a fresh conn that also
        # dies → propagate (don't loop, don't hit the AssertionError fall-through).
        # Pins the boundary that `attempt < _BARRIER_WRITE_ATTEMPTS` enforces.
        dead1 = _FakeConn(execute_error=psycopg2.OperationalError("reaped"))
        dead2 = _FakeConn(execute_error=psycopg2.OperationalError("still down"))
        pg_barrier._local.conn = dead1  # cached → reused
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: dead2)
        with pytest.raises(psycopg2.OperationalError):
            claim_batch("exec-1", 0)
        assert dead1.executes == 1 and dead2.executes == 1  # exactly one retry
        assert sleeps == [pg_barrier._BARRIER_RETRY_BACKOFF_SECONDS]

    def test_non_connection_execute_error_on_reused_conn_not_retried(
        self, _clean_local, monkeypatch, sleeps
    ):
        # The `conn_dead` conjunct is the only guard against retrying a real SQL
        # error on a cached conn — a regression dropping it would silently re-run a
        # DataError. Pin: reused conn, non-conn error → NOT retried.
        bad = _FakeConn(execute_error=psycopg2.DataError("invalid byte 0x00"))
        pg_barrier._local.conn = bad  # cached → reused True
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: pytest.fail("must not reconnect on a non-connection error"),
        )
        with pytest.raises(psycopg2.DataError):
            claim_batch("exec-1", 0)
        assert bad.executes == 1  # no retry
        assert sleeps == []

    def test_retry_returns_the_lost_answer_authoritatively(
        self, _clean_local, monkeypatch, sleeps
    ):
        # The "win/LOST answer is authoritative" half: after a reaped-conn retry, a
        # fresh conn whose RETURNING yields no row → claim already held → returns
        # False (not the truthy MagicMock default the happy-path test can only see).
        dead = _FakeConn(execute_error=psycopg2.OperationalError("reaped"))
        healthy = _FakeConn(fetchone_result=None)  # ON CONFLICT DO NOTHING: no row
        pg_barrier._local.conn = dead
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)
        assert claim_batch("exec-1", 0) is False  # authoritative "lost" from retry
        assert healthy.commits == 1


class TestReleaseOrchestrationClaimRetry:
    """``release_orchestration_claim`` is a first-write-after-idle on the failure
    path whose raise the caller swallows — an un-retried idle-reap would leave the
    claim committed and suppress every redelivery. Its DELETE is idempotent, so it
    reuses the retry-once helper.
    """

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr(pg_barrier.time, "sleep", lambda *_a, **_k: None)

    def test_retries_once_on_reaped_cached_conn(self, _clean_local, monkeypatch, caplog):
        dead = _FakeConn(
            execute_error=psycopg2.InterfaceError("connection already closed")
        )
        healthy = _FakeConn()
        pg_barrier._local.conn = dead
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        with caplog.at_level("WARNING"):
            pg_barrier.release_orchestration_claim("exec-1")

        assert dead.executes == 1 and healthy.executes == 1  # exactly one retry
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed on the retry
        assert "release orchestration claim" in caplog.text

    def test_non_connection_error_surfaces(self, _clean_local, monkeypatch):
        # A real (non-connection) error must not be silently retried away — it
        # propagates so the best-effort caller logs it.
        pg_barrier._local.conn = _FakeConn(execute_error=ValueError("logic"))
        monkeypatch.setattr(
            pg_barrier, "create_pg_connection", lambda **_k: pytest.fail("no reconnect")
        )
        with pytest.raises(ValueError, match="logic"):
            pg_barrier.release_orchestration_claim("exec-1")


# --- Layer 2: enqueue + link/abort with a real injected connection ---


@pytest.fixture
def barrier_db():
    """Inject a real autocommit connection into pg_barrier's thread-local.

    Autocommit so each statement commits independently (like the worker tasks in
    production) and the barrier's ``_cursor`` commit() is a no-op. The link/abort
    tasks run in this same (test) thread, so they see the injected connection.
    """
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    try:
        conn = create_pg_connection(env_prefix="TEST_DB_")
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_barrier_state')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_barrier_state migration not applied (run backend migrate)")
        cur.execute("DELETE FROM pg_barrier_state")
    pg_barrier._local.conn = conn
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_barrier_state")
    conn.close()
    pg_barrier._local.conn = None


def _row(conn, execution_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT remaining, results FROM pg_barrier_state WHERE execution_id = %s",
            (execution_id,),
        )
        return cur.fetchone()


def _org(conn, execution_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT organization_id FROM pg_barrier_state WHERE execution_id = %s",
            (execution_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _expires_in_seconds(conn, execution_id):
    """Seconds from *now* until the barrier's expires_at (DB-side now(), so no
    client-clock skew) — the fixed 6h absolute cap.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (expires_at - now())) "
            "FROM pg_barrier_state WHERE execution_id = %s",
            (execution_id,),
        )
        return float(cur.fetchone()[0])


def _last_progress_age_seconds(conn, execution_id):
    """How long ago (DB-side) the barrier last made progress — the reaper's stuck
    signal (UN-3661). Small = fresh; large = stalled.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - last_progress_at)) "
            "FROM pg_barrier_state WHERE execution_id = %s",
            (execution_id,),
        )
        return float(cur.fetchone()[0])


class TestPgBarrierEnqueue:
    def test_upsert_creates_row_and_attaches_links(self, barrier_db):
        tasks = [_mock_header_task() for _ in range(3)]
        handle = PgBarrier().enqueue(
            [t for t, _ in tasks],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-A"},
            callback_queue="general",
            app_instance=None,
        )
        assert handle.id == "exec-A"
        assert _row(barrier_db, "exec-A") == (3, [])
        for _, cloned in tasks:
            cloned.link.assert_called_once()
            cloned.link_error.assert_called_once()
            cloned.apply_async.assert_called_once()

    def test_enqueue_sets_expires_cap_and_fresh_progress(self, barrier_db, monkeypatch):
        # enqueue stamps expires_at = now()+ttl (the absolute cap) AND
        # last_progress_at = now() (fresh), so a just-enqueued barrier is neither
        # expired nor stale. (UN-3661)
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "600")
        task, _ = _mock_header_task()
        PgBarrier().enqueue(
            [task],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-SD"},
            callback_queue="general",
            app_instance=None,
        )
        assert 590 <= _expires_in_seconds(barrier_db, "exec-SD") <= 600  # ~ttl cap
        assert _last_progress_age_seconds(barrier_db, "exec-SD") < 5  # fresh

    def test_enqueue_self_heals_on_stale_connection(self, barrier_db, monkeypatch):
        # End-to-end through enqueue(): the first barrier write hits a dead cached
        # conn; the fix must reconnect to the REAL db, land the row exactly once,
        # and still dispatch every header exactly once (no double-dispatch). This
        # pins the wiring — reverting enqueue() to the inline `with _cursor()`
        # would make this fail (the no-DB retry tests alone would not catch that).
        monkeypatch.setattr(pg_barrier.time, "sleep", lambda *_a, **_k: None)
        dead = _FakeConn(
            execute_error=psycopg2.OperationalError(
                "server closed the connection unexpectedly"
            )
        )
        pg_barrier._local.conn = (
            dead  # the barrier_db fixture's real conn is the reconnect target
        )
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: barrier_db)

        tasks = [_mock_header_task() for _ in range(3)]
        handle = PgBarrier().enqueue(
            [t for t, _ in tasks],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-HEAL"},
            callback_queue="general",
            app_instance=None,
        )

        assert handle.id == "exec-HEAL"
        assert dead.closed is True  # stale conn discarded by _cursor
        assert _row(barrier_db, "exec-HEAL") == (3, [])  # row landed once, remaining=N
        for _, cloned in tasks:  # every header dispatched exactly once
            cloned.apply_async.assert_called_once()

    def test_fairness_header_stamped(self, barrier_db):
        task, cloned = _mock_header_task()
        PgBarrier().enqueue(
            [task],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-F"},
            callback_queue="general",
            app_instance=None,
            fairness=FairnessKey(org_id="o", workload_type=WorkloadType.API),
        )
        headers = cloned.set.call_args.kwargs["headers"]
        assert FAIRNESS_HEADER_NAME in headers

    def test_upsert_overwrites_stale_state(self, barrier_db):
        # A prior run left a row at remaining=1 with results; the new enqueue
        # resets it.
        with barrier_db.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, organization_id, remaining, results, "
                " created_at, expires_at) "
                "VALUES ('exec-R', '', 1, '[1,2]'::jsonb, now(), "
                "        now() + interval '1h')"
            )
        task, _ = _mock_header_task()
        PgBarrier().enqueue(
            [task, _mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-R"},
            callback_queue="general",
            app_instance=None,
        )
        assert _row(barrier_db, "exec-R") == (2, [])

    def test_enqueue_stamps_organization_id(self, barrier_db):
        # The whole reason the org column + migration exist (reaper recovery).
        PgBarrier().enqueue(
            [_mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-ORG", "organization_id": "org-42"},
            callback_queue="general",
            app_instance=None,
        )
        assert _org(barrier_db, "exec-ORG") == "org-42"

    def test_enqueue_defaults_org_to_empty_when_absent(self, barrier_db):
        PgBarrier().enqueue(
            [_mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-NOORG"},  # no organization_id
            callback_queue="general",
            app_instance=None,
        )
        assert _org(barrier_db, "exec-NOORG") == ""

    def test_upsert_refreshes_org_on_reenqueue(self, barrier_db):
        # Exercises the ON CONFLICT DO UPDATE SET organization_id clause.
        with barrier_db.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, organization_id, remaining, results, "
                " created_at, expires_at) "
                "VALUES ('exec-REORG', 'old-org', 1, '[]'::jsonb, now(), "
                "        now() + interval '1h')"
            )
        PgBarrier().enqueue(
            [_mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-REORG", "organization_id": "new-org"},
            callback_queue="general",
            app_instance=None,
        )
        assert _org(barrier_db, "exec-REORG") == "new-org"

    def test_mid_loop_dispatch_failure_deletes_row(self, barrier_db):
        good, _ = _mock_header_task()
        bad, bad_cloned = _mock_header_task()
        bad_cloned.apply_async.side_effect = RuntimeError("broker down")
        with pytest.raises(RuntimeError):
            PgBarrier().enqueue(
                [good, bad],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-D"},
                callback_queue="general",
                app_instance=None,
            )
        assert _row(barrier_db, "exec-D") is None  # cleaned up


def _seed(conn, execution_id, remaining, *, results="[]"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pg_barrier_state "
            "(execution_id, organization_id, remaining, results, "
            " created_at, expires_at) "
            "VALUES (%s, '', %s, %s::jsonb, now(), now() + interval '1h')",
            (execution_id, remaining, results),
        )


class TestDecrAndCheck:
    def test_pending_decrements_only(self, barrier_db):
        _seed(barrier_db, "exec-P", 3)
        out = barrier_pg_decr_and_check(
            {"f": 1}, execution_id="exec-P", callback_descriptor=_CALLBACK
        )
        assert out["status"] == "pending"
        remaining, results = _row(barrier_db, "exec-P")
        assert remaining == 2
        assert results == [{"f": 1}]

    def test_decrement_refreshes_last_progress_at(self, barrier_db):
        # Each decrement re-stamps last_progress_at = now(), so a barrier that IS
        # making progress never goes stale (the reaper only reaps a stalled one).
        # Seed a STALE last_progress_at (as if about to be reaped) → decrement must
        # refresh it. (UN-3661)
        with barrier_db.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, organization_id, remaining, results, "
                " created_at, expires_at, last_progress_at) "
                "VALUES ('exec-SL', '', 2, '[]'::jsonb, "
                " now() - interval '1 hour', now() + interval '5 hours', "
                " now() - interval '1 hour')"
            )
        assert _last_progress_age_seconds(barrier_db, "exec-SL") > 3000  # ~1h stale
        barrier_pg_decr_and_check(
            {"f": 1}, execution_id="exec-SL", callback_descriptor=_CALLBACK
        )
        assert _last_progress_age_seconds(barrier_db, "exec-SL") < 5  # refreshed

    def test_idle_reaped_conn_self_heals_and_decrements_exactly_once(
        self, barrier_db, monkeypatch
    ):
        # End-to-end through the production entry (_barrier_pg_decrement): the
        # decrement's cached conn was idle-reaped and fails the first execute; the
        # phase-split retry reconnects to the REAL db and lands the decrement
        # EXACTLY once (2 → 1, not 2 → 0, and one result appended). Reverting
        # _apply_decrement to a plain `with _cursor()` makes this fail.
        monkeypatch.setattr(pg_barrier.time, "sleep", lambda *_a, **_k: None)
        _seed(barrier_db, "exec-HEALD", 2)
        dead = _FakeConn(
            execute_error=psycopg2.OperationalError(
                "server closed the connection unexpectedly"
            )
        )
        pg_barrier._local.conn = dead  # the barrier_db fixture conn is the target
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: barrier_db)

        out = _barrier_pg_decrement(
            {"f": "x"}, execution_id="exec-HEALD", callback_descriptor=_CALLBACK
        )

        assert out["status"] == "pending" and out["remaining"] == 1
        assert dead.closed is True  # stale conn discarded
        assert _row(barrier_db, "exec-HEALD") == (1, [{"f": "x"}])  # decremented once

    def test_pg_terminate_backend_mid_decrement_fires_callback_once(
        self, barrier_db, monkeypatch
    ):
        # The strongest pin: a REAL server-side connection kill (the
        # pg_terminate_backend analog of a PgBouncer idle-reap) mid-decrement. The
        # victim is a genuine non-autocommit connection (production posture); we
        # terminate its backend for real, then drive the decrement that takes the
        # barrier to 0. The phase-split retry must reconnect to live PG, land the
        # decrement EXACTLY once, and fire the callback EXACTLY once. A
        # double-count would drive remaining to -1 → "abandoned" → no callback, so
        # asserting "complete" + one signature call + row deleted proves
        # exactly-once against a real terminated socket.
        monkeypatch.setattr(pg_barrier.time, "sleep", lambda *_a, **_k: None)
        _seed(barrier_db, "exec-PTB", 1)  # last batch: decrement → 0 fires callback

        victim = create_pg_connection(env_prefix="TEST_DB_")  # non-autocommit
        with victim.cursor() as cur:
            cur.execute("SELECT pg_backend_pid()")
            victim_pid = cur.fetchone()[0]
        victim.rollback()  # return to IDLE so the decrement entry-guard passes
        pg_barrier._local.conn = victim  # the decrement uses this cached conn

        # Kill the victim's backend from the admin (fixture) connection — the
        # client still thinks it's open (conn.closed == 0), exactly like an idle
        # reap; the failure surfaces on the next statement (the decrement UPDATE).
        with barrier_db.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(%s)", (victim_pid,))
        # The retry reconnects via create_pg_connection; in tests that must target
        # the reachable TEST_DB_ (the bare DB_* host is the in-container name).
        monkeypatch.setattr(
            pg_barrier,
            "create_pg_connection",
            lambda **_k: create_pg_connection(env_prefix="TEST_DB_"),
        )

        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="cb-ptb")
            out = barrier_pg_decr_and_check(
                {"f": "x"}, execution_id="exec-PTB", callback_descriptor=_CALLBACK
            )

        assert out["status"] == "complete"  # reached 0 exactly once (not -1)
        sig.assert_called_once()  # callback fired exactly once
        assert _row(barrier_db, "exec-PTB") is None  # barrier torn down after fire
        assert victim.closed  # the terminated conn was discarded by the retry

    def test_complete_fires_callback_with_aggregated_results(self, barrier_db):
        _seed(barrier_db, "exec-C", 1, results='[{"f": "a"}]')
        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="cb-task-1")
            out = barrier_pg_decr_and_check(
                {"f": "b"}, execution_id="exec-C", callback_descriptor=_CALLBACK
            )
        assert out["status"] == "complete"
        # Callback got the full aggregated list as its first positional arg.
        assert sig.call_args.kwargs["args"] == [[{"f": "a"}, {"f": "b"}]]
        assert _row(barrier_db, "exec-C") is None  # row deleted after dispatch

    def test_complete_path_passes_fairness_header(self, barrier_db):
        _seed(barrier_db, "exec-FH", 1)
        descriptor = {**_CALLBACK, "fairness_headers": {FAIRNESS_HEADER_NAME: {"o": 1}}}
        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="cb")
            barrier_pg_decr_and_check(
                {"f": 1}, execution_id="exec-FH", callback_descriptor=descriptor
            )
        assert sig.call_args.kwargs["headers"] == {FAIRNESS_HEADER_NAME: {"o": 1}}

    def test_callback_dispatch_failure_preserves_row(self, barrier_db):
        # The central failure-masking invariant: dispatch happens BEFORE the row
        # is deleted, so an apply_async failure leaves the row in place (reclaimed
        # by expiry) — guards against a delete-before-dispatch reorder.
        _seed(barrier_db, "exec-CF", 1)
        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.side_effect = RuntimeError("broker down")
            with pytest.raises(RuntimeError):
                barrier_pg_decr_and_check(
                    {"f": 1}, execution_id="exec-CF", callback_descriptor=_CALLBACK
                )
        assert _row(barrier_db, "exec-CF") is not None  # row survives for TTL reclaim

    def test_list_result_appended_as_single_element(self, barrier_db):
        # jsonb_build_array() must append a list-shaped result as ONE element
        # (plain `||` would concatenate it). Guards that choice.
        _seed(barrier_db, "exec-L", 2)
        barrier_pg_decr_and_check(
            [1, 2], execution_id="exec-L", callback_descriptor=_CALLBACK
        )
        remaining, results = _row(barrier_db, "exec-L")
        assert remaining == 1
        assert results == [[1, 2]]  # one element that is the list, not [1, 2]

    def test_nul_byte_result_tears_down_barrier(self, barrier_db):
        # A NUL byte survives json.dumps but jsonb rejects it. The barrier must
        # be torn down (fail fast) rather than hang to expiry.
        _seed(barrier_db, "exec-NB", 1)
        with pytest.raises(psycopg2.DataError):
            barrier_pg_decr_and_check(
                {"f": "bad\x00value"},
                execution_id="exec-NB",
                callback_descriptor=_CALLBACK,
            )
        assert _row(barrier_db, "exec-NB") is None  # torn down, not left hanging

    def test_decrement_after_abort_does_not_fire(self, barrier_db):
        # The new failure-masking model: an aborted barrier is GONE (abort
        # deletes the row), so a late in-flight decrement finds no row and never
        # fires — even when it would otherwise have hit remaining == 0.
        _seed(barrier_db, "exec-DA", 1)
        barrier_pg_abort(execution_id="exec-DA")  # header failed → row deleted
        with patch("celery.current_app.signature") as sig:
            out = barrier_pg_decr_and_check(
                {"f": 1}, execution_id="exec-DA", callback_descriptor=_CALLBACK
            )
        assert out["status"] == "abandoned"
        sig.assert_not_called()

    def test_negative_remaining_does_not_fire(self, barrier_db):
        _seed(barrier_db, "exec-N", 0)  # decrement → -1
        with patch("celery.current_app.signature") as sig:
            out = barrier_pg_decr_and_check(
                {"f": 1}, execution_id="exec-N", callback_descriptor=_CALLBACK
            )
        assert out["status"] == "abandoned"
        sig.assert_not_called()
        assert _row(barrier_db, "exec-N") is None

    def test_missing_row_does_not_fire(self, barrier_db):
        with patch("celery.current_app.signature") as sig:
            out = barrier_pg_decr_and_check(
                {"f": 1}, execution_id="nope", callback_descriptor=_CALLBACK
            )
        assert out["status"] == "abandoned"
        sig.assert_not_called()

    def test_unserialisable_result_raises(self, barrier_db):
        _seed(barrier_db, "exec-U", 1)
        with pytest.raises(TypeError):
            barrier_pg_decr_and_check(
                {object()}, execution_id="exec-U", callback_descriptor=_CALLBACK
            )

    def test_registered_under_canonical_name(self):
        assert barrier_pg_decr_and_check.name == "barrier_pg_decr_and_check"


class TestDecrementCoreExtraction:
    """The decrement logic lives in a plain ``_barrier_pg_decrement`` core so the
    9e PR 2c PG-consumed path can call it in-body (a PG-consumed task fires no
    ``.link``). The Celery ``@worker_task`` is a thin delegator; both paths must
    share one implementation (no drift). (Inert in 2a — no PG caller yet.)
    """

    def test_core_is_a_plain_callable_not_a_celery_task(self):
        # A ``@worker_task`` exposes ``.name`` / ``.delay``; the in-body core
        # must not, or callers could accidentally re-dispatch instead of running.
        assert not hasattr(_barrier_pg_decrement, "name")
        assert not hasattr(_barrier_pg_decrement, "delay")

    def test_core_runs_the_decrement_in_body(self, barrier_db):
        # Called directly (no Celery), the core performs the atomic decrement.
        _seed(barrier_db, "exec-core", 3)
        out = _barrier_pg_decrement(
            {"f": 1}, execution_id="exec-core", callback_descriptor=_CALLBACK
        )
        assert out["status"] == "pending"
        remaining, results = _row(barrier_db, "exec-core")
        assert remaining == 2
        assert results == [{"f": 1}]

    def test_worker_task_produces_same_decrement_as_core(self, barrier_db):
        # The real no-drift guard: the wrapper, run against a real seeded row,
        # must produce the SAME observable decrement as a direct core call
        # (mirror of test_core_runs_the_decrement_in_body). Unlike the mocked
        # forwarding test below, this would catch a renamed/reordered core param
        # — the core is NOT mocked away.
        _seed(barrier_db, "exec-wrap", 3)
        out = barrier_pg_decr_and_check(
            {"f": 1}, execution_id="exec-wrap", callback_descriptor=_CALLBACK
        )
        assert out["status"] == "pending"
        remaining, results = _row(barrier_db, "exec-wrap")
        assert remaining == 2
        assert results == [{"f": 1}]

    def test_worker_task_forwards_kwargs_verbatim(self):
        # Complements the real-row test above by pinning the keyword-forwarding
        # contract explicitly: the wrapper passes result + execution_id +
        # callback_descriptor straight through, returning the core's result.
        sentinel = {"status": "pending", "remaining": 9}
        with patch.object(
            pg_barrier, "_barrier_pg_decrement", return_value=sentinel
        ) as core:
            out = barrier_pg_decr_and_check(
                {"f": 1}, execution_id="exec-d", callback_descriptor=_CALLBACK
            )
        assert out is sentinel
        core.assert_called_once_with(
            {"f": 1}, execution_id="exec-d", callback_descriptor=_CALLBACK
        )

    def test_open_transaction_on_shared_conn_raises(self):
        # The in-body contract is enforced loudly: a caller that enters with an
        # already-open transaction on the shared connection is rejected before
        # any decrement runs (would otherwise corrupt 'remaining' and hang the
        # barrier to expiry). Guards the 2c in-body caller.
        import psycopg2.extensions

        conn = MagicMock()
        conn.get_transaction_status.return_value = (
            psycopg2.extensions.TRANSACTION_STATUS_INTRANS
        )
        with patch.object(pg_barrier, "_get_conn", return_value=conn):
            with pytest.raises(RuntimeError, match="own committed transaction"):
                _barrier_pg_decrement(
                    {"f": 1}, execution_id="exec-tx", callback_descriptor=_CALLBACK
                )
        conn.cursor.assert_not_called()  # rejected before touching the DB


class TestAbort:
    def test_claims_and_deletes(self, barrier_db):
        _seed(barrier_db, "exec-X", 2)
        out = barrier_pg_abort(execution_id="exec-X")
        assert out["status"] == "aborted"
        assert _row(barrier_db, "exec-X") is None

    def test_concurrent_aborts_deduplicate(self, barrier_db):
        _seed(barrier_db, "exec-Y", 2)
        first = barrier_pg_abort(execution_id="exec-Y")
        second = barrier_pg_abort(execution_id="exec-Y")
        assert first["status"] == "aborted"
        assert second["status"] == "already_aborted"  # row gone / claim lost

    def test_registered_under_canonical_name(self):
        assert barrier_pg_abort.name == "barrier_pg_abort"

    def test_max_retries_zero(self):
        # A Celery retry would replay the decrement and corrupt the count.
        assert barrier_pg_decr_and_check.max_retries == 0
        assert barrier_pg_abort.max_retries == 0


# --- Layer 3: atomicity through the real task + DB constraint ---


class TestDecrementAtomicityThroughTask:
    def test_exactly_one_task_fires_the_callback(self, barrier_db):
        # Two header-task links decrement a remaining=2 barrier concurrently,
        # each through barrier_pg_decr_and_check itself (not raw SQL). The row
        # lock serialises them so exactly one returns "complete" and the callback
        # is dispatched exactly once — the real single-fire guarantee.
        import threading

        _seed(barrier_db, "exec-Z", 2)
        statuses: dict[str, str] = {}
        conns = []

        def run(label):
            conn = create_pg_connection(env_prefix="TEST_DB_")
            conn.autocommit = True
            conns.append(conn)
            pg_barrier._local.conn = conn  # this thread's own connection
            try:
                out = barrier_pg_decr_and_check(
                    {"t": label}, execution_id="exec-Z", callback_descriptor=_CALLBACK
                )
                statuses[label] = out["status"]
            finally:
                pg_barrier._local.conn = None

        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="cb")
            threads = [threading.Thread(target=run, args=(x,)) for x in ("a", "b")]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            assert all(not t.is_alive() for t in threads)
            assert sorted(statuses.values()) == ["complete", "pending"]
            assert sig.return_value.apply_async.call_count == 1  # single fire
        for c in conns:
            c.close()


class TestDbConstraint:
    def test_expires_at_must_exceed_created_at(self, barrier_db):
        # The one writer-proof invariant (workers SQL can't import the model).
        with pytest.raises(psycopg2.errors.CheckViolation):
            with barrier_db.cursor() as cur:
                cur.execute(
                    "INSERT INTO pg_barrier_state "
                    "(execution_id, organization_id, remaining, results, "
                    " created_at, expires_at) "
                    "VALUES ('bad', '', 1, '[]'::jsonb, now(), now())"  # expires==created
                )


class TestPgFireAndForgetMode:
    """9e PR 2c — PgBarrier's ``transport="pg_queue"`` fire-and-forget path:
    headers dispatched onto PG (no ``.link``), in-body claim + decrement, callback
    self-chained onto PG, and dedup-marker cleanup at enqueue/finalise/abort.
    """

    def test_enqueue_pg_mode_dispatches_headers_via_pg_with_context(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        # A header with a pre-existing kwarg, real args, and a queue — to prove
        # the Signature→dispatch unpacking preserves all three (a dropped args or
        # queue would silently process an empty/misrouted batch).
        h0 = _pg_header(args=[{"file": "f0"}], queue="api_file_processing")
        h0.kwargs = {"pre_existing": "keep"}
        h1 = _pg_header(args=[{"file": "f1"}], queue="api_file_processing")
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            PgBarrier().enqueue(
                [h0, h1],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-pg"},
                callback_queue="general",
                app_instance=None,
                transport="pg_queue",
            )
        assert mock_dispatch.call_count == 2  # one per header, no .link
        for i, call in enumerate(mock_dispatch.call_args_list):
            assert call.kwargs["backend"] is QueueBackend.PG
            assert call.kwargs["args"] == [{"file": f"f{i}"}]  # args preserved
            assert call.kwargs["queue"] == "api_file_processing"  # queue preserved
            ctx = call.kwargs["kwargs"]["_barrier_context"]
            assert ctx["execution_id"] == "exec-pg"
            assert ctx["batch_index"] == i
            assert ctx["callback_descriptor"]["transport"] == "pg_queue"
        # The pre-existing kwarg on h0 survives alongside the injected context.
        assert mock_dispatch.call_args_list[0].kwargs["kwargs"]["pre_existing"] == "keep"

    def test_enqueue_pg_mode_clears_stale_dedup_on_reuse(self, barrier_db):
        # greptile #2068: a re-enqueue with the same execution_id must wipe prior
        # dedup markers atomically with the barrier reset, else every claim_batch
        # returns False and the barrier hangs.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        claim_batch("exec-reuse", 0)
        claim_batch("exec-reuse", 1)
        with patch("queue_backend.dispatch.dispatch"):
            PgBarrier().enqueue(
                [_pg_header()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-reuse"},
                callback_queue="general",
                app_instance=None,
                transport="pg_queue",
            )
        with barrier_db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                ("exec-reuse",),
            )
            assert cur.fetchone()[0] == 0  # stale markers wiped by the UPSERT block

    def test_run_batch_with_barrier_first_delivery_runs_and_decrements(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-fd", 2)
        ctx = {
            "execution_id": "exec-fd",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }
        work = MagicMock(return_value={"ok": 1})
        out = run_batch_with_barrier(ctx, work)
        work.assert_called_once()
        assert out == {"ok": 1}
        remaining, results = _row(barrier_db, "exec-fd")
        assert remaining == 1
        assert results == [{"ok": 1}]

    def test_run_batch_with_barrier_redelivery_skips_work_and_decrement(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-re", 2)
        claim_batch("exec-re", 0)  # batch already claimed → this is a redelivery
        ctx = {
            "execution_id": "exec-re",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }
        work = MagicMock(return_value={"ok": 1})
        out = run_batch_with_barrier(ctx, work)
        work.assert_not_called()  # no reprocessing
        assert out["status"] == "skipped_redelivery"
        remaining, _ = _row(barrier_db, "exec-re")
        assert remaining == 2  # NOT decremented again

    def _dedup_count(self, conn, execution_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                (execution_id,),
            )
            return cur.fetchone()[0]

    def test_exception_marks_error_then_tears_down_keeping_markers(
        self, barrier_db, monkeypatch
    ):
        # Confirmed ERROR mark → safe to tear the barrier row down, but KEEP the
        # per-batch dedup marker so this message's redelivery is skipped by
        # claim_batch (not re-run wholesale).
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-err", 2)
        marked = []
        monkeypatch.setattr(
            pg_barrier,
            "_mark_execution_error_on_abort",
            lambda ctx, *, reason: marked.append(reason) or True,
        )
        ctx = {
            "execution_id": "exec-err",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }

        def boom():
            raise RuntimeError("batch failed")

        with pytest.raises(RuntimeError, match="batch failed"):
            run_batch_with_barrier(ctx, boom)
        assert marked  # execution marked ERROR before teardown
        # Row torn down (mirror chord abort) but the dedup marker survives.
        assert _row(barrier_db, "exec-err") is None
        assert self._dedup_count(barrier_db, "exec-err") == 1  # claim marker kept

    def test_exception_with_unconfirmed_mark_leaves_barrier_row(
        self, barrier_db, monkeypatch
    ):
        # ERROR mark NOT confirmed (backend down / no org) → the barrier row is the
        # reaper's only recovery handle, so it must be LEFT intact, not deleted.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-strand", 2)
        monkeypatch.setattr(
            pg_barrier,
            "_mark_execution_error_on_abort",
            lambda ctx, *, reason: False,
        )
        ctx = {
            "execution_id": "exec-strand",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }

        def boom():
            raise RuntimeError("batch failed")

        with pytest.raises(RuntimeError, match="batch failed"):
            run_batch_with_barrier(ctx, boom)
        # Barrier row preserved for the reaper (remaining untouched).
        remaining, _ = _row(barrier_db, "exec-strand")
        assert remaining == 2

    def test_fire_barrier_callback_pg_self_chains_via_dispatch(self):
        descriptor = {**_CALLBACK, "transport": "pg_queue"}
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb-1")
            cb_id = _fire_barrier_callback(descriptor, [{"r": 1}])
        assert cb_id == "pg-cb-1"
        assert mock_dispatch.call_args.kwargs["backend"] is QueueBackend.PG
        assert mock_dispatch.call_args.kwargs["args"] == [[{"r": 1}]]

    def test_fire_barrier_callback_pg_tags_transport_marker(self):
        # The PG callback carries the _pg_transport marker so the aggregating
        # callback can gate its at-least-once duplicate guard on it. The shared
        # descriptor must NOT be mutated (a copy is dispatched).
        descriptor = {**_CALLBACK, "transport": "pg_queue"}
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb")
            _fire_barrier_callback(descriptor, [{"r": 1}])
        dispatched = mock_dispatch.call_args.kwargs["kwargs"]
        assert dispatched.get(pg_barrier.PG_TRANSPORT_CALLBACK_KWARG) is True
        assert pg_barrier.PG_TRANSPORT_CALLBACK_KWARG not in descriptor["kwargs"]

    def test_fire_barrier_callback_legacy_omits_transport_marker(self):
        # The Celery .link path must NOT inject the marker → the callback's PG
        # guard stays a no-op on Celery (no redelivery to guard).
        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="celery-cb")
            _fire_barrier_callback(_CALLBACK, [{"r": 1}])
        passed = sig.call_args.kwargs["kwargs"]
        assert pg_barrier.PG_TRANSPORT_CALLBACK_KWARG not in passed

    def test_fire_barrier_callback_pg_carries_fairness(self):
        # greptile: the PG callback must ride the producer's org/priority (parity
        # with the Celery path), reconstructed from the stored fairness_headers.
        descriptor = {
            **_CALLBACK,
            "transport": "pg_queue",
            "fairness_headers": {
                FAIRNESS_HEADER_NAME: {
                    "org_id": "org-9",
                    "workload_type": "api",
                    "pipeline_priority": 8,
                }
            },
        }
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb")
            _fire_barrier_callback(descriptor, [{"r": 1}])
        fairness = mock_dispatch.call_args.kwargs["fairness"]
        assert fairness is not None
        assert fairness.org_id == "org-9"
        assert fairness.pipeline_priority == 8

    def test_fire_barrier_callback_pg_without_fairness_passes_none(self):
        # No producer key → None (dispatch writes neutral defaults), not a crash.
        descriptor = {**_CALLBACK, "transport": "pg_queue"}  # fairness_headers None
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb")
            _fire_barrier_callback(descriptor, [{"r": 1}])
        assert mock_dispatch.call_args.kwargs["fairness"] is None

    def test_fire_barrier_callback_legacy_uses_celery(self):
        # No backend marker → the .link-mode Celery dispatch (unchanged).
        with patch("celery.current_app.signature") as sig:
            sig.return_value.apply_async.return_value = MagicMock(id="celery-cb")
            cb_id = _fire_barrier_callback(_CALLBACK, [{"r": 1}])
        assert cb_id == "celery-cb"
        sig.assert_called_once()

    def test_abort_clears_dedup_markers(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-ab", 2)
        claim_batch("exec-ab", 0)
        barrier_pg_abort(execution_id="exec-ab")
        with barrier_db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                ("exec-ab",),
            )
            assert cur.fetchone()[0] == 0

    def test_abort_preserve_flag_keeps_dedup_markers(self, barrier_db):
        # preserve_dedup_markers=True (the in-body PG path): the barrier row is
        # still deleted, but the marker survives so a redelivered batch is skipped
        # by claim_batch rather than re-run wholesale.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-keep", 2)
        claim_batch("exec-keep", 0)
        barrier_pg_abort(execution_id="exec-keep", preserve_dedup_markers=True)
        assert _row(barrier_db, "exec-keep") is None  # barrier row still deleted
        with barrier_db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                ("exec-keep",),
            )
            assert cur.fetchone()[0] == 1  # marker preserved
        assert claim_batch("exec-keep", 0) is False  # redelivery would be skipped

    def test_last_batch_self_chains_callback_to_pg_and_cleans_up(self, barrier_db):
        # The PR's core promise, end to end: the batch that drives remaining → 0
        # self-chains the aggregating callback onto PG (backend=PG, args=[results])
        # and clears both the barrier row and the dedup markers.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-last", 1)  # this batch is the last → remaining → 0
        descriptor = {
            "task_name": "process_batch_callback_api",
            "kwargs": {"execution_id": "exec-last"},
            "queue": "api_file_processing_callback",
            "fairness_headers": None,
            "transport": "pg_queue",
        }
        ctx = {
            "execution_id": "exec-last",
            "batch_index": 0,
            "callback_descriptor": descriptor,
        }
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb")
            out = run_batch_with_barrier(ctx, lambda: {"successful_files": 1})
        assert out == {"successful_files": 1}
        # callback self-chained onto PG with the aggregated results
        assert mock_dispatch.call_args.kwargs["backend"] is QueueBackend.PG
        assert mock_dispatch.call_args.args[0] == "process_batch_callback_api"
        assert mock_dispatch.call_args.kwargs["args"] == [[{"successful_files": 1}]]
        # barrier row + dedup markers cleaned up at finalise
        assert _row(barrier_db, "exec-last") is None
        with barrier_db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                ("exec-last",),
            )
            assert cur.fetchone()[0] == 0

    def test_decrement_failure_aborts_barrier(self, barrier_db, monkeypatch):
        # #69: a decrement-side failure (after the work succeeded) must tear the
        # barrier down in-body — else the dedup marker is committed, redelivery is
        # blocked, and the barrier strands to expiry. With a confirmed ERROR mark
        # the row is torn down (same path as a work failure).
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-decfail", 2)
        monkeypatch.setattr(
            pg_barrier, "_mark_execution_error_on_abort", lambda ctx, *, reason: True
        )
        ctx = {
            "execution_id": "exec-decfail",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }
        with patch.object(
            pg_barrier, "_barrier_pg_decrement", side_effect=RuntimeError("decr boom")
        ):
            with pytest.raises(RuntimeError, match="decr boom"):
                run_batch_with_barrier(ctx, lambda: {"ok": 1})
        assert _row(barrier_db, "exec-decfail") is None  # barrier torn down

    def test_pg_mid_loop_dispatch_failure_deletes_row_and_clears_dedup(self, barrier_db):
        # The PG-branch counterpart of test_mid_loop_dispatch_failure_deletes_row:
        # a header PG-dispatch failure mid fan-out deletes the barrier row AND
        # reclaims dedup markers (greptile #2069) — an already-claimed earlier
        # header's marker would otherwise orphan, since the in-flight abort is a
        # no-op once the barrier row is gone.
        #
        # The marker must be claimed AFTER enqueue's UPSERT block (which wipes
        # stale markers for this execution_id) — else the assertion would pass on
        # the UPSERT, not the mid-loop clear under test. So the first dispatch
        # call claims it (a fast consumer on the PG path), the second fails.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")

        def dispatch_side_effect(*args, **kwargs):
            if not dispatch_side_effect.claimed:
                dispatch_side_effect.claimed = True
                claim_batch("exec-midfail", 0)  # marker created post-UPSERT
                return MagicMock(id="1")
            raise RuntimeError("broker down")

        dispatch_side_effect.claimed = False
        with patch("queue_backend.dispatch.dispatch", side_effect=dispatch_side_effect):
            with pytest.raises(RuntimeError, match="broker down"):
                PgBarrier().enqueue(
                    [_pg_header(), _pg_header()],
                    callback_task_name="process_batch_callback",
                    callback_kwargs={"execution_id": "exec-midfail"},
                    callback_queue="general",
                    app_instance=None,
                    transport="pg_queue",
                )
        assert _row(barrier_db, "exec-midfail") is None  # row deleted on failure
        with barrier_db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
                ("exec-midfail",),
            )
            # The marker existed post-UPSERT and was removed by the mid-loop
            # clear_execution_batches under test (not by the UPSERT reset).
            assert cur.fetchone()[0] == 0


class TestMarkExecutionErrorOnAbort:
    """``_mark_execution_error_on_abort`` — the in-body PG failure → terminal mark
    (no DB; the internal API client + mark helper are mocked).
    """

    def _ctx(self, *, org):
        kwargs = {"execution_id": "exec-1", "pipeline_id": "pipe-1"}
        if org is not None:
            kwargs["organization_id"] = org
        return {
            "execution_id": "exec-1",
            "batch_index": 0,
            "callback_descriptor": {**_CALLBACK, "kwargs": kwargs},
        }

    def test_no_org_returns_false_without_building_client(self, monkeypatch):
        # No org → can't call the org-scoped API; must NOT build a client or mark.
        built = MagicMock(side_effect=AssertionError("client built without org"))
        monkeypatch.setattr("shared.api.InternalAPIClient", built)
        assert (
            pg_barrier._mark_execution_error_on_abort(
                self._ctx(org=None), reason="batch 0 failed"
            )
            is False
        )

    def test_org_present_marks_error_and_returns_helper_result(self, monkeypatch):
        client = MagicMock(name="api_client")
        monkeypatch.setattr(
            "shared.api.InternalAPIClient", MagicMock(return_value=client)
        )
        mark = MagicMock(return_value=True)
        monkeypatch.setattr("queue_backend.pg_queue.recovery.mark_execution_error", mark)
        out = pg_barrier._mark_execution_error_on_abort(
            self._ctx(org="org-9"), reason="batch 0 failed"
        )
        assert out is True
        mark.assert_called_once()
        args, kwargs = mark.call_args
        assert args[0] is client
        assert args[1] == "exec-1"
        assert args[2] == "org-9"
        assert kwargs["error_message"] == "[pg-barrier-abort] batch 0 failed."

    def test_helper_false_propagates(self, monkeypatch):
        monkeypatch.setattr(
            "shared.api.InternalAPIClient", MagicMock(return_value=MagicMock())
        )
        monkeypatch.setattr(
            "queue_backend.pg_queue.recovery.mark_execution_error",
            MagicMock(return_value=False),
        )
        assert (
            pg_barrier._mark_execution_error_on_abort(self._ctx(org="org-9"), reason="x")
            is False
        )

    def test_client_build_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            "shared.api.InternalAPIClient",
            MagicMock(side_effect=RuntimeError("no config")),
        )
        assert (
            pg_barrier._mark_execution_error_on_abort(self._ctx(org="org-9"), reason="x")
            is False
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
