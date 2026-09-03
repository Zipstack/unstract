"""Add a created_at index to workflow_execution.

Serves bare "rows in this date window" queries with no leading column value — the
dashboard metrics active-org prefilter today, and the grouped metric queries in
UN-4045. The composite indexes lead with workflow_id / pipeline_id, so they are
date-ordered only within one workflow or pipeline; the partial index is empty in
steady state. Measurements in UN-3883.

Built CONCURRENTLY (atomic = False): a plain AddIndex holds a SHARE lock for the
whole build and would block every execution in flight. Prefer building it out of
band before the deploy::

    CREATE INDEX CONCURRENTLY IF NOT EXISTS we_created_at_idx
        ON workflow_execution (created_at);

The migration then no-ops via IF NOT EXISTS and asserts the existing index is valid
and has the expected definition.
"""

from django.db import migrations, models

INDEX_NAME = "we_created_at_idx"

INDEX_DEF_SUFFIX = "USING btree (created_at)"

# IF NOT EXISTS matches on name alone, so a hand-built index with a different
# definition — (created_at DESC) is the likely slip, since the neighbouring indexes
# in this Meta are declared "-created_at" — would be kept while AddIndex recorded
# fields=["created_at"] into model state. An interrupted CONCURRENTLY build likewise
# leaves an INVALID index that costs on every write and is never read. Fail loudly on
# both rather than diverge silently.
_ASSERT_INDEX_MATCHES = f"""
DO $$
DECLARE
    idx_def text;
    idx_valid boolean;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid), i.indisvalid INTO idx_def, idx_valid
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_index i ON i.indexrelid = c.oid
    WHERE c.relname = '{INDEX_NAME}' AND n.nspname = current_schema();

    IF idx_def IS NULL THEN
        RAISE EXCEPTION 'Index {INDEX_NAME} is missing from schema % after CREATE INDEX.', current_schema();
    END IF;

    IF NOT idx_valid THEN
        RAISE EXCEPTION 'Index {INDEX_NAME} exists but is INVALID (a prior CREATE INDEX CONCURRENTLY was interrupted). Drop it and re-run: DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};';
    END IF;

    IF idx_def NOT LIKE '%{INDEX_DEF_SUFFIX}' THEN
        RAISE EXCEPTION 'Index {INDEX_NAME} exists with an unexpected definition (%), expected {INDEX_DEF_SUFFIX}. Drop it and re-run: DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};', idx_def;
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
                    sql=_ASSERT_INDEX_MATCHES, reverse_sql=migrations.RunSQL.noop
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
