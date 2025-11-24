# Generated manually to add pipeline_state field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agentic_studio_v2', '0002_fix_loglevel_enum'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenticproject',
            name='pipeline_state',
            field=models.JSONField(
                blank=True,
                null=True,
                db_comment="Pipeline processing state for stages (raw_text, summary, schema, prompt, extraction)"
            ),
        ),
    ]
