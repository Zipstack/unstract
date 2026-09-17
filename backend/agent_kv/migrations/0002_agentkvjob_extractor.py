"""Record which extractor each job ran.

Defaulting to "kv" is the historical truth, not a guess: before this column
existed the API accepted exactly one extractor and it was always `kv`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentkvjob",
            name="extractor",
            field=models.CharField(default="kv", max_length=32),
        ),
    ]
