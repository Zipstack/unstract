"""Add a partial index over UNDISPATCHED workflow executions.

Serves the undispatched-execution sweep (``workflow_v2/undispatched_sweep.py``), which
terminalises rows left ``PENDING`` because the request died between
``create_workflow_execution`` and ``execute_workflow_async`` — committed but never
queued, so no ``pg_barrier_state`` row exists and the reaper's barrier scan cannot see
them. Measured on integration 2026-08-17: 967 such rows from a single 5-minute load
test whose API tier shed 71% of its traffic.

The sweep runs every 5 minutes (``WORKER_PG_REAPER_SWEEP_SECONDS``) with::

    WHERE status = 'PENDING' AND created_at < now() - grace
      AND task_id IS NULL AND queue_message_id IS NULL

Design
------
* PARTIAL — the index covers only rows that are simultaneously PENDING and
  undispatched. In steady state that is ~ZERO rows: an execution leaves PENDING within
  seconds of creation, and one of ``task_id`` / ``queue_message_id`` is stamped the
  moment dispatch succeeds. So the index is effectively empty, costs almost nothing to
  maintain, and only grows when something is actually wrong.
* ``created_at`` as the indexed column — the sweep's only range predicate, and the
  ORDER BY for the batch limit.
* WHY A NEW INDEX AT ALL. ``we_active_by_workflow_idx`` (migration 0023) *is* usable
  here — ``status = 'PENDING'`` provably implies its ``NOT IN (terminal)`` predicate —
  so without this the fallback is a full scan of that (small) partial index rather than
  a table seq scan. That is survivable but planner-dependent and grows with the count
  of active executions. This makes it an exact index scan over a near-empty index.
* CONCURRENTLY + ``atomic = False`` — ``workflow_execution`` is a multi-million-row
  table in production; a plain ``AddIndex`` holds a SHARE lock for the whole build and
  blocks writes, i.e. blocks every execution in flight.
* FROZEN LITERAL — migrations must not import app enums, so ``'PENDING'`` is hardcoded.
  Drift against ``ExecutionStatus.PENDING`` is caught by
  ``tests/test_undispatched_execution_index.py`` (model/enum introspection only, no
  test DB), mirroring what ``test_active_execution_index.py`` does for 0023.
* INVALID-INDEX GUARD — ``IF NOT EXISTS`` silently no-ops over a leftover INVALID index
  from an interrupted CONCURRENTLY build, and Django would then record this migration as
  applied while the index is physically unusable (never read, write overhead only). The
  second statement RAISEs in that case, so the failure is loud rather than green-but-broken.

Deployment
----------
``CREATE INDEX CONCURRENTLY`` scans the table and can run for minutes on a large table —
long enough to time out a deploy's ``migrate`` step. Prefer building it OUT OF BAND
*before* the deploy; the migration then no-ops via ``IF NOT EXISTS``::

    CREATE INDEX CONCURRENTLY IF NOT EXISTS we_undispatched_idx
      ON workflow_execution (created_at)
      WHERE status = 'PENDING'
        AND task_id IS NULL
        AND queue_message_id IS NULL;

Then confirm the planner uses it (the partial-index proof depends on the literals
reaching the planner as constants)::

    EXPLAIN SELECT id, workflow_id FROM workflow_execution
      WHERE status = 'PENDING' AND created_at < now() - interval '15 minutes'
        AND task_id IS NULL AND queue_message_id IS NULL
      ORDER BY created_at LIMIT 500;
    -- expect: Index Scan using we_undispatched_idx

Recovery
--------
An interrupted build leaves an INVALID index that adds write overhead but is never read.
``IF NOT EXISTS`` will NOT rebuild over it (and the guard below RAISEs on it), so drop it
first and re-run::

    DROP INDEX CONCURRENTLY IF EXISTS we_undispatched_idx;
"""

from django.db import migrations, models
from django.db.models import Q

INDEX_NAME = "we_undispatched_idx"

# Frozen — see the FROZEN LITERAL note above.
PENDING_STATUS = "PENDING"

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

    dependencies = [("workflow_v2", "0025_workflow_workflow_org_modified_idx")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON workflow_execution (created_at) "
                        f"WHERE status = '{PENDING_STATUS}' "
                        "AND task_id IS NULL "
                        "AND queue_message_id IS NULL;"
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_VALID, reverse_sql=migrations.RunSQL.noop
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="workflowexecution",
                    index=models.Index(
                        fields=["created_at"],
                        name=INDEX_NAME,
                        condition=Q(
                            status=PENDING_STATUS,
                            task_id__isnull=True,
                            queue_message_id__isnull=True,
                        ),
                    ),
                ),
            ],
        ),
    ]
