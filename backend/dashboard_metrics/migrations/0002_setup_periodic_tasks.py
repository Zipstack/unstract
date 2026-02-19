"""Data migration to create periodic tasks for dashboard metrics.

Creates three periodic tasks:
- Aggregation: Every 15 minutes, queries source tables and populates
  EventMetricsHourly, EventMetricsDaily, and EventMetricsMonthly
- Hourly cleanup: Daily at 2:00 AM UTC, removes hourly data older than 30 days
- Daily cleanup: Weekly on Sundays at 3:00 AM UTC, removes daily data older than 365 days
"""

from django.db import migrations


def create_periodic_tasks(apps, schema_editor):
    """Create all periodic tasks for metrics processing."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # --- Aggregation task: every 15 minutes ---
    schedule_15min, _ = IntervalSchedule.objects.get_or_create(
        every=15,
        period="minutes",
    )

    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_aggregate_from_sources",
        defaults={
            "task": "dashboard_metrics.aggregate_from_sources",
            "interval": schedule_15min,
            "queue": "dashboard_metric_events",
            "enabled": True,
            "description": (
                "Aggregate metrics from source tables (Usage, PageUsage, etc.) "
                "into hourly, daily, and monthly metrics tables"
            ),
        },
    )

    # --- Hourly cleanup task: daily at 2:00 AM UTC ---
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
            "queue": "dashboard_metric_events",
            "kwargs": '{"retention_days": 30}',
            "enabled": True,
            "description": "Clean up hourly dashboard metrics older than 30 days",
        },
    )

    # --- Daily cleanup task: weekly on Sundays at 3:00 AM UTC ---
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
            "queue": "dashboard_metric_events",
            "kwargs": '{"retention_days": 365}',
            "enabled": True,
            "description": "Clean up daily dashboard metrics older than 365 days",
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    """Remove all periodic tasks on rollback."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    PeriodicTask.objects.filter(
        name__in=[
            "dashboard_metrics_aggregate_from_sources",
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
            create_periodic_tasks,
            remove_periodic_tasks,
        ),
    ]
