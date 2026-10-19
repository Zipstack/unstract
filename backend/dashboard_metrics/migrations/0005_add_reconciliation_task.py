"""Data migration to schedule the daily-tier reconciliation pass.

The 15-minute aggregation reads a narrow source window, which cannot repair
gaps left by cron downtime. This runs the same task once a day at a wider
window to backfill them.

Declared for **both** transports, like 0002/0004: Beat reads
``django_celery_beat_periodictask``, the PG scheduler reads ``pg_periodic_task``,
and a schedule present on one only stops firing the moment the flag flips.
``kwargs`` is a JSON string on Beat and a JSONField on PG — same value, two
encodings.

The row carries ``source_window_days``, which the previous release's zero-argument
signatures reject with ``TypeError``. Rolling the code back past this release means
reversing this migration too, **before** the image rolls back — ``migrate
dashboard_metrics 0004``, which reverses 0006 and this one together.
"""

import json

from django.db import migrations
from django.utils import timezone

RECONCILE_TASK_NAME = "dashboard_metrics_reconcile_source_window"
EXISTING_AGGREGATE_ROW = "dashboard_metrics_aggregate_from_sources"
RECONCILE_DESCRIPTION = (
    "Re-aggregate metrics over a 7 day source window to repair "
    "daily-tier gaps left by cron downtime"
)

# Single source for both directions, and importable by the drift test.
PG_PERIODIC_TASKS = [
    {
        "name": RECONCILE_TASK_NAME,
        "task_name": "dashboard_metrics.aggregate_from_sources",
        "queue": "dashboard_metric_events",
        "task_args": [],
        # Scoped to the tier it repairs. Without a tier this runs ALL, and its
        # hourly half is pure duplicated work — the hourly tier always covers the
        # last 24h regardless of source_window_days — while being the only thing
        # that writes event_metrics_hourly concurrently with the */15 run, whose
        # per-tier lock is deliberately unable to block it.
        "task_kwargs": {"source_window_days": 7, "tier": "daily_monthly"},
        # Beat: CrontabSchedule(minute=40, hour=4, every day) UTC — clear of the
        # 2:00 and 3:00 cleanup tasks, and off the aggregation's */15 grid
        # (:00 :15 :30 :45). That separates the starts on the PG scheduler only:
        # the Beat aggregation row is an IntervalSchedule (0002), which fires at
        # last_run_at + 15min and drifts, so on that transport they can coincide.
        "cron_string": "40 4 * * *",
    },
]


def _inherited_ownership(periodic_task_model, pg_periodic_task_model):
    """Which scheduler fires the existing aggregation row, so this one matches.

    Hardcoding Beat would land the reconciliation pass with no firer wherever the
    metrics periodics are already PG-adopted: the adopted row's Beat twin is
    disabled and Beat may not be running at all. 0006 makes the same inference for
    the row it adds; this pass is the only automatic repair for the narrowed source
    window, so it is the worse one to strand.
    """
    beat = periodic_task_model.objects.filter(name=EXISTING_AGGREGATE_ROW).first()
    pg = pg_periodic_task_model.objects.filter(name=EXISTING_AGGREGATE_ROW).first()
    return {
        "beat_enabled": True if beat is None else beat.enabled,
        "pg_enabled": True if pg is None else pg.enabled,
        "pg_owned": False if pg is None else pg.pg_owned,
    }


def create_reconciliation_task(apps, schema_editor):
    """Create the once-daily reconciliation periodic task on both transports."""
    crontab_model = apps.get_model("django_celery_beat", "CrontabSchedule")
    periodic_task_model = apps.get_model("django_celery_beat", "PeriodicTask")
    pg_periodic_task_model = apps.get_model("pg_queue", "PgPeriodicTask")
    owner = _inherited_ownership(periodic_task_model, pg_periodic_task_model)

    schedule_4am, _ = crontab_model.objects.get_or_create(
        minute="40",
        hour="4",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    for spec in PG_PERIODIC_TASKS:
        periodic_task_model.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task": spec["task_name"],
                "crontab": schedule_4am,
                "queue": spec["queue"],
                "kwargs": json.dumps(spec["task_kwargs"]),
                "enabled": owner["beat_enabled"],
                "description": RECONCILE_DESCRIPTION,
            },
        )
        pg_periodic_task_model.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task_name": spec["task_name"],
                "queue": spec["queue"],
                "task_args": spec["task_args"],
                "task_kwargs": spec["task_kwargs"],
                "cron_string": spec["cron_string"],
                "org_id": "",
                "enabled": owner["pg_enabled"],
                # Inherited, not hardcoded: see _inherited_ownership.
                "pg_owned": owner["pg_owned"],
            },
        )

    _bump_beat_change_tracker(apps)


def remove_reconciliation_task(apps, schema_editor):
    """Remove the reconciliation periodic task from both transports."""
    names = [spec["name"] for spec in PG_PERIODIC_TASKS]
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
        name__in=names
    ).delete()
    apps.get_model("pg_queue", "PgPeriodicTask").objects.filter(name__in=names).delete()
    _bump_beat_change_tracker(apps)


def _bump_beat_change_tracker(apps):
    """Make a running Beat reload instead of missing the new schedule.

    django-celery-beat's post_save receiver binds the concrete PeriodicTask, so
    writes through a historical model never bump PeriodicTasks.last_update and
    DatabaseScheduler keeps its stale in-memory copy. Same fix and reason as
    scheduler/ownership.py and mirror_pg_periodic_tasks.py.
    """
    periodic_tasks_model = apps.get_model("django_celery_beat", "PeriodicTasks")
    periodic_tasks_model.objects.update_or_create(
        ident=1, defaults={"last_update": timezone.now()}
    )


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0004_pg_periodic_tasks"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(
            create_reconciliation_task,
            remove_reconciliation_task,
        ),
    ]
