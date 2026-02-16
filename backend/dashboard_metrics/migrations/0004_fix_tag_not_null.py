"""Fix tag column to enforce NOT NULL at database level.

The tag column was created as nullable despite the Django model not having
null=True. This caused duplicate rows because PostgreSQL unique indexes
treat NULLs as distinct values, bypassing the unique constraint.

This migration:
1. Removes duplicate NULL-tag rows that conflict with existing '' rows
2. Updates remaining NULL tags to empty string
3. Alters the columns to NOT NULL with default ''
"""

from django.db import migrations

TABLES_WITH_TIME_COL = [
    ("event_metrics_hourly", "timestamp"),
    ("event_metrics_daily", "date"),
    ("event_metrics_monthly", "month"),
]


def cleanup_and_fix_nulls(apps, schema_editor):
    """Remove NULL-tag duplicates and set remaining NULLs to empty string."""
    for table, time_col in TABLES_WITH_TIME_COL:
        # Step 1: Delete NULL-tag rows where a matching '' row already exists
        schema_editor.execute(
            f"""
            DELETE FROM "{table}" n
            USING "{table}" e
            WHERE n.tag IS NULL
              AND e.tag = ''
              AND n.organization_id = e.organization_id
              AND n."{time_col}" = e."{time_col}"
              AND n.metric_name = e.metric_name
              AND n.project = e.project
            """
        )

        # Step 2: For remaining NULL-tag duplicates (no '' counterpart),
        # keep only the most recent row
        schema_editor.execute(
            f"""
            DELETE FROM "{table}" WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY organization_id, "{time_col}",
                                     metric_name, project
                        ORDER BY modified_at DESC
                    ) AS rn
                    FROM "{table}"
                    WHERE tag IS NULL
                ) ranked WHERE rn > 1
            )
            """
        )

        # Step 3: Update remaining NULL tags to empty string
        schema_editor.execute(f"""UPDATE "{table}" SET tag = '' WHERE tag IS NULL""")


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0003_setup_aggregation_task"),
    ]

    operations = [
        migrations.RunPython(cleanup_and_fix_nulls, migrations.RunPython.noop),
        # Enforce NOT NULL with default at database level
        migrations.RunSQL(
            sql=(
                "ALTER TABLE event_metrics_hourly "
                "ALTER COLUMN tag SET DEFAULT '', "
                "ALTER COLUMN tag SET NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE event_metrics_hourly " "ALTER COLUMN tag DROP NOT NULL;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE event_metrics_daily "
                "ALTER COLUMN tag SET DEFAULT '', "
                "ALTER COLUMN tag SET NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE event_metrics_daily " "ALTER COLUMN tag DROP NOT NULL;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE event_metrics_monthly "
                "ALTER COLUMN tag SET DEFAULT '', "
                "ALTER COLUMN tag SET NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE event_metrics_monthly " "ALTER COLUMN tag DROP NOT NULL;"
            ),
        ),
    ]
