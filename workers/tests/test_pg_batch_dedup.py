"""Per-batch idempotency markers (9e PR 2b) — ``claim_batch`` /
``clear_execution_batches`` against the real ``pg_batch_dedup`` table.

The PG queue is at-least-once, so ``process_file_batch`` can be redelivered; the
marker makes the barrier decrement fire exactly once per ``(execution_id,
batch_index)``. These tests pin the claim's check-and-set semantics (incl. a
concurrent race) and the teardown cleanup. Inert in 2b — PR 2c wires them into
the batch task / barrier-finalise path.

The fixture mirrors ``test_pg_barrier``'s ``barrier_db``: a real autocommit
connection injected into pg_barrier's thread-local (the helpers live there to
share the one connection per worker child). Skips if Postgres is unreachable or
the 0006 migration is unapplied.
"""

from __future__ import annotations

import os

import psycopg2
import pytest
from queue_backend import pg_barrier
from queue_backend.pg_barrier import claim_batch, clear_execution_batches
from queue_backend.pg_queue.connection import create_pg_connection


def _skip_or_fail(reason: str) -> None:
    """Skip when Postgres isn't available — UNLESS ``REQUIRE_PG_TESTS`` is set
    (CI where PG is expected), where a skip would silently ship the idempotency
    primitive untested, so we fail loudly instead.
    """
    if os.getenv("REQUIRE_PG_TESTS"):
        pytest.fail(f"REQUIRE_PG_TESTS set but PG unusable: {reason}")
    pytest.skip(reason)


@pytest.fixture
def dedup_db():
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    try:
        conn = create_pg_connection(env_prefix="TEST_DB_")
    except psycopg2.OperationalError as exc:
        _skip_or_fail(f"Postgres not reachable: {exc}")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_batch_dedup')")
        if cur.fetchone()[0] is None:
            conn.close()
            _skip_or_fail("pg_batch_dedup migration not applied (run backend migrate)")
        cur.execute("DELETE FROM pg_batch_dedup")
    pg_barrier._local.conn = conn
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_batch_dedup")
    conn.close()
    pg_barrier._local.conn = None


def _count(conn, execution_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
            (execution_id,),
        )
        return cur.fetchone()[0]


class TestClaimBatch:
    def test_first_claim_succeeds(self, dedup_db):
        assert claim_batch("exec-1", 0) is True
        assert _count(dedup_db, "exec-1") == 1

    def test_redelivery_of_same_batch_is_rejected(self, dedup_db):
        assert claim_batch("exec-1", 0) is True
        # Same (execution_id, batch_index) again = a redelivery → skip.
        assert claim_batch("exec-1", 0) is False
        assert _count(dedup_db, "exec-1") == 1  # no duplicate row

    def test_different_batch_index_is_a_distinct_claim(self, dedup_db):
        assert claim_batch("exec-1", 0) is True
        assert claim_batch("exec-1", 1) is True  # sibling batch, independent
        assert _count(dedup_db, "exec-1") == 2

    def test_same_batch_index_different_execution_is_distinct(self, dedup_db):
        assert claim_batch("exec-1", 0) is True
        assert claim_batch("exec-2", 0) is True  # the key is the (exec, idx) pair
        assert _count(dedup_db, "exec-1") == 1
        assert _count(dedup_db, "exec-2") == 1

    def test_negative_batch_index_is_rejected_by_db(self, dedup_db):
        # batch_index is a non-negative ordinal; the CheckConstraint is
        # writer-proof even though claim_batch's callers only pass >= 0.
        with pytest.raises(psycopg2.errors.CheckViolation):
            claim_batch("exec-neg", -1)

    def test_concurrent_claims_resolve_to_exactly_one_winner(self, dedup_db):
        # The real at-least-once guarantee: N redeliveries racing on the SAME
        # batch must produce exactly one True (the row's existence is the token).
        # To actually force the contended ON CONFLICT path (not let a fast first
        # thread connect+commit before the others start), pre-build all N
        # connections in the main thread and release every claim simultaneously
        # via a threading.Barrier. Repeat over several distinct batches so a flaky
        # non-atomic check-then-insert can't pass by luck. Each thread uses its
        # own connection (a libpq conn is not thread-safe across threads).
        import threading

        n = 8
        conns = [create_pg_connection(env_prefix="TEST_DB_") for _ in range(n)]
        for c in conns:
            c.autocommit = True
        try:
            for trial in range(5):
                batch_index = trial  # a fresh, uncontended-so-far batch each round
                gate = threading.Barrier(n)
                results: list[bool] = []
                lock = threading.Lock()

                # Bind loop vars as defaults (ruff B023): the threads are created
                # and joined within this iteration, but defaults make the capture
                # explicit and lint-clean.
                def run(conn, bi=batch_index, gate=gate, results=results, lock=lock):
                    pg_barrier._local.conn = conn
                    try:
                        gate.wait()  # align all claims at the same instant
                        won = claim_batch("exec-race", bi)
                        with lock:
                            results.append(won)
                    finally:
                        pg_barrier._local.conn = None

                threads = [threading.Thread(target=run, args=(c,)) for c in conns]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                assert sum(results) == 1, f"trial {trial}: {sum(results)} winners"
                assert _count(dedup_db, "exec-race") == trial + 1
        finally:
            for c in conns:
                c.close()


class TestClearExecutionBatches:
    def test_clears_only_the_target_execution(self, dedup_db):
        claim_batch("exec-keep", 0)
        claim_batch("exec-drop", 0)
        claim_batch("exec-drop", 1)

        removed = clear_execution_batches("exec-drop")

        assert removed == 2  # both of exec-drop's markers
        assert _count(dedup_db, "exec-drop") == 0
        assert _count(dedup_db, "exec-keep") == 1  # untouched

    def test_clear_with_no_rows_returns_zero(self, dedup_db):
        assert clear_execution_batches("never-claimed") == 0

    def test_cleared_batch_can_be_reclaimed(self, dedup_db):
        # After teardown clears the markers, a fresh execution reusing the same
        # id (or a re-run) can claim again — the gate is per live execution.
        assert claim_batch("exec-1", 0) is True
        assert claim_batch("exec-1", 0) is False
        clear_execution_batches("exec-1")
        assert claim_batch("exec-1", 0) is True  # claimable again post-cleanup


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
