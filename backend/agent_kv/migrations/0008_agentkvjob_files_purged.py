"""Record purge intent explicitly instead of inferring it from the ref columns.

UN-4232. A cancel that lands after an extraction has already finished -- and
after the engine has already flushed its OCR and LLM usage -- used to have its
result written and then deleted: the customer was billed for an answer that was
destroyed. Keeping the result requires knowing whether the caller has asked for
this job's data to be destroyed, and that question cannot be answered from
``input_ref``/``result_ref``: both columns mean "never set", "purged", and
"purge attempted but the object delete failed, so the ref is kept for a TTL
retry" at different times. Three attempts to infer it from them were reverted.

``files_purged`` records the fact directly. Written unconditionally by
``DELETE /agent-kv/{job_id}`` and by ``run_ttl_cleanup`` before either tries a
delete, so a failed delete cannot leave it False; read by
``AgentKVJob.attach_result_to_cancelled`` (refuses to attach a late result to a
purged job) and by ``JobResultView`` (refuses to serve one, including the case
where a ref survived a failed delete, which no ref-based check can see).

``default=False`` with no NULL state, deliberately: "we do not know whether
this was purged" is the condition this column exists to abolish. Existing rows
are correctly False -- a row written before this migration predates any purge
marker, and the API's behaviour for it (serve the result if a ref is there) is
unchanged.

A plain AddField with a non-volatile default is metadata-only on PG 11+ (no
table rewrite, no backfill scan), so this needs no concurrent/batched
treatment -- and ``agent_kv_job`` has not been deployed anywhere yet regardless.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0007_remove_agent_kv_periodic_tasks"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentkvjob",
            name="files_purged",
            field=models.BooleanField(default=False),
        ),
    ]
