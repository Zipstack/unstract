# Generated manually for adding file_execution_id to LookupExecutionAudit

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lookup", "0002_remove_reference_data_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="lookupexecutionaudit",
            name="file_execution_id",
            field=models.UUIDField(
                blank=True,
                help_text="Workflow file execution ID for tracking in API/ETL pipelines",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="lookupexecutionaudit",
            index=models.Index(
                fields=["file_execution_id"],
                name="lookup_exec_file_ex_idx",
            ),
        ),
    ]
