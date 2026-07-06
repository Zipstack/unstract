"""Schema-drift guard for the PG-queue tables the workers hit with raw SQL.

The workers speak to Postgres with **raw psycopg2 SQL, no Django ORM** — they run
in Docker decoupled from the backend by design, so they cannot import the models
as a source of truth. Column names therefore live as **string literals** across
``queue_backend/`` — ``queue_backend/pg_queue/*`` plus ``queue_backend/pg_barrier.py``
(the raw SQL for ``pg_barrier_state`` / ``pg_orchestration_claim`` lives there, one
directory up). A change in ``backend/pg_queue`` that renames or drops one of those
columns would NOT fail at import/compile time — only at runtime as a SQL error.

This DB-gated test closes that gap by asserting every column the workers depend on
still exists in the live schema. **Scope of enforcement:** it runs only against a
*migrated* Postgres — a dev machine with the ``pg_queue`` migration applied, or a CI
lane that provisions one and sets ``REQUIRE_PG_TESTS=1`` (conftest already turns the
``pg_conn`` skip into a failure there). The ``integration-workers`` CI lane is
currently ``optional`` and un-migrated, so ``pg_conn`` skips these there — wiring a
migrated lane is a follow-up. Until then, treat this as a dev/CI-lane guard, not a
production merge gate.

Semantics — **expected ⊆ actual**:
  * A renamed/removed column listed here → **fails** (the intended signal: update
    the raw SQL in ``queue_backend/`` and this contract together).
  * A newly *added* column → does **not** fail: the queue SQL uses explicit column
    lists (never ``SELECT *``), so a new column can't break a worker.

The manifest is the **full model mirror** of each queue-owned table (the workers
use ~all columns of these purpose-built tables; a couple — e.g.
``pg_periodic_schedule.created_at``/``updated_at`` — may not appear in any current
SQL, so the guard errs toward flagging any rename/removal on these tables for
review). Keep in sync only when a queue column is **renamed or removed**.
"""

import pytest
from queue_backend.pg_queue.schema import QUEUE_TABLES, queue_schema

# table -> columns the workers expect to exist (full model mirror; see module doc).
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


def _actual_columns(pg_conn, schema: str, table: str) -> set[str]:
    """Columns present for *schema.table* in the live DB.

    ``information_schema.columns`` is **privilege-filtered, not search_path-filtered**,
    so the schema is pinned explicitly: an unqualified ``table_name`` match would
    union columns from every visible schema (e.g. a stale per-developer sibling
    schema alongside ``unstract``) and mask a column dropped in the target schema.
    The schema is ``queue_schema()`` — exactly what the workers' ``qualified()`` SQL
    resolves to.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, table),
        )
        return {row[0] for row in cur.fetchall()}


def test_contract_covers_every_registered_queue_table():
    """The manifest must list exactly the tables the workers register in
    ``QUEUE_TABLES`` — so adding a queue table forces a column contract for it and
    the drift guard can never silently skip one."""
    assert set(WORKER_SCHEMA_CONTRACT) == set(QUEUE_TABLES)


@pytest.mark.parametrize("table", sorted(WORKER_SCHEMA_CONTRACT))
def test_worker_required_columns_exist(pg_conn, table):
    schema = queue_schema()  # the schema the workers' qualified() SQL targets
    actual = _actual_columns(pg_conn, schema, table)
    assert actual, f"{schema}.{table} not found in the live schema (migration applied?)"
    missing = WORKER_SCHEMA_CONTRACT[table] - actual
    assert not missing, (
        f"{schema}.{table} is missing worker-required column(s) {sorted(missing)}: a "
        f"model rename/removal in backend/pg_queue broke the workers' raw SQL. Update "
        f"the SQL in queue_backend/ and WORKER_SCHEMA_CONTRACT together."
    )
