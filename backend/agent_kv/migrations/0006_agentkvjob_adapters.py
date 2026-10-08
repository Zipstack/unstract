"""Record which platform adapters a job ran on.

The `table` extractor resolves the CALLER's own adapters rather than operator
env credentials, so adapter choice became a per-request, cost-bearing decision.
Before this column the chosen ids reached `executor_params` and nowhere else --
not the job row, not the status document, not `usage_summary` -- so the first
question in any billing dispute ("which model did job X use?") needed a join
against `usage_v2` on `run_id` that the API cannot perform and the customer
cannot see.

Additive and nullable-by-default (`{}`), so existing rows are untouched: they
predate caller-supplied adapters and genuinely ran on env credentials, which
`{}` is the honest representation of.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0005_agentkvjob_extractor_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentkvjob",
            name="adapters",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
