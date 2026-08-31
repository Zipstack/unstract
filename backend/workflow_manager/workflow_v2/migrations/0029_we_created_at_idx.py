"""Add an unqualified created_at index to workflow_execution.

Serves any bare "rows in this date window" question on this table. The immediate
caller is the dashboard metrics cron's active-org prefilter
(``dashboard_metrics/tasks.py``)::

    WorkflowExecution.objects.filter(created_at__gte=window_start)
        .values_list("workflow__organization_id", flat=True).distinct()

Measured on production 2026-08-31 at 1,849ms per call — the slowest single query on
the instance by average execution time. Analysis in UN-3883.

WHY THE EXISTING INDEXES DO NOT COVER IT. ``(workflow_id, -created_at)`` and
``(pipeline_id, -created_at)`` are date-ordered only *within* one workflow or pipeline,
so a date range with no leading column value has to scan them whole.
``we_active_by_workflow_idx`` is keyed on workflow_id, and ``we_undispatched_idx`` is a
partial index that is empty in steady state. Nothing leads with ``created_at``.

Beyond the prefilter, this is a prerequisite for the grouped-query rewrite in UN-4045.
Grouping by organization removes the per-org predicate that
``deployed_api_requests`` / ``etl_pipeline_executions`` / ``prompt_executions`` use as
their index entry point, leaving each of them on a bare ``created_at`` range over this
table — the same shape as the prefilter, at the same cost, three more times per run.

Design
------
* UNPARTIAL and single-column — the predicate has no other constant to key on, and the
  callers differ in what they select, so a covering column would help one and not the
  others.
* CONCURRENTLY + ``atomic = False`` — ``workflow_execution`` is a multi-million-row
  table in production; a plain ``AddIndex`` holds a SHARE lock for the whole build and
  blocks writes, i.e. blocks every execution in flight.
* INVALID-INDEX GUARD — ``IF NOT EXISTS`` silently no-ops over a leftover INVALID index
  from an interrupted CONCURRENTLY build, and Django would then record this migration as
  applied while the index is physically unusable (never read, write overhead only). The
  second statement RAISEs in that case, so the failure is loud rather than
  green-but-broken.

Deployment
----------
``CREATE INDEX CONCURRENTLY`` scans the table and can run for minutes at this size —
long enough to time out a deploy's ``migrate`` step. Prefer building it OUT OF BAND
*before* the deploy; the migration then no-ops via ``IF NOT EXISTS``::

    CREATE INDEX CONCURRENTLY IF NOT EXISTS we_created_at_idx
      ON workflow_execution (created_at);

Then confirm it is valid and that the planner picks it up::

    SELECT c.relname, i.indisvalid FROM pg_class c
      JOIN pg_index i ON i.indexrelid = c.oid
      WHERE c.relname = 'we_created_at_idx';
    -- indisvalid must be 't'

Recovery
--------
An interrupted build leaves an INVALID index that adds write overhead but is never read.
``IF NOT EXISTS`` will NOT rebuild over it (and the guard below RAISEs on it), so drop
it first and re-run::

    DROP INDEX CONCURRENTLY IF EXISTS we_created_at_idx;
"""

from django.db import migrations, models

INDEX_NAME = "we_created_at_idx"

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

    dependencies = [("workflow_v2", "0028_undispatched_idx_dispatched_at")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON workflow_execution (created_at);"
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
                    index=models.Index(fields=["created_at"], name=INDEX_NAME),
                ),
            ],
        ),
    ]
