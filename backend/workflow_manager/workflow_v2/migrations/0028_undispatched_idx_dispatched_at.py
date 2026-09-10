"""Re-key the undispatched partial index on ``dispatched_at``.

0027 added the column and explains why the inference it replaces was unsound. This
swaps the index that serves the sweep so the new predicate stays an index scan rather
than degrading to a sequential scan of a multi-million-row table.

The sweep now runs::

    WHERE status = 'PENDING' AND created_at < now() - grace
      AND dispatched_at IS NULL
      AND task_id IS NULL AND queue_message_id IS NULL

The handle checks are KEPT deliberately — see 0027 for why they are what make the
rollout single-phase — so the index condition carries all three.

Ordering matters here. The NEW index is created before the OLD one is dropped, so the
predicate is served throughout: a deploy that is interrupted between the two operations
leaves both present, which costs a little write overhead and nothing else. Dropping
first would leave the sweep unindexed for the length of the build.

Same operational rules as 0026, which this mirrors:

* ``atomic = False`` — CREATE / DROP INDEX CONCURRENTLY cannot run in a transaction.
* Prefer building OUT OF BAND before the deploy; ``IF NOT EXISTS`` then no-ops::

      CREATE INDEX CONCURRENTLY IF NOT EXISTS we_undispatched_dispatch_idx
        ON workflow_execution (created_at)
        WHERE status = 'PENDING'
          AND dispatched_at IS NULL
          AND task_id IS NULL
          AND queue_message_id IS NULL;

* An interrupted build leaves an INVALID index that is never read but still costs
  writes. ``IF NOT EXISTS`` will not rebuild over it and the guard below RAISEs on it,
  so drop and re-run::

      DROP INDEX CONCURRENTLY IF EXISTS we_undispatched_dispatch_idx;

* Confirm the planner uses it — the partial-index proof depends on the literals
  reaching the planner as constants::

      EXPLAIN SELECT id, workflow_id FROM workflow_execution
        WHERE status = 'PENDING' AND created_at < now() - interval '1 hour'
          AND dispatched_at IS NULL
          AND task_id IS NULL AND queue_message_id IS NULL
        ORDER BY created_at LIMIT 500;
      -- expect: Index Scan using we_undispatched_dispatch_idx

A NEW NAME rather than a rebuild under the old one: an index cannot be redefined in
place, and reusing ``we_undispatched_idx`` would mean dropping before creating, leaving
the window this ordering exists to avoid.
"""

from django.db import migrations, models
from django.db.models import Q

OLD_INDEX_NAME = "we_undispatched_idx"
INDEX_NAME = "we_undispatched_dispatch_idx"

# Frozen literal, tied to ExecutionStatus by
# tests/test_undispatched_execution_index.py — see 0026.
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

    dependencies = [("workflow_v2", "0027_workflowexecution_dispatched_at")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Create the replacement FIRST — the predicate stays served throughout.
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON workflow_execution (created_at) "
                        f"WHERE status = '{PENDING_STATUS}' "
                        "AND dispatched_at IS NULL "
                        "AND task_id IS NULL "
                        "AND queue_message_id IS NULL;"
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_VALID, reverse_sql=migrations.RunSQL.noop
                ),
                # Only then retire the old one. Reverse recreates it, so a rollback of
                # this migration leaves the pre-0028 predicate indexed.
                migrations.RunSQL(
                    sql=f"DROP INDEX CONCURRENTLY IF EXISTS {OLD_INDEX_NAME};",
                    reverse_sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {OLD_INDEX_NAME} "
                        "ON workflow_execution (created_at) "
                        f"WHERE status = '{PENDING_STATUS}' "
                        "AND task_id IS NULL "
                        "AND queue_message_id IS NULL;"
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="workflowexecution",
                    name=OLD_INDEX_NAME,
                ),
                migrations.AddIndex(
                    model_name="workflowexecution",
                    index=models.Index(
                        fields=["created_at"],
                        name=INDEX_NAME,
                        condition=Q(
                            status=PENDING_STATUS,
                            dispatched_at__isnull=True,
                            task_id__isnull=True,
                            queue_message_id__isnull=True,
                        ),
                    ),
                ),
            ],
        ),
    ]
