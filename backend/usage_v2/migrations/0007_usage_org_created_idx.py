from django.db import migrations, models


class Migration(migrations.Migration):
    """Index usage by (organization_id, created_at) for the dashboard queries.

    The dashboard aggregation queries usage per org over a short window (24 h for
    the hourly tier, 2 days for daily) about 5,000 times a day. Without this index
    the only org index is the plain FK index on organization_id, so each call reads
    the org's whole usage history and filters it by created_at. On prod, one org
    holds 3.2M of the 8M rows (UN-4672).

    CONCURRENTLY needs the migration to run outside a transaction, hence
    atomic = False. IF NOT EXISTS lets the index be built out of band first; the
    migration then no-ops. If a concurrent build is interrupted it leaves an
    INVALID index that IF NOT EXISTS would skip, so drop it and re-run:

        DROP INDEX CONCURRENTLY IF EXISTS idx_usage_org_created;
    """

    atomic = False

    dependencies = [
        ("usage_v2", "0006_alter_usage_organization"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "idx_usage_org_created "
                'ON "usage" (organization_id, created_at DESC);'
            ),
            reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS idx_usage_org_created;",
            state_operations=[
                migrations.AddIndex(
                    model_name="usage",
                    index=models.Index(
                        fields=["organization", "-created_at"],
                        name="idx_usage_org_created",
                    ),
                ),
            ],
        ),
    ]
