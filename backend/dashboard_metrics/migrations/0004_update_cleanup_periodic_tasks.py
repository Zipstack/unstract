"""Data migration to update periodic cleanup tasks for dashboard metrics.

Updates the hourly cleanup task name and adds a new daily cleanup task.
"""

from django.db import migrations


def update_periodic_tasks(apps, schema_editor):
    """Update hourly cleanup task and add daily cleanup task."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Handle legacy task name (cleanup_old_data) or already correct name
    # Delete any legacy task with old name
    PeriodicTask.objects.filter(name="dashboard_metrics_cleanup").delete()

    # Update or create hourly cleanup task with correct configuration
    schedule_2am, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )
    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_cleanup_hourly",
        defaults={
            "task": "dashboard_metrics.cleanup_hourly_data",
            "crontab": schedule_2am,
            "kwargs": '{"retention_days": 30}',
            "enabled": True,
            "description": "Clean up hourly dashboard metrics older than 30 days",
        },
    )

    # Create weekly cleanup task for daily metrics at 3:00 AM UTC on Sundays
    schedule_3am_sun, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_week="0",  # Sunday
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_cleanup_daily",
        defaults={
            "task": "dashboard_metrics.cleanup_daily_data",
            "crontab": schedule_3am_sun,
            "kwargs": '{"retention_days": 365}',
            "enabled": True,
            "description": "Clean up daily dashboard metrics older than 365 days",
        },
    )


def revert_periodic_tasks(apps, schema_editor):
    """Revert: delete daily cleanup task (hourly task managed by 0002)."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Delete the daily cleanup task added by this migration
    PeriodicTask.objects.filter(name="dashboard_metrics_cleanup_daily").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0003_add_daily_monthly_tables"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(
            update_periodic_tasks,
            revert_periodic_tasks,
        ),
    ]
