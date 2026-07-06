"""Schema-drift guard for the PG-queue tables the workers hit with raw SQL.

The workers speak to Postgres with **raw psycopg2 SQL, no Django ORM** — they run
in Docker decoupled from the backend by design, so they cannot import the models
as a source of truth. Column names therefore live as **string literals** across
``queue_backend/pg_queue/*``. A change in ``backend/pg_queue`` that renames or
drops one of those columns would NOT fail at import/compile time — it would only
surface at runtime as a SQL error.

This DB-gated test closes that gap: it asserts every column the workers depend on
still exists in the live schema, so a model rename/removal fails in CI instead of
in production.

Semantics — **expected ⊆ actual**:
  * A renamed/removed column that the workers use → **fails** (the intended
    signal: update the raw SQL in ``queue_backend/pg_queue/`` and this contract).
  * A newly *added* column → does **not** fail: the queue SQL uses explicit
    column lists (never ``SELECT *``), so a new column can't break a worker.

Mirror of the ``backend/pg_queue`` models (the queue owns these tables). Keep in
sync only when a queue column is **renamed or removed** — that is exactly the
drift this guard is here to catch.
"""

import pytest
from queue_backend.pg_queue.schema import QUEUE_TABLES

# table -> columns the workers' raw SQL relies on.
WORKER_SCHEMA_CONTRACT = {
    "pg_queue_message": {
        "msg_id",
        "queue_name",
        "message",
        "org_id",
        "enqueued_at",
        "vt",
        "read_ct",
        "priority",
    },
    "pg_task_result": {
        "task_id",
        "status",
        "result",
        "error",
        "created_at",
        "expires_at",
    },
    "pg_barrier_state": {
        "execution_id",
        "organization_id",
        "remaining",
        "results",
        "created_at",
        "expires_at",
        "last_progress_at",
    },
    "pg_batch_dedup": {"execution_id", "batch_index", "created_at"},
    "pg_orchestration_claim": {"execution_id", "organization_id", "claimed_at"},
    "pg_orchestrator_lock": {"id", "leader", "acquired_at"},
    "pg_periodic_schedule": {
        "pipeline_id",
        "organization_id",
        "workflow_id",
        "pipeline_name",
        "cron_string",
        "enabled",
        "pg_owned",
        "last_run_at",
        "next_run_at",
        "created_at",
        "updated_at",
    },
}


def _actual_columns(pg_conn, table: str) -> set[str]:
    """Columns present for *table* in the live schema (search-path resolved, so it
    matches how the workers' unqualified/qualified SQL sees the table)."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def test_contract_covers_every_registered_queue_table():
    """The manifest must list exactly the tables the workers register in
    ``QUEUE_TABLES`` — so adding a queue table forces a column contract for it and
    the drift guard can never silently skip one."""
    assert set(WORKER_SCHEMA_CONTRACT) == set(QUEUE_TABLES)


@pytest.mark.parametrize("table", sorted(WORKER_SCHEMA_CONTRACT))
def test_worker_required_columns_exist(pg_conn, table):
    actual = _actual_columns(pg_conn, table)
    assert actual, f"{table} not found in the live schema (migration applied?)"
    missing = WORKER_SCHEMA_CONTRACT[table] - actual
    assert not missing, (
        f"{table} is missing worker-required column(s) {sorted(missing)}: a model "
        f"rename/removal in backend/pg_queue broke the workers' raw SQL. Update the "
        f"SQL in queue_backend/pg_queue/ and WORKER_SCHEMA_CONTRACT together."
    )
