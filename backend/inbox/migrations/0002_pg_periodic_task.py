"""Declare the daily inbox purge for the PG scheduler.

Seeded inert (``pg_owned=False``, ``next_run_at`` NULL), as dashboard_metrics 0004
does: ``converge_pg_scheduler --periodics`` adopts it, so nothing fires from this
migration and there is no catch-up burst. No Celery Beat twin: the purge exists only
on the PG scheduler.
"""

from django.db import migrations

NAME = "inbox_purge"


def create_pg_periodic_task(apps, schema_editor):
    apps.get_model("pg_queue", "PgPeriodicTask").objects.update_or_create(
        name=NAME,
        defaults={
            "task_name": "inbox.purge",
            # A quick DELETE, so the pipeline-trigger consumer drains it.
            "queue": "scheduler",
            "task_args": [],
            "task_kwargs": {},
            "cron_string": "30 2 * * *",
            "org_id": "",
            "enabled": True,
            "pg_owned": False,
        },
    )


def remove_pg_periodic_task(apps, schema_editor):
    apps.get_model("pg_queue", "PgPeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inbox", "0001_initial"),
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(create_pg_periodic_task, remove_pg_periodic_task),
    ]
