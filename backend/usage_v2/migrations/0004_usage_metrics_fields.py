from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usage_v2", "0003_usage_usage_executi_4deb35_idx"),
    ]

    operations = [
        # Extend llm_usage_reason choices (cloud plugins append at runtime)
        migrations.AlterField(
            model_name="usage",
            name="llm_usage_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("extraction", "Extraction"),
                    ("challenge", "Challenge"),
                    ("summarize", "Summarize"),
                    ("lookup", "Lookup"),
                ],
                db_comment="Reason for LLM usage. Empty if usage_type is 'embedding'. ",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="project_id",
            field=models.UUIDField(
                blank=True,
                db_comment=(
                    "Prompt Studio project (tool) the call belongs to (no FK; "
                    "survives tool deletion). NULL for embeddings and historical "
                    "rows."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="prompt_id",
            field=models.UUIDField(
                blank=True,
                db_comment=(
                    "Prompt key UUID that triggered the call (no FK; survives "
                    "prompt deletion). NULL for single-pass / embeddings / "
                    "historical rows."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="execution_time_ms",
            field=models.IntegerField(
                blank=True,
                db_comment="Wall-clock time for the operation in milliseconds",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SUCCESS", "Success"),
                    ("ERROR", "Error"),
                    ("SKIPPED", "Skipped"),
                ],
                db_comment="Operation outcome: SUCCESS, ERROR, or SKIPPED",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="error_message",
            field=models.TextField(
                blank=True,
                db_comment="Error details when status is ERROR",
                null=True,
            ),
        ),
        # Indexes on project_id / prompt_id moved to 0005 so they can run
        # CONCURRENTLY — usage is billing-critical and a plain AddIndex takes
        # a share-update lock for the duration of the build on large tables.
    ]
