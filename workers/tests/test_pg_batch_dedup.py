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

import psycopg2
import pytest
from queue_backend import pg_barrier
from queue_backend.pg_barrier import claim_batch, clear_execution_batches
from queue_backend.pg_queue.connection import create_pg_connection


@pytest.fixture
def dedup_db():
    import os

    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    try:
        conn = create_pg_connection(env_prefix="TEST_DB_")
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_batch_dedup')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_batch_dedup migration not applied (run backend migrate)")
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

    def test_concurrent_claims_resolve_to_exactly_one_winner(self, dedup_db):
        # The real at-least-once guarantee: two redeliveries racing on the same
        # batch must produce exactly one True (the row's existence is the token).
        # Each thread uses its own connection (a libpq conn is not thread-safe).
        import threading

        results: dict[str, bool] = {}
        conns = []

        def run(label):
            conn = create_pg_connection(env_prefix="TEST_DB_")
            conn.autocommit = True
            conns.append(conn)
            pg_barrier._local.conn = conn
            try:
                results[label] = claim_batch("exec-race", 0)
            finally:
                pg_barrier._local.conn = None

        threads = [threading.Thread(target=run, args=(f"t{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for c in conns:
            c.close()

        assert sum(1 for won in results.values() if won) == 1  # exactly one winner
        assert _count(dedup_db, "exec-race") == 1


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
