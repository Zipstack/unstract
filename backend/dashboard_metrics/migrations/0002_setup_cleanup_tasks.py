"""Data migration to create periodic cleanup tasks for dashboard metrics."""

from django.db import migrations


def create_cleanup_tasks(apps, schema_editor):
    """Create periodic tasks for metrics cleanup."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Schedule for hourly cleanup: Daily at 2:00 AM UTC
    schedule_2am, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    # Create periodic task for hourly metrics cleanup
    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_cleanup_hourly",
        defaults={
            "task": "dashboard_metrics.cleanup_hourly_data",
            "crontab": schedule_2am,
            "queue": "dashboard_metric_events",
            "kwargs": '{"retention_days": 30}',
            "enabled": True,
            "description": "Clean up hourly dashboard metrics older than 30 days",
        },
    )

    # Schedule for daily cleanup: Weekly on Sundays at 3:00 AM UTC
    schedule_3am_sun, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_week="0",  # Sunday
        day_of_month="*",
        month_of_year="*",
        defaults={"timezone": "UTC"},
    )

    # Create periodic task for daily metrics cleanup
    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_cleanup_daily",
        defaults={
            "task": "dashboard_metrics.cleanup_daily_data",
            "crontab": schedule_3am_sun,
            "queue": "dashboard_metric_events",
            "kwargs": '{"retention_days": 365}',
            "enabled": True,
            "description": "Clean up daily dashboard metrics older than 365 days",
        },
    )


def remove_cleanup_tasks(apps, schema_editor):
    """Remove periodic tasks on rollback."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    PeriodicTask.objects.filter(
        name__in=[
            "dashboard_metrics_cleanup_hourly",
            "dashboard_metrics_cleanup_daily",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0001_initial"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(
            create_cleanup_tasks,
            remove_cleanup_tasks,
        ),
    ]
