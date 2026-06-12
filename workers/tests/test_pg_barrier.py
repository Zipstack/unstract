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
    def test_default_is_six_hours(self, monkeypatch):
        monkeypatch.delenv("WORKER_BARRIER_KEY_TTL_SECONDS", raising=False)
        assert pg_barrier._ttl_seconds() == 6 * 60 * 60

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "120")
        assert pg_barrier._ttl_seconds() == 120

    @pytest.mark.parametrize("bad", ["abc", "0", "-5"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", bad)
        with pytest.raises(ValueError, match="WORKER_BARRIER_KEY_TTL_SECONDS"):
            pg_barrier._ttl_seconds()


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
            "SELECT remaining, results, aborted FROM pg_barrier_state "
            "WHERE execution_id = %s",
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
        remaining, results, aborted = _row(barrier_db, "exec-A")
        assert (remaining, results, aborted) == (3, [], False)
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
        # A prior run left a row at remaining=1, aborted; the new enqueue resets.
        with barrier_db.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, remaining, results, aborted, created_at, expires_at) "
                "VALUES ('exec-R', 1, '[1,2]'::jsonb, true, now(), now() + interval '1h')"
            )
        task, _ = _mock_header_task()
        PgBarrier().enqueue(
            [task, _mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-R"},
            callback_queue="general",
            app_instance=None,
        )
        assert _row(barrier_db, "exec-R") == (2, [], False)

    def test_opportunistic_expiry_sweep(self, barrier_db):
        with barrier_db.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, remaining, results, aborted, created_at, expires_at) "
                "VALUES ('exec-old', 5, '[]'::jsonb, false, now(), now() - interval '1s')"
            )
        PgBarrier().enqueue(
            [_mock_header_task()[0]],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-new"},
            callback_queue="general",
            app_instance=None,
        )
        assert _row(barrier_db, "exec-old") is None  # swept

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


def _seed(conn, execution_id, remaining, *, aborted=False, results="[]"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pg_barrier_state "
            "(execution_id, remaining, results, aborted, created_at, expires_at) "
            "VALUES (%s, %s, %s::jsonb, %s, now(), now() + interval '1h')",
            (execution_id, remaining, results, aborted),
        )


class TestDecrAndCheck:
    def test_pending_decrements_only(self, barrier_db):
        _seed(barrier_db, "exec-P", 3)
        out = barrier_pg_decr_and_check(
            {"f": 1}, execution_id="exec-P", callback_descriptor=_CALLBACK
        )
        assert out["status"] == "pending"
        remaining, results, _ = _row(barrier_db, "exec-P")
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

    def test_aborted_does_not_fire(self, barrier_db):
        _seed(barrier_db, "exec-AB", 1, aborted=True)
        with patch("celery.current_app.signature") as sig:
            out = barrier_pg_decr_and_check(
                {"f": 1}, execution_id="exec-AB", callback_descriptor=_CALLBACK
            )
        assert out["status"] == "aborted"
        sig.assert_not_called()
        assert _row(barrier_db, "exec-AB") is None

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


# --- Layer 3: atomicity (two connections race the decrement SQL) ---


class TestDecrementAtomicity:
    def test_exactly_one_reader_sees_zero(self, barrier_db):
        # Two header tasks both decrement a remaining=2 barrier concurrently;
        # the row lock serialises them so exactly one observes remaining == 0.
        _seed(barrier_db, "exec-Z", 2)
        conn_b = create_pg_connection(env_prefix="TEST_DB_")
        conn_b.autocommit = True
        sql = (
            "UPDATE pg_barrier_state "
            "SET remaining = remaining - 1 WHERE execution_id = %s "
            "RETURNING remaining"
        )
        try:
            with barrier_db.cursor() as cur_a, conn_b.cursor() as cur_b:
                cur_a.execute(sql, ("exec-Z",))
                a = cur_a.fetchone()[0]
                cur_b.execute(sql, ("exec-Z",))
                b = cur_b.fetchone()[0]
        finally:
            conn_b.close()
        assert sorted([a, b]) == [0, 1]  # exactly one zero, no double-zero


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
