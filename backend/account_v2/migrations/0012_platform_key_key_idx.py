from django.db import migrations, models


class Migration(migrations.Migration):
    """Index platform_key.key for the bearer-token lookups.

    x2text-service and platform-service authenticate each request with
    ``SELECT ... FROM platform_key WHERE key = %s``, about 145k times a day on
    prod. Without an index on key, every lookup is a sequential scan (UN-4672).

    CONCURRENTLY needs the migration to run outside a transaction, hence
    atomic = False. IF NOT EXISTS lets the index be built out of band first. If
    a concurrent build is interrupted it leaves an INVALID index that IF NOT
    EXISTS would skip, so drop it and re-run:

        DROP INDEX CONCURRENTLY IF EXISTS platform_key_key_idx;
    """

    atomic = False

    dependencies = [
        ("account_v2", "0011_user_session_generation_sessionrecord"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                'platform_key_key_idx ON "platform_key" (key);'
            ),
            reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS platform_key_key_idx;",
            state_operations=[
                migrations.AddIndex(
                    model_name="platformkey",
                    index=models.Index(fields=["key"], name="platform_key_key_idx"),
                ),
            ],
        ),
    ]
