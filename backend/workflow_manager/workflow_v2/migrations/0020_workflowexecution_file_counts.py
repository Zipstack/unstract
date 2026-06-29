from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_v2", "0019_remove_filehistory_trigram_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="successful_files",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                db_comment=(
                    "Per-run aggregate of files that completed successfully. "
                    "Written by the worker callback at terminal state. Null on "
                    "rows created before this column was added."
                ),
            ),
        ),
        migrations.AddField(
            model_name="workflowexecution",
            name="failed_files",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                db_comment=(
                    "Per-run aggregate of files that errored. Written by the "
                    "worker callback at terminal state. Null on rows created "
                    "before this column was added."
                ),
            ),
        ),
    ]
