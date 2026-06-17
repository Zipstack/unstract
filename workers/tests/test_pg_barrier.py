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
    barrier_pg_abort,
    barrier_pg_decr_and_check,
)
from queue_backend.pg_queue.connection import create_pg_connection

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
                "(execution_id, remaining, results, created_at, expires_at) "
                "VALUES ('exec-R', 1, '[1,2]'::jsonb, now(), now() + interval '1h')"
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
            "(execution_id, remaining, results, created_at, expires_at) "
            "VALUES (%s, %s, %s::jsonb, now(), now() + interval '1h')",
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
                    "(execution_id, remaining, results, created_at, expires_at) "
                    "VALUES ('bad', 1, '[]'::jsonb, now(), now())"  # expires == created
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
