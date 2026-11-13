"""Index usage by (organization_id, created_at) for the dashboard queries (UN-4672).

The dashboard aggregation queries usage per org over a short window (24 h for the
hourly tier, 2 days for daily) about 5,000 times a day. The only full index leading
with organization_id is the plain FK index, so each call read the org's whole usage
history and filtered it by created_at: 0.4-4.8 s per call on the prod replica, where
one org holds 3.2M of the 8M rows.

Built CONCURRENTLY (atomic = False): a plain AddIndex holds a SHARE lock for the whole
build and would block usage inserts. usage is 3.2 GB on prod, so build it out of band
before the deploy. Application tables are not in the default search path, so set it
first:

    SET search_path TO unstract;  -- or whatever DB_SCHEMA is set to
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_org_created
        ON usage (organization_id, created_at DESC);

The migration then no-ops via IF NOT EXISTS and asserts the existing index is valid
and has the expected definition.
"""

from django.db import migrations, models

INDEX_NAME = "idx_usage_org_created"

INDEX_DEF_SUFFIX = "USING btree (organization_id, created_at DESC)"

# IF NOT EXISTS matches on name alone, so a hand-built index with different columns
# would be kept while Django recorded this definition into model state. An
# interrupted CONCURRENTLY build likewise leaves an INVALID index that costs on every
# write and is never read. Fail loudly on both rather than diverge silently. Same
# guard as file_execution 0007.
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

    dependencies = [
        ("usage_v2", "0006_alter_usage_organization"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        'ON "usage" (organization_id, created_at DESC);'
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_MATCHES, reverse_sql=migrations.RunSQL.noop
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="usage",
                    index=models.Index(
                        fields=["organization", "-created_at"], name=INDEX_NAME
                    ),
                ),
            ],
        ),
    ]
