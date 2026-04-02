# Generated migration for word_confidence_data field

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "prompt_studio_output_manager_v2",
            "0003_promptstudiooutputmanager_confidence_data",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="promptstudiooutputmanager",
            name="word_confidence_data",
            field=models.JSONField(
                blank=True,
                db_comment="Field to store word-level confidence data",
                null=True,
            ),
        ),
    ]
