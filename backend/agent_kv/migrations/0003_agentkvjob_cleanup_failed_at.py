"""Record when TTL cleanup last failed on a job, and index the ordering.

Review follow-up on UN-4044. ``run_ttl_cleanup`` retains a ref whose file
delete failed, because the ref is the only handle a retry can work from. Under
the previous plain ``expires_at`` ordering those rows refilled the capped batch
on every tick, so a persistent object-store fault on 500 rows stalled cleanup
outright and every later expired job kept its files past TTL.

Ordering is now ``(cleanup_failed_at NULLS FIRST, expires_at)``: a job that has
never failed is always processed ahead of one that has, so failures cannot
block the backlog, and the stamp is refreshed on each failed attempt so
failures rotate rather than one row absorbing every retry.

A plain (non-CONCURRENT) AddIndex is correct here, unlike the concurrent builds
used elsewhere in this codebase: ``agent_kv_job`` is created by this app's own
``0001_initial`` and has never been deployed, so the table is empty when this
runs and the ACCESS EXCLUSIVE lock has nothing to block.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0002_agentkvjob_extractor"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentkvjob",
            name="cleanup_failed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="agentkvjob",
            index=models.Index(
                fields=["cleanup_failed_at", "expires_at"],
                name="agent_kv_jo_cleanup_f38edc_idx",
            ),
        ),
    ]
