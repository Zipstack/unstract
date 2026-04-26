from django.db import migrations, models


class Migration(migrations.Migration):
    """Build the lookup-usage dashboard index without locking the table.

    CONCURRENTLY requires that the migration itself runs outside a
    transaction, hence atomic = False. We use RunSQL with IF NOT EXISTS so
    a partial-apply (process killed between SQL success and django_migrations
    insert) is recoverable on retry without manual --fake intervention.
    """

    atomic = False

    dependencies = [
        ("usage_v2", "0004_usage_metrics_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "idx_usage_reason_ref_created "
                'ON "usage" (llm_usage_reason, reference_id, created_at DESC);'
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS idx_usage_reason_ref_created;"
            ),
            state_operations=[
                migrations.AddIndex(
                    model_name="usage",
                    index=models.Index(
                        fields=["llm_usage_reason", "reference_id", "-created_at"],
                        name="idx_usage_reason_ref_created",
                    ),
                ),
            ],
        ),
    ]
