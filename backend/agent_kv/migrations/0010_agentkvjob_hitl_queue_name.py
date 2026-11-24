"""The review queue a submit named, and the class its push landed under.

`blank=True, default=""` rather than nullable: "no queue" and "the empty
string" are the same state for this field, and a third state (NULL) would make
every reader test for two falsy values. Matches `webhook_url` beside it, which
is the other optional caller-supplied string on this model.

No backfill: every existing row predates the field and correctly means "no
review was asked for", which is what the default already says.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0009_drop_agent_kv_periodic_tasks"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentkvjob",
            name="hitl_queue_name",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="agentkvjob",
            name="hitl_queue_class",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
