# Generated manually to fix LogLevel enum mismatch
# WARNING enum changed from CRITICAL to FATAL, and WARNING to WARN
# This aligns with unstract.sdk.constants.LogLevel

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agentic_studio_v2', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agenticlog',
            name='level',
            field=models.CharField(
                choices=[
                    ('DEBUG', 'Debug'),
                    ('INFO', 'Info'),
                    ('WARN', 'Warning'),
                    ('ERROR', 'Error'),
                    ('FATAL', 'Fatal')
                ],
                db_comment='Log level',
                max_length=20
            ),
        ),
    ]
