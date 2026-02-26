# Generated manually for Superset dashboard performance optimization

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add indexes to optimize page_usage queries for analytics dashboards.

    These indexes address timeout issues in Superset multi-org usage dashboards:
    1. idx_page_usage_created_org - Enables date-range filtering (90-day lookback)
       with INCLUDE columns for index-only scans (Django doesn't support INCLUDE)
    2. idx_page_usage_run_id - Speeds up JOIN with workflow_file_execution
    """

    # Required for CONCURRENTLY - cannot run in transaction
    atomic = False

    dependencies = [
        ("account_usage", "0002_alter_pageusage_pages_processed"),
    ]

    operations = [
        # Covering index - must use RunSQL because Django doesn't support INCLUDE
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_page_usage_created_org
                ON page_usage(created_at, organization_id)
                INCLUDE (pages_processed, run_id);
            """,
            reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS idx_page_usage_created_org;",
        ),
        # Simple index - using Django's concurrent index operation
        AddIndexConcurrently(
            model_name="pageusage",
            index=models.Index(fields=["run_id"], name="idx_page_usage_run_id"),
        ),
    ]
