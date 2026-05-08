from django.db import migrations, models


class Migration(migrations.Migration):
    """Build the project_id / prompt_id dashboard indexes without locking.

    CONCURRENTLY requires the migration to run outside a transaction, hence
    atomic = False. RunSQL with IF NOT EXISTS makes a partial-apply
    (process killed between SQL success and django_migrations insert)
    recoverable on retry without manual --fake intervention.
    """

    atomic = False

    dependencies = [
        ("usage_v2", "0004_usage_metrics_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "idx_usage_project_created "
                'ON "usage" (project_id, created_at DESC);'
            ),
            reverse_sql=("DROP INDEX CONCURRENTLY IF EXISTS idx_usage_project_created;"),
            state_operations=[
                migrations.AddIndex(
                    model_name="usage",
                    index=models.Index(
                        fields=["project_id", "-created_at"],
                        name="idx_usage_project_created",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "idx_usage_prompt_created "
                'ON "usage" (prompt_id, created_at DESC);'
            ),
            reverse_sql=("DROP INDEX CONCURRENTLY IF EXISTS idx_usage_prompt_created;"),
            state_operations=[
                migrations.AddIndex(
                    model_name="usage",
                    index=models.Index(
                        fields=["prompt_id", "-created_at"],
                        name="idx_usage_prompt_created",
                    ),
                ),
            ],
        ),
    ]
