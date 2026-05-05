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
            name="reference_id",
            field=models.UUIDField(
                blank=True,
                db_comment=(
                    "Polymorphic correlation ID (no FK constraint) linking to the "
                    "entity that triggered this usage. Interpret via reference_type. "
                    "OSS values: prompt_key UUID. "
                    "NULL for most operations; survives entity deletion."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="usage",
            name="reference_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("prompt_key", "Prompt Key"),
                    ("lookup_version", "Lookup Version"),
                ],
                db_comment=(
                    "Discriminator for reference_id. "
                    "OSS values: 'prompt_key'. "
                    "NULL when reference_id is NULL."
                ),
                max_length=64,
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
        # reference_id and reference_type must both be NULL or both be set
        # so reference_id is always decodable.
        migrations.AddConstraint(
            model_name="usage",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("reference_id__isnull", True), ("reference_type__isnull", True)
                    ),
                    models.Q(
                        ("reference_id__isnull", False), ("reference_type__isnull", False)
                    ),
                    _connector="OR",
                ),
                name="usage_reference_pair_consistent",
            ),
        ),
        # Index creation moved to 0005 so it can run CONCURRENTLY — the usage
        # table is billing-critical and a plain AddIndex takes a share-update
        # lock for the duration of the build on large tables.
    ]
