"""Data migration to create periodic aggregation task for dashboard metrics."""

from django.db import migrations


def create_aggregation_task(apps, schema_editor):
    """Create periodic task for metrics aggregation from source tables."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Schedule for aggregation: Every 15 minutes
    schedule_15min, _ = IntervalSchedule.objects.get_or_create(
        every=15,
        period="minutes",
    )

    # Create periodic task for metrics aggregation
    PeriodicTask.objects.update_or_create(
        name="dashboard_metrics_aggregate_from_sources",
        defaults={
            "task": "dashboard_metrics.aggregate_from_sources",
            "interval": schedule_15min,
            "queue": "dashboard_metric_events",
            "enabled": True,
            "description": (
                "Aggregate metrics from source tables (Usage, PageUsage, etc.) "
                "into EventMetricsHourly for fast dashboard queries"
            ),
        },
    )


def remove_aggregation_task(apps, schema_editor):
    """Remove periodic task on rollback."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    PeriodicTask.objects.filter(
        name="dashboard_metrics_aggregate_from_sources"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0002_setup_cleanup_tasks"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(
            create_aggregation_task,
            remove_aggregation_task,
        ),
    ]
