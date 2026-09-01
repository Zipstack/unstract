"""Data migration to schedule the daily-tier reconciliation pass.

The 15-minute aggregation reads a narrow source window, which cannot repair
gaps left by cron downtime. This runs the same task once a day at a wider
window to backfill them.
"""

from django.db import migrations

RECONCILE_TASK_NAME = "dashboard_metrics_reconcile_source_window"


def create_reconciliation_task(apps, schema_editor):
    """Create the once-daily reconciliation periodic task."""
    crontab_model = apps.get_model("django_celery_beat", "CrontabSchedule")
    periodic_task_model = apps.get_model("django_celery_beat", "PeriodicTask")

    # 4:00 AM UTC — clear of the 2:00 and 3:00 cleanup tasks
    schedule_4am, _ = crontab_model.objects.get_or_create(
        minute="0",
        hour="4",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    periodic_task_model.objects.update_or_create(
        name=RECONCILE_TASK_NAME,
        defaults={
            "task": "dashboard_metrics.aggregate_from_sources",
            "crontab": schedule_4am,
            "queue": "dashboard_metric_events",
            "kwargs": '{"source_window_days": 7}',
            "enabled": True,
            "description": (
                "Re-aggregate metrics over a 7 day source window to repair "
                "daily-tier gaps left by cron downtime"
            ),
        },
    )


def remove_reconciliation_task(apps, schema_editor):
    """Remove the reconciliation periodic task on rollback."""
    periodic_task_model = apps.get_model("django_celery_beat", "PeriodicTask")
    periodic_task_model.objects.filter(name=RECONCILE_TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0004_pg_periodic_tasks"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(
            create_reconciliation_task,
            remove_reconciliation_task,
        ),
    ]
