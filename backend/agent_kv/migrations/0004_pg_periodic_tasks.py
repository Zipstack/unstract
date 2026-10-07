"""Schedule the two Agent-KV maintenance periodics.

Both tasks were registered in ``workers/scheduler/agent_kv_tasks.py`` and both
internal endpoints existed, but nothing anywhere created a row to fire them --
no ``PgPeriodicTask``, no beat entry, no CronJob. The module's own docstring
said an operator must register them by hand, which in practice means they never
ran.

What that costs, concretely:

* ``run_sweep`` never runs, so an OOM-killed executor leaves its job row
  non-terminal forever -- ``link_error`` never fires for a killed process -- and
  the row holds its concurrency slot until the 6h Redis TTL. Enough of those and
  the org's allowance is exhausted and new submits start getting 429s.
* ``run_ttl_cleanup`` never runs, so ``AGENT_KV_RESULT_TTL_DAYS`` is advisory:
  every staged customer document and every result stays in the bucket
  indefinitely. That is a retention-policy failure, not just a disk-usage one.

Follows the ``dashboard_metrics`` precedent (migrations 0004-0006) rather than
inventing a mechanism: the same ``PgPeriodicTask`` table, the same
``update_or_create`` shape so a re-run is idempotent, and ``pg_owned: False`` so
applying this migration does not itself start firing them -- the rollout flag
decides that, exactly as it does for the metrics periodics.

Cadences are deliberately offset from each other and off the hour: the sweep is
cheap and wants to be frequent (a stuck job holds a slot), the TTL cleanup is a
bulk delete that should not land on the same tick as anything else.
"""

from django.db import migrations

PG_PERIODIC_TASKS = [
    {
        "name": "agent_kv_sweep",
        # Wire name registered by workers/scheduler/agent_kv_tasks.py.
        "task_name": "agent_kv.sweep",
        "queue": "scheduler",
        "task_args": [],
        "task_kwargs": {},
        # Every 10 minutes: a stuck job holds a concurrency slot, and the
        # handler is idempotent and batch-capped server-side, so a missed tick
        # costs nothing and a frequent one is cheap.
        "cron_string": "*/10 * * * *",
    },
    {
        "name": "agent_kv_ttl_cleanup",
        "task_name": "agent_kv.ttl_cleanup",
        "queue": "scheduler",
        "task_args": [],
        "task_kwargs": {},
        # Daily at 03:17 UTC. Off the hour and off the dashboard_metrics
        # cleanups (02:00 / 03:00) so a bulk object-store delete does not land
        # on the same tick as another bulk job.
        "cron_string": "17 3 * * *",
    },
]


def create_pg_periodic_tasks(apps, schema_editor):
    # snake_case, not the usual `PgPeriodicTask = apps.get_model(...)` Django
    # idiom: it is a local variable, and sonar's S117 reads the CamelCase name
    # as a naming violation. The historical-model object is the same either way.
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
                # Inert until the rollout flag decides otherwise; never fired by
                # applying this migration. Same posture as dashboard_metrics.
                "pg_owned": False,
            },
        )


def remove_pg_periodic_tasks(apps, schema_editor):
    periodic_task = apps.get_model("pg_queue", "PgPeriodicTask")
    periodic_task.objects.filter(
        name__in=[spec["name"] for spec in PG_PERIODIC_TASKS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0003_agentkvjob_cleanup_failed_at"),
        # The table this seeds.
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(create_pg_periodic_tasks, remove_pg_periodic_tasks),
    ]
