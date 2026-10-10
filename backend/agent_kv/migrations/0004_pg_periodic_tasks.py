"""Remove the Agent-KV maintenance periodics -- the CronJob owns the schedule.

An earlier revision of this migration SEEDED two ``PgPeriodicTask`` rows
(``agent_kv.sweep`` at ``*/10``, ``agent_kv.ttl_cleanup`` at ``17 3 * * *``) on
the premise that nothing anywhere fired the two maintenance commands -- "no
``PgPeriodicTask``, no beat entry, no CronJob". **That premise was false when it
was written.** ``templates/backend/agent-kv-cronjobs.yaml`` in the cloud chart
already ran the same two management commands, on the same branch, added several
commits earlier. The seeding migration was written in response to a review
finding about the unscheduled sweep without noticing the finding had already
been answered elsewhere in the same change.

Keeping both would have been worse than either alone:

* **Two owners for one schedule.** The rows are seeded ``pg_owned: False``, and
  the PG scheduler claims only ``WHERE pg_owned AND enabled``
  (``pg_queue/models.py``), so they are inert *today*. But the whole point of
  that flag is that a rollout flips it -- and the moment it did, the ``*/10``
  rows and the CronJob's ``*/15`` ticks would both fire, colliding exactly at
  ``:30`` and contending on the same job rows. The TTL cadences disagreed by
  24x (daily here, hourly in the chart), so whichever fired would be whichever
  owner someone remembered.
* **Only one owner has operational bounds.** The CronJob carries
  ``concurrencyPolicy: Forbid`` and ``activeDeadlineSeconds``; a PG periodic has
  neither, so a hung sweep under the scheduler has nothing stopping it.
* **The feature only runs where the CronJob is.** This deployment routes
  ``table`` only, and the ``agentic_table`` plugin ships in the cloud image. A
  pure-OSS install cannot dispatch an Agent-KV job at all, so there is no
  stranded row for a sweep to reap there.

So the CronJob is the single owner, and this migration deletes the rows rather
than merely stopping at not creating them -- any environment that applied the
seeding revision (dev namespaces did) still has them, and leaving them to be
switched on by a future global ``pg_owned`` flip is precisely the hazard being
removed.

**Self-hosted OSS operators who enable the Agent-KV API must schedule
``manage.py agent_kv_sweep`` and ``manage.py agent_kv_ttl_cleanup``
themselves** (cron, a systemd timer, or their own ``PgPeriodicTask`` rows with
``pg_owned: True``). Without them a stranded job holds its concurrency slot
until the 6h Redis TTL, and ``AGENT_KV_RESULT_TTL_DAYS`` is advisory --
staged documents and results stay in the bucket indefinitely, which is a
retention failure rather than a disk-usage one. ``docs/agent-kv-api.md`` §12
carries this in the deploy checklist.

Reverse re-creates the rows (still inert) so the migration is reversible and a
``migrate agent_kv 0003`` lands back on the previous tree's state exactly.
"""

from django.db import migrations

#: What the seeding revision wrote, kept ONLY so forward can delete exactly
#: those rows by name and reverse can restore them. Not a live schedule --
#: the cadences that run are in the cloud chart's `backend.agentKvCronJobs`.
PG_PERIODIC_TASKS = [
    {
        "name": "agent_kv_sweep",
        "task_name": "agent_kv.sweep",
        "queue": "scheduler",
        "task_args": [],
        "task_kwargs": {},
        "cron_string": "*/10 * * * *",
    },
    {
        "name": "agent_kv_ttl_cleanup",
        "task_name": "agent_kv.ttl_cleanup",
        "queue": "scheduler",
        "task_args": [],
        "task_kwargs": {},
        "cron_string": "17 3 * * *",
    },
]


def remove_pg_periodic_tasks(apps, schema_editor):
    """Delete the seeded rows. Idempotent: a fresh install matches nothing."""
    # snake_case, not the usual `PgPeriodicTask = apps.get_model(...)` Django
    # idiom: it is a local variable, and sonar's S117 reads the CamelCase name
    # as a naming violation. The historical-model object is the same either way.
    periodic_task = apps.get_model("pg_queue", "PgPeriodicTask")
    periodic_task.objects.filter(
        name__in=[spec["name"] for spec in PG_PERIODIC_TASKS]
    ).delete()


def create_pg_periodic_tasks(apps, schema_editor):
    """Reverse only. Restores the rows the seeding revision created, inert."""
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
        ("agent_kv", "0003_agentkvjob_cleanup_failed_at"),
        # The table this operates on.
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(remove_pg_periodic_tasks, create_pg_periodic_tasks),
    ]
