# Generated migration for adding adapter availability tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="adapterinstance",
            name="is_available",
            field=models.BooleanField(
                default=True,
                db_comment="Is the adapter available in SDK (not deprecated)",
            ),
        ),
        migrations.AddField(
            model_name="adapterinstance",
            name="deprecation_metadata",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                db_comment="Metadata about adapter deprecation (reason, date, replacement)",
            ),
        ),
    ]
