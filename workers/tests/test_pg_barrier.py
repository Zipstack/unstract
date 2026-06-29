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


class _FakeCursorCtx:
    def __init__(self, on_execute):
        self._on_execute = on_execute

    def __enter__(self):
        cur = MagicMock(name="cursor")
        cur.execute.side_effect = self._on_execute
        return cur

    def __exit__(self, *exc):
        return False


class _FakeConn:
    """Minimal psycopg2-connection stub. ``execute_error`` (if set) is raised by
    every cursor.execute on this connection — simulating a stale/dead socket.
    """

    def __init__(self, *, execute_error=None):
        self.closed = False
        self._execute_error = execute_error
        self.commits = 0
        self.rollbacks = 0
        self.executes = 0

    def cursor(self):
        def _on_execute(*_a, **_k):
            self.executes += 1
            if self._execute_error is not None:
                raise self._execute_error

        return _FakeCursorCtx(_on_execute)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def _clean_local():
    """Ensure the module thread-local connection is reset around each test."""
    pg_barrier._local.conn = None
    yield
    pg_barrier._local.conn = None


class TestIdempotentWriteRetry:
    """`_run_idempotent_write` self-heals a stale cached connection with ONE
    retry — the fix for the `server closed the connection unexpectedly` abort at
    barrier enqueue. It must retry ONLY on connection errors, stay bounded, and
    never silently swallow a real (non-connection) failure.
    """

    def test_retries_once_on_dead_connection_then_succeeds(
        self, _clean_local, monkeypatch
    ):
        dead = _FakeConn(
            execute_error=psycopg2.OperationalError(
                "server closed the connection unexpectedly"
            )
        )
        healthy = _FakeConn()
        pg_barrier._local.conn = dead
        # On reconnect (_cursor discarded the dead conn), hand back the healthy one.
        monkeypatch.setattr(pg_barrier, "create_pg_connection", lambda **_k: healthy)

        attempts = []

        def op(cur):
            attempts.append(1)
            cur.execute("UPSERT ...", ("x",))

        pg_barrier._run_idempotent_write(op, what="test")

        assert len(attempts) == 2  # first failed mid-execute, retry succeeded
        assert dead.closed is True  # stale conn discarded
        assert healthy.commits == 1  # committed exactly once, on the retry
        assert pg_barrier._local.conn is healthy

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
            pg_barrier._run_idempotent_write(op, what="test")
        assert reconnects == []  # a real error must surface immediately, no retry

    def test_reraises_after_exhausting_attempts(self, _clean_local, monkeypatch):
        err = psycopg2.OperationalError("still down")
        # Every connection (initial + reconnect) is dead → both attempts fail.
        monkeypatch.setattr(
            pg_barrier, "create_pg_connection", lambda **_k: _FakeConn(execute_error=err)
        )

        with pytest.raises(psycopg2.OperationalError, match="still down"):
            pg_barrier._run_idempotent_write(lambda cur: cur.execute("X"), what="test")


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

    def test_run_batch_with_barrier_exception_aborts_barrier(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-err", 2)
        ctx = {
            "execution_id": "exec-err",
            "batch_index": 0,
            "callback_descriptor": _CALLBACK,
        }

        def boom():
            raise RuntimeError("batch failed")

        with pytest.raises(RuntimeError, match="batch failed"):
            run_batch_with_barrier(ctx, boom)
        # No .link_error on the PG path → torn down in-body (mirror chord abort).
        assert _row(barrier_db, "exec-err") is None

    def test_fire_barrier_callback_pg_self_chains_via_dispatch(self):
        descriptor = {**_CALLBACK, "transport": "pg_queue"}
        with patch("queue_backend.dispatch.dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(id="pg-cb-1")
            cb_id = _fire_barrier_callback(descriptor, [{"r": 1}])
        assert cb_id == "pg-cb-1"
        assert mock_dispatch.call_args.kwargs["backend"] is QueueBackend.PG
        assert mock_dispatch.call_args.kwargs["args"] == [[{"r": 1}]]

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

    def test_decrement_failure_aborts_barrier(self, barrier_db):
        # #69: a decrement-side failure (after the work succeeded) must tear the
        # barrier down in-body — else the dedup marker is committed, redelivery is
        # blocked, and the barrier strands to expiry.
        with barrier_db.cursor() as cur:
            cur.execute("DELETE FROM pg_batch_dedup")
        _seed(barrier_db, "exec-decfail", 2)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
