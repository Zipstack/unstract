"""Add a created_at index to workflow_execution.

Serves bare "rows in this date window" queries with no leading column value — the
dashboard metrics active-org prefilter today, and the grouped metric queries in
UN-4045. The composite indexes lead with workflow_id / pipeline_id, so they are
date-ordered only within one workflow or pipeline; the partial index is empty in
steady state. Measurements in UN-3883.

Built CONCURRENTLY (atomic = False): a plain AddIndex holds a SHARE lock for the
whole build and would block every execution in flight. Prefer building it out of
band before the deploy; the migration then no-ops via IF NOT EXISTS.
"""

from django.db import migrations, models

INDEX_NAME = "we_created_at_idx"

# An interrupted CONCURRENTLY build leaves an INVALID index that costs on every
# write and is never read. IF NOT EXISTS would keep it while Django recorded the
# migration as applied, so fail loudly instead.
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
