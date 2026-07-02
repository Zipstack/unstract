"""UN-3671: orchestration idempotency claim — the double-orchestration guard for
``async_execute_bin`` before replica scale-out.

Two layers:

1. **Gate + short-circuit** (no DB): the transport-gated
   ``_should_skip_duplicate_orchestration`` helper and the
   ``async_execute_bin_general`` no-op wiring, with ``claim_orchestration`` mocked.
2. **Claim primitive** (real Postgres): ``claim_orchestration`` against the
   ``pg_orchestration_claim`` table — skips if unreachable/unmigrated.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import psycopg2
import pytest
from general import tasks
from general.tasks import _should_skip_duplicate_orchestration
from queue_backend import pg_barrier
from queue_backend.pg_barrier import claim_orchestration
from queue_backend.pg_queue.connection import create_pg_connection

# --- Layer 1: transport-gated gate (no DB) ---


class TestOrchestrationGate:
    """``_should_skip_duplicate_orchestration`` — Celery never claims; on PG the
    first delivery proceeds and a duplicate skips.
    """

    def test_celery_transport_never_claims(self):
        # The whole guard is PG-only: on Celery it must not even consult the claim
        # (proves the Celery path is behaviorally untouched).
        with patch("general.tasks.claim_orchestration") as claim:
            assert _should_skip_duplicate_orchestration("e1", "celery") is False
            claim.assert_not_called()

    def test_pg_first_delivery_proceeds(self):
        with patch("general.tasks.claim_orchestration", return_value=True) as claim:
            assert _should_skip_duplicate_orchestration("e1", "pg_queue") is False
            claim.assert_called_once_with("e1")

    def test_pg_duplicate_delivery_skips(self):
        with patch("general.tasks.claim_orchestration", return_value=False):
            assert _should_skip_duplicate_orchestration("e1", "pg_queue") is True


class TestOrchestratorShortCircuit:
    """``async_execute_bin_general`` no-ops on a duplicate BEFORE any setup / arm /
    dispatch.
    """

    def test_duplicate_returns_skip_without_setup(self):
        # Exercise the REAL gate end-to-end: a PG duplicate (claim_orchestration
        # returns False) must short-circuit to the skip result before any setup /
        # barrier arm / dispatch — so no real DB is touched.
        #
        # The worker bootstraps ``async_execute_bin_general`` under a bare
        # ``tasks`` module object (a sys.path quirk), which is a DIFFERENT object
        # than ``from general import tasks``. So patch the claim in the task's OWN
        # globals (via the unwrapped function), not on our module alias — otherwise
        # the task would resolve the real claim and hit Postgres. Reaching the skip
        # dict is itself proof setup was never called (it runs after the gate).
        fn = tasks.async_execute_bin_general
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        with patch.dict(fn.__globals__, {"claim_orchestration": lambda _eid: False}):
            out = tasks.async_execute_bin_general(
                schema_name="org",
                workflow_id="wf",
                execution_id="e-dup",
                hash_values_of_files={},
                transport="pg_queue",
            )
        assert out == {
            "status": "skipped_duplicate_orchestration",
            "execution_id": "e-dup",
            "workflow_id": "wf",
        }


# --- Layer 2: claim_orchestration against real Postgres ---


@pytest.fixture
def claim_db():
    """Inject a real autocommit connection into pg_barrier's thread-local so
    ``claim_orchestration`` writes to the real ``pg_orchestration_claim`` table.
    """
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    try:
        conn = create_pg_connection(env_prefix="TEST_DB_")
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_orchestration_claim')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip(
                "pg_orchestration_claim migration not applied (run backend migrate)"
            )
        cur.execute("DELETE FROM pg_orchestration_claim")
    pg_barrier._local.conn = conn
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_orchestration_claim")
    conn.close()
    pg_barrier._local.conn = None


def _claim_count(conn, execution_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_orchestration_claim WHERE execution_id = %s",
            (execution_id,),
        )
        return cur.fetchone()[0]


@pytest.mark.integration
class TestClaimOrchestration:
    def test_first_claim_wins(self, claim_db):
        assert claim_orchestration("exec-1") is True

    def test_duplicate_claim_loses(self, claim_db):
        assert claim_orchestration("exec-1") is True
        assert claim_orchestration("exec-1") is False  # redelivery / sibling replica

    def test_distinct_executions_are_independent(self, claim_db):
        assert claim_orchestration("exec-1") is True
        assert claim_orchestration("exec-2") is True  # keyed on execution_id

    def test_claim_persists_as_tombstone(self, claim_db):
        # NOT cleared at finalise (unlike per-batch markers): a post-completion
        # redelivery still finds it, so a finished execution can't be re-orchestrated.
        assert claim_orchestration("exec-keep") is True
        assert _claim_count(claim_db, "exec-keep") == 1
        assert claim_orchestration("exec-keep") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
