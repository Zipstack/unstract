"""Data migration to create the periodic cleanup task for dashboard metrics."""

from django.db import migrations


def create_cleanup_periodic_task(apps, schema_editor):
    """Create the periodic task for cleanup."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Schedule: Daily at 2:00 AM UTC
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    # Create or update the periodic task for hourly cleanup
    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_cleanup_hourly",
        defaults={
            "task": "dashboard_metrics.cleanup_hourly_data",
            "crontab": schedule,
            "enabled": True,
            "description": "Clean up hourly dashboard metrics older than 30 days",
        },
    )


def remove_cleanup_periodic_task(apps, schema_editor):
    """Remove the periodic task on rollback."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    PeriodicTask.objects.filter(name="dashboard_metrics_cleanup_hourly").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0001_initial"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(
            create_cleanup_periodic_task,
            remove_cleanup_periodic_task,
        ),
    ]
