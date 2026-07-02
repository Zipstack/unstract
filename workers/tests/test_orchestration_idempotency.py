"""UN-3671: orchestration idempotency claim — the double-orchestration guard for
``async_execute_bin`` before replica scale-out.

Two layers:

1. **Gate + short-circuit** (no DB): the transport-gated
   ``_should_skip_duplicate_orchestration`` helper and the
   ``async_execute_bin_general`` no-op wiring, with the claim primitive mocked.
2. **Claim primitive** (real Postgres): ``try_claim_orchestration`` /
   ``release_orchestration_claim`` against the ``pg_orchestration_claim`` table —
   skips if unreachable/unmigrated.
"""

from __future__ import annotations

import logging
import os
import threading
from unittest.mock import patch

import psycopg2
import pytest
from general import tasks
from general.tasks import _should_skip_duplicate_orchestration
from queue_backend import pg_barrier
from queue_backend.pg_barrier import (
    release_orchestration_claim,
    try_claim_orchestration,
)
from queue_backend.pg_queue.connection import create_pg_connection

# --- Layer 1: transport-gated gate (no DB) ---


class TestOrchestrationGate:
    """``_should_skip_duplicate_orchestration`` — Celery never claims; on PG the
    first delivery proceeds and a duplicate skips.
    """

    def test_celery_transport_never_claims(self):
        # The whole guard is PG-only: on Celery it must not even consult the claim
        # (proves the Celery path is behaviorally untouched).
        with patch("general.tasks.try_claim_orchestration") as claim:
            assert _should_skip_duplicate_orchestration("e1", "celery") is False
            claim.assert_not_called()

    def test_pg_first_delivery_proceeds(self):
        with patch("general.tasks.try_claim_orchestration", return_value=True) as claim:
            assert _should_skip_duplicate_orchestration("e1", "pg_queue") is False
            claim.assert_called_once_with("e1")

    def test_pg_duplicate_delivery_skips(self):
        with patch("general.tasks.try_claim_orchestration", return_value=False):
            assert _should_skip_duplicate_orchestration("e1", "pg_queue") is True

    def test_claim_error_propagates(self):
        # A DB error in the claim must PROPAGATE, not be swallowed — a swallow-and-
        # proceed would double-orchestrate, a swallow-and-skip would silently drop a
        # legitimate first delivery. Pin the no-try/except contract.
        with patch(
            "general.tasks.try_claim_orchestration",
            side_effect=psycopg2.OperationalError("db down"),
        ):
            with pytest.raises(psycopg2.OperationalError):
                _should_skip_duplicate_orchestration("e1", "pg_queue")

    def test_skip_on_retry_logs_error_with_errorid(self, caplog):
        # A skip when retries > 0 is a SUPPRESSED retry (a prior attempt claimed
        # and crashed before releasing), not a benign duplicate — log it at ERROR
        # with an errorId so alerting can distinguish the two.
        with patch("general.tasks.try_claim_orchestration", return_value=False):
            with caplog.at_level(logging.ERROR, logger="general.tasks"):
                assert _should_skip_duplicate_orchestration("e1", "pg_queue", 2) is True
        assert "ORCH_CLAIM_SUPPRESSED_RETRY" in caplog.text


