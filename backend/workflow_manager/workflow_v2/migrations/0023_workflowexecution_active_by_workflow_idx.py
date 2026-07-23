"""Add a partial index over ACTIVE workflow executions.

Speeds up the hot "is there an in-flight execution of this workflow?" lookup
(``_get_active_workflow_executions`` in ``endpoint_v2/source.py`` and the worker's
``get_workflow_executions_by_status``), which runs
``WHERE workflow_id = … AND status IN ('PENDING', 'EXECUTING')`` per file /
execution. The existing ``(workflow_id, created_at)`` index returns *all* of a
workflow's executions (99%+ terminal history) and then filters down to the 1-2
active rows — a cost that grows without bound as a workflow accumulates history.

Measured once at authoring on a 35k-execution workflow (figures illustrative,
as-measured): ~44x fewer rows scanned (the index walks the active rows, not all
34,913) and 21ms -> 1.4ms latency per call. Production workflows reach 100k+.

Design
------
* PARTIAL — the index only covers non-terminal rows, so it stays tiny (a few
  thousand active rows regardless of table size) and its cost is independent of
  history. On a ~3M-row table it is ~2 MB vs ~20 MB for a full
  ``(workflow_id, status)`` composite.
* COMPLEMENT PREDICATE (``status NOT IN (terminal)``) rather than a frozen
  ``status IN ('PENDING', 'EXECUTING')`` list. This is an *index-level* property:
  a query for any subset of non-terminal statuses still provably implies
  ``NOT IN (terminal)``, so the index stays usable if a new *active* status
  (e.g. a future PAUSE) is added. It does NOT make a new active status work
  end-to-end — the callers use a frozen positive ``status IN ('PENDING',
  'EXECUTING')`` list, so such a row is *indexed* but not *returned* until every
  caller's list is updated too. Only a new *terminal* status requires touching
  this predicate.
* CONCURRENTLY + ``atomic = False`` — builds without a write lock, so live
  execution traffic is not blocked. ``workflow_execution`` is a large
  (multi-million-row) table in production; a plain ``AddIndex`` would hold a SHARE
  lock and block writes for the full build.
* INVALID-INDEX GUARD — ``IF NOT EXISTS`` would silently no-op over a leftover
  INVALID index from a prior interrupted CONCURRENTLY build, and Django would then
  record this migration as applied while the index is physically unusable
  (never read, only write overhead). The second statement RAISEs in that case so
  the failure is loud instead of green-but-broken.

Deployment
----------
``CREATE INDEX CONCURRENTLY`` scans the whole table (twice) and can run for several
minutes on a large table — long enough to time out a deploy's ``migrate`` step.
Prefer building the index OUT OF BAND *before* the deploy; the migration then
becomes a no-op via ``IF NOT EXISTS``::

    CREATE INDEX CONCURRENTLY IF NOT EXISTS we_active_by_workflow_idx
      ON workflow_execution (workflow_id)
      WHERE status NOT IN ('COMPLETED', 'STOPPED', 'ERROR');

After building, verify the planner actually chooses it — the partial-index proof
depends on the ``status`` values reaching the planner as constants, so re-verify
if the DB driver is ever changed (e.g. a psycopg3 server-side-binding move)::

    EXPLAIN SELECT * FROM workflow_execution
      WHERE workflow_id = '…' AND status IN ('PENDING', 'EXECUTING');
    -- expect: Index Scan using we_active_by_workflow_idx

Recovery
--------
An interrupted ``CREATE INDEX CONCURRENTLY`` leaves an INVALID index that still
adds write overhead but is not used for reads. ``IF NOT EXISTS`` will NOT rebuild
over it (and the guard below RAISEs on it), so recover by dropping it first, then
re-running the migration::

    DROP INDEX CONCURRENTLY IF EXISTS we_active_by_workflow_idx;
"""

from django.db import migrations, models
from django.db.models import Q

INDEX_NAME = "we_active_by_workflow_idx"

# Terminal ExecutionStatus values (COMPLETED, STOPPED, ERROR). Kept as literals —
# migrations must not import app enums, so they stay frozen if the enum changes.
# The model-side copy (WorkflowExecution.Meta.indexes) is asserted against
# ExecutionStatus.terminal_values() by tests/test_active_execution_index.py so it
# cannot silently drift. Update ONLY for a new *terminal* status.
TERMINAL_STATUSES = ["COMPLETED", "STOPPED", "ERROR"]

# Fail loudly if a prior interrupted CONCURRENTLY build left an INVALID index of
# this name: the IF NOT EXISTS above would otherwise silently keep it and Django
# would record this migration as applied while the index is physically unusable.
_ASSERT_INDEX_VALID = f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_index i ON i.indexrelid = c.oid
        WHERE c.relname = '{INDEX_NAME}' AND NOT i.indisvalid
    ) THEN
        RAISE EXCEPTION 'Index {INDEX_NAME} exists but is INVALID (a prior CREATE INDEX CONCURRENTLY was interrupted). Drop it and re-run: DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};';
    END IF;
END
$$;
"""


class Migration(migrations.Migration):
    # CREATE / DROP INDEX CONCURRENTLY cannot run inside a transaction block.
    atomic = False

    dependencies = [
        ("workflow_v2", "0022_merge_20260626_1131"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Build the real index safely: lock-free (CONCURRENTLY), idempotent
                # (IF [NOT] EXISTS), a no-op if it was created out of band first.
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON workflow_execution (workflow_id) "
                        "WHERE status NOT IN ('COMPLETED', 'STOPPED', 'ERROR');"
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                # Guard: turn a masked INVALID index (from a prior failed build)
                # into a loud failure instead of a green-but-unused index.
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_VALID,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            # Keep Django's model state aware of the index (mirrors Meta.indexes on
            # WorkflowExecution) so future makemigrations does not re-add/remove it.
            state_operations=[
                migrations.AddIndex(
                    model_name="workflowexecution",
                    index=models.Index(
                        fields=["workflow_id"],
                        name=INDEX_NAME,
                        condition=~Q(status__in=TERMINAL_STATUSES),
                    ),
                ),
            ],
        ),
    ]
