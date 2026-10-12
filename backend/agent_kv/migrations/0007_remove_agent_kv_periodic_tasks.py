"""Remove the Agent-KV maintenance periodics -- the CronJob owns the schedule.

Migration 0004 seeded two ``PgPeriodicTask`` rows (``agent_kv.sweep`` at
``*/10``, ``agent_kv.ttl_cleanup`` at ``17 3 * * *``) on the stated premise
that nothing anywhere fired the two maintenance commands -- "no
``PgPeriodicTask``, no beat entry, no CronJob". **That premise was false when
it was written.** ``templates/backend/agent-kv-cronjobs.yaml`` in the cloud
chart already ran the same two management commands, added several commits
earlier on the same branch. 0004 was written in response to a review finding
about the unscheduled sweep without noticing the finding had already been
answered elsewhere in the same change.

Keeping both would have been worse than either alone:

* **Two owners for one schedule.** The rows are seeded ``pg_owned: False`` and
  the PG scheduler claims only ``WHERE pg_owned AND enabled``
  (``pg_queue/models.py``), so they are inert *today*. But that flag exists to
  be flipped by a rollout -- and the moment it was, the ``*/10`` rows and the
  CronJob's ``*/15`` ticks would both fire, colliding exactly at ``:30`` and
  contending on the same job rows. The TTL cadences disagreed by 24x (daily
  here, hourly in the chart), so whichever ran would be whichever owner someone
  happened to remember.
* **Only one owner has operational bounds.** The CronJob carries
  ``concurrencyPolicy: Forbid`` and ``activeDeadlineSeconds``; a PG periodic has
  neither, so a hung sweep under the scheduler has nothing stopping it.
* **The feature only runs where the CronJob is.** This deployment routes
  ``table`` only, and the ``agentic_table`` plugin ships in the cloud image. A
  pure-OSS install cannot dispatch an Agent-KV job at all, so there is no
  stranded row for a sweep to reap there.

**Why this is a new migration and not an edit to 0004.** Django records a
migration as applied and never re-runs it. Rewriting 0004's forward operation
would therefore have had no effect whatsoever in exactly the environments that
have the rows -- every dev namespace that applied the seeding version -- while
changing behaviour only for fresh installs. The first cut of this fix did that,
and its own docstring claimed to clean up environments it could not reach.

So: 0004 stays as it was, this removes. A fresh install seeds and then deletes
(two trivial writes); an environment that already applied 0004 just deletes.
Both land on the same state, which is the point.

The delete is scoped BY NAME and is idempotent: a fresh install's 0004 created
exactly these two rows, and an unscoped delete here would wipe the
dashboard_metrics periodics this table is shared with.

**Self-hosted OSS operators who enable the Agent-KV API must schedule
``manage.py agent_kv_sweep`` and ``manage.py agent_kv_ttl_cleanup``
themselves** (cron, a systemd timer, or their own ``PgPeriodicTask`` rows with
``pg_owned: True``). Without them a stranded job holds its concurrency slot
until the 6 h Redis TTL, and ``AGENT_KV_RESULT_TTL_DAYS`` is advisory --
staged documents and results stay in the bucket indefinitely, which is a
retention failure rather than a disk-usage one. ``docs/agent-kv-api.md`` §12
carries this in the deploy checklist.

Reverse re-creates the rows (still inert), so ``migrate agent_kv 0006`` lands
back on the previous release's state exactly rather than leaving an environment
with no rows and no way to restore them.
"""

import importlib

from django.db import migrations

#: The rows 0004 created, read from 0004 itself rather than re-declared here,
#: so the two files cannot drift into deleting a different set than was seeded.
#: `importlib` because the module name starts with a digit and cannot be a
#: plain `import` (same reason `tests/test_periodic_tasks_migration.py` does
#: it this way).
PG_PERIODIC_TASKS = importlib.import_module(
    "agent_kv.migrations.0004_pg_periodic_tasks"
).PG_PERIODIC_TASKS


def remove_pg_periodic_tasks(apps, schema_editor):
    """Delete the seeded rows. Idempotent: a fresh install matches nothing."""
    # snake_case, not the usual `PgPeriodicTask = apps.get_model(...)` Django
    # idiom: it is a local variable, and sonar's S117 reads the CamelCase name
    # as a naming violation. The historical-model object is the same either way.
    periodic_task = apps.get_model("pg_queue", "PgPeriodicTask")
    periodic_task.objects.filter(
        name__in=[spec["name"] for spec in PG_PERIODIC_TASKS]
    ).delete()


def restore_pg_periodic_tasks(apps, schema_editor):
    """Reverse only. Restores 0004's rows, still inert (`pg_owned: False`).

    A reverse that restored them ENABLED would turn a rollback into the
    double-fire this migration exists to prevent.
    """
    periodic_task = apps.get_model("pg_queue", "PgPeriodicTask")
    for spec in PG_PERIODIC_TASKS:
        periodic_task.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task_name": spec["task_name"],
                "queue": spec["queue"],
                "task_args": spec["task_args"],
                "task_kwargs": spec["task_kwargs"],
                "cron_string": spec["cron_string"],
                # Platform-wide, not per-org (spec §5.4): both internal
                # endpoints sweep across every organization.
                "org_id": "",
                "enabled": True,
                "pg_owned": False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0006_agentkvjob_adapters"),
    ]

    operations = [
        migrations.RunPython(remove_pg_periodic_tasks, restore_pg_periodic_tasks),
    ]
