"""Declare the dashboard-metrics periodics for the PG scheduler (UN-3796).

The PG twin of ``0002_setup_periodic_tasks``, which declares the same three schedules
for Celery Beat. **Deliberately in this app rather than in ``pg_queue``**: the failure
mode that matters is the two declarations drifting apart, and a reviewer editing a
schedule sees both only if they sit side by side.

Why a data migration here, when the pipeline mirror is a management command: these are
three fixed rows known at build time, so a migration is the right tool — tiny, idempotent
(``update_or_create``), and it reaches every environment including on-prem with no
operator step. Pipeline schedules are bulk and per-environment, so they stay a chunked
command that runs outside the migrate transaction.

Rows land **inert**: ``pg_owned=False`` and ``next_run_at=NULL``. Nothing fires from this
migration — the PG scheduler skips rows it does not own, and a NULL ``next_run_at`` means
"record a baseline next tick" rather than "overdue, fire now", so enabling the flag never
produces a burst of catch-up runs.

``task_kwargs`` is stored **decoded**: Beat keeps ``kwargs`` as a JSON *string*
(``'{"retention_days": 30}'``) while ``PgPeriodicTask.task_kwargs`` is a JSONField, so the
dispatcher can build a payload without re-parsing per tick.
"""

from django.db import migrations

# Single source for both directions, and importable by the drift test. Mirrors the Beat
# declarations in 0002_setup_periodic_tasks one-for-one — same names (the mirror key is
# PeriodicTask.name), same queue, same kwargs, and cron strings equivalent to the
# IntervalSchedule/CrontabSchedule rows there.
PG_PERIODIC_TASKS = [
    {
        "name": "dashboard_metrics_aggregate_from_sources",
        "task_name": "dashboard_metrics.aggregate_from_sources",
        "queue": "dashboard_metric_events",
        "task_args": [],
        "task_kwargs": {},
        # Beat: IntervalSchedule(every=15, period="minutes")
        "cron_string": "*/15 * * * *",
    },
    {
        "name": "dashboard_metrics_cleanup_hourly",
        "task_name": "dashboard_metrics.cleanup_hourly_data",
        "queue": "dashboard_metric_events",
        "task_args": [],
        "task_kwargs": {"retention_days": 30},
        # Beat: CrontabSchedule(minute=0, hour=2, every day) UTC
        "cron_string": "0 2 * * *",
    },
    {
        "name": "dashboard_metrics_cleanup_daily",
        "task_name": "dashboard_metrics.cleanup_daily_data",
        "queue": "dashboard_metric_events",
        "task_args": [],
        "task_kwargs": {"retention_days": 365},
        # Beat: CrontabSchedule(minute=0, hour=3, day_of_week=0 → Sunday) UTC
        "cron_string": "0 3 * * 0",
    },
]


def create_pg_periodic_tasks(apps, schema_editor):
    PgPeriodicTask = apps.get_model("pg_queue", "PgPeriodicTask")
    for spec in PG_PERIODIC_TASKS:
        PgPeriodicTask.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task_name": spec["task_name"],
                "queue": spec["queue"],
                "task_args": spec["task_args"],
                "task_kwargs": spec["task_kwargs"],
                "cron_string": spec["cron_string"],
                "org_id": "",
                "enabled": True,
                # Inert until the rollout flag decides otherwise; never fired by
                # applying this migration.
                "pg_owned": False,
            },
        )


def remove_pg_periodic_tasks(apps, schema_editor):
    PgPeriodicTask = apps.get_model("pg_queue", "PgPeriodicTask")
    PgPeriodicTask.objects.filter(
        name__in=[spec["name"] for spec in PG_PERIODIC_TASKS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0003_alter_eventmetricsdaily_organization_and_more"),
        # The table this seeds.
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(create_pg_periodic_tasks, remove_pg_periodic_tasks),
    ]