class TestOrchestratorShortCircuit:
    """``async_execute_bin_general`` no-ops on a duplicate BEFORE any setup / arm /
    dispatch.
    """

    def test_duplicate_returns_skip_without_setup(self):
        # Exercise the REAL gate end-to-end: a PG duplicate (try_claim_orchestration
        # returns False) must short-circuit to the skip result before any setup /
        # barrier arm / dispatch. Reaching the skip dict is itself proof setup was
        # never called (it runs after the gate).
        #
        # Belt-and-braces: the worker *bootstrap* loads async_execute_bin_general
        # under a bare ``tasks`` module (a sys.path quirk) distinct from
        # ``general.tasks`` — that bootstrap doesn't run under pytest, so here
        # ``fn.__globals__`` IS ``general.tasks.__dict__`` and a plain
        # ``patch("general.tasks...")`` would also work. Patching the task's own
        # globals is simply robust to either loading.
        fn = tasks.async_execute_bin_general
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        with patch.dict(fn.__globals__, {"try_claim_orchestration": lambda _eid: False}):
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

    @staticmethod
    def _task_globals():
        fn = tasks.async_execute_bin_general
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        return fn.__globals__

    def test_no_release_when_claim_never_acquired(self):
        # G2: if the claim's own INSERT raises, the failure path must NOT call
        # release — nothing was acquired, and a spurious DELETE would reconnect just
        # to delete nothing and muddy the log.
        released: list[str] = []

        def _boom(_eid):
            raise psycopg2.OperationalError("db down")

        with patch.dict(
            self._task_globals(),
            {
                "try_claim_orchestration": _boom,
                "release_orchestration_claim": lambda eid: released.append(eid),
            },
        ):
            with pytest.raises(psycopg2.OperationalError):
                tasks.async_execute_bin_general(
                    schema_name="org",
                    workflow_id="wf",
                    execution_id="e-x",
                    hash_values_of_files={},
                    transport="pg_queue",
                )
        assert released == []  # claim never acquired → nothing released

    def test_release_called_when_claimed_and_work_fails(self):
        # The claim was won (gate proceeds) but the work fails → release it so the
        # redelivery/retry can re-orchestrate.
        released: list[str] = []
        with patch.dict(
            self._task_globals(),
            {
                "try_claim_orchestration": lambda _eid: True,  # won the claim
                "release_orchestration_claim": lambda eid: released.append(eid),
            },
        ):
            with patch.object(
                tasks.WorkerExecutionContext,
                "setup_execution_context",
                side_effect=RuntimeError("setup boom"),
            ):
                with pytest.raises(RuntimeError):
                    tasks.async_execute_bin_general(
                        schema_name="org",
                        workflow_id="wf",
                        execution_id="e-y",
                        hash_values_of_files={},
                        transport="pg_queue",
                    )
        assert released == ["e-y"]  # claimed then failed → released


# --- Layer 2: claim primitive against real Postgres ---


@pytest.fixture
def claim_db():
    """Inject a real autocommit connection into pg_barrier's thread-local so the
    claim primitives write to the real ``pg_orchestration_claim`` table.
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
        assert try_claim_orchestration("exec-1") is True

    def test_duplicate_claim_loses(self, claim_db):
        assert try_claim_orchestration("exec-1") is True
        assert try_claim_orchestration("exec-1") is False  # redelivery / sibling

    def test_distinct_executions_are_independent(self, claim_db):
        assert try_claim_orchestration("exec-1") is True
        assert try_claim_orchestration("exec-2") is True  # keyed on execution_id

    def test_claim_persists_as_tombstone(self, claim_db):
        # NOT cleared at finalise (unlike per-batch markers): a post-completion
        # redelivery still finds it, so a finished execution can't be re-orchestrated.
        assert try_claim_orchestration("exec-keep") is True
        assert _claim_count(claim_db, "exec-keep") == 1
        assert try_claim_orchestration("exec-keep") is False

    def test_release_allows_reclaim(self, claim_db):
        # The failure-path release frees the slot so a redelivery/retry can
        # re-orchestrate (this is what stops a transient failure permanently
        # no-oping every redelivery).
        assert try_claim_orchestration("exec-rel") is True
        assert try_claim_orchestration("exec-rel") is False  # held
        release_orchestration_claim("exec-rel")
        assert _claim_count(claim_db, "exec-rel") == 0
        assert try_claim_orchestration("exec-rel") is True  # reclaimable after release

    def test_release_is_safe_when_absent(self, claim_db):
        release_orchestration_claim("never-claimed")  # no row → no error
        assert _claim_count(claim_db, "never-claimed") == 0

    def test_concurrent_claims_resolve_to_exactly_one_winner(self, claim_db):
        # The real reason this feature exists: N replicas racing the SAME
        # orchestration must resolve to exactly one True. Force the contended
        # ON CONFLICT path — pre-build N connections and release every claim at
        # once via a threading.Barrier — and repeat over distinct executions so a
        # non-atomic check-then-insert can't pass by luck. Each thread uses its own
        # connection (a libpq conn is not thread-safe across threads).
        n = 8
        conns = [create_pg_connection(env_prefix="TEST_DB_") for _ in range(n)]
        for c in conns:
            c.autocommit = True
        try:
            for trial in range(5):
                execution_id = f"exec-race-{trial}"
                gate = threading.Barrier(n)
                results: list[bool] = []
                lock = threading.Lock()

                # Bind loop vars as defaults (ruff B023): threads are created and
                # joined within the iteration, but defaults make the capture explicit.
                def run(conn, eid=execution_id, gate=gate, results=results, lock=lock):
                    pg_barrier._local.conn = conn
                    try:
                        gate.wait()  # align all claims at the same instant
                        won = try_claim_orchestration(eid)
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
                assert _claim_count(claim_db, execution_id) == 1
        finally:
            for c in conns:
                c.close()
            pg_barrier._local.conn = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
