"""Add a (status, created_at) index to workflow_file_execution.

The dashboard metrics cron asks "how many files reached status X in the last N days
for this org?". All four existing indexes on this table lead with
``workflow_execution_id``, so the planner has no way to drive from here and instead
goes top-down from the org: 600 workflows -> a sequential scan of all 1.28M rows of
``workflow_execution`` -> an index lookup per run. Measured on production 2026-08-31,
that shape costs 870ms (documents_processed) and 809ms (failed_pages) per call, 83%
of the cron's total DB time. Analysis in UN-3883.

This index offers the other direction: start from this table, then join *up* to
workflow_execution and workflow. ``status = 'ERROR'`` is 0.4% of rows so failed_pages
becomes selective immediately; ``status = 'COMPLETED'`` is 97.6%, so
documents_processed only benefits once UN-3973 narrows its window.

Design
------
* CONCURRENTLY + ``atomic = False`` — a plain ``AddIndex`` holds a SHARE lock for the
  whole build and would block every write to a 3.4GB table taking live inserts,
  stalling file processing.
* INVALID-INDEX GUARD — ``IF NOT EXISTS`` silently no-ops over a leftover INVALID index
  from an interrupted CONCURRENTLY build, and Django would then record this migration
  as applied while the index is physically unusable (never read, write overhead only).
  The second statement RAISEs in that case, so the failure is loud rather than
  green-but-broken.

Pattern follows ``workflow_v2/migrations/0026_workflowexecution_undispatched_idx.py``.

Deployment
----------
``CREATE INDEX CONCURRENTLY`` scans the table and can run for minutes at this size —
long enough to time out a deploy's ``migrate`` step. Prefer building it OUT OF BAND
*before* the deploy; the migration then no-ops via ``IF NOT EXISTS``::

    CREATE INDEX CONCURRENTLY IF NOT EXISTS wfe_status_created_idx
      ON workflow_file_execution (status, created_at);

Then confirm it is valid and that the planner actually picks it up::

    SELECT c.relname, i.indisvalid FROM pg_class c
      JOIN pg_index i ON i.indexrelid = c.oid
      WHERE c.relname = 'wfe_status_created_idx';
    -- indisvalid must be 't'

Recovery
--------
An interrupted build leaves an INVALID index that adds write overhead but is never
read. ``IF NOT EXISTS`` will NOT rebuild over it (and the guard below RAISEs on it),
so drop it first and re-run::

    DROP INDEX CONCURRENTLY IF EXISTS wfe_status_created_idx;
"""

from django.db import migrations, models

INDEX_NAME = "wfe_status_created_idx"

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
        (
            "file_execution",
            "0006_workflowfileexecution_wf_file_hash_path_status_idx_and_more",
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON workflow_file_execution (status, created_at);"
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_VALID, reverse_sql=migrations.RunSQL.noop
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="workflowfileexecution",
                    index=models.Index(fields=["status", "created_at"], name=INDEX_NAME),
                ),
            ],
        ),
    ]
