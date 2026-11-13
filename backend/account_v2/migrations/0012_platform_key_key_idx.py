"""Index platform_key.key for bearer-token auth (UN-4672).

x2text-service and platform-service authenticate each request with
``SELECT ... FROM platform_key WHERE key = %s``, about 145k times a day on prod.
Without an index on key every lookup is a sequential scan of the table.

Built CONCURRENTLY (atomic = False) so the build never blocks writes. The table is
small (4.6 MB on prod), so building at deploy is fine. To build it out of band:

    SET search_path TO unstract;  -- or whatever DB_SCHEMA is set to
    CREATE INDEX CONCURRENTLY IF NOT EXISTS platform_key_key_idx ON platform_key (key);

The migration then no-ops via IF NOT EXISTS and asserts the existing index is valid
and has the expected definition.
"""

from django.db import migrations, models

INDEX_NAME = "platform_key_key_idx"

INDEX_DEF_SUFFIX = "USING btree (key)"

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
        ("account_v2", "0011_user_session_generation_sessionrecord"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        'ON "platform_key" (key);'
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
                migrations.RunSQL(
                    sql=_ASSERT_INDEX_MATCHES, reverse_sql=migrations.RunSQL.noop
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="platformkey",
                    index=models.Index(fields=["key"], name=INDEX_NAME),
                ),
            ],
        ),
    ]
