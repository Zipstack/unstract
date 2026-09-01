"""Split the metrics aggregation into two schedules by tier (UN-3974).

The hourly tier keeps its 15-minute cadence; the daily and monthly tiers move to
hourly, taking the expensive DAY-granularity half of the work from 96 runs a day to
24. Both rows run the same task and differ only in their ``tier`` kwargs — a second
task name would need its own worker registration and internal endpoint.

Beat and PG rows are declared here from one spec, so this pair cannot drift the way
0002 and 0004 can. Beat stores kwargs as a JSON string, PgPeriodicTask decoded. The
new PG row lands inert (``pg_owned=False``) like 0004's.
"""

import json

from django.db import migrations

AGGREGATE_TASK_NAME = "dashboard_metrics.aggregate_from_sources"
AGGREGATE_QUEUE = "dashboard_metric_events"

# Frozen literals — migrations must not import app enums. Kept in step with
# dashboard_metrics.tasks.AggregationTier.
TIER_HOURLY = "hourly"
TIER_DAILY_MONTHLY = "daily_monthly"

# Created by 0002 / 0004; only its kwargs and description change here.
EXISTING_AGGREGATE_ROW = "dashboard_metrics_aggregate_from_sources"

AGGREGATION_SCHEDULES = [
    {
        "name": EXISTING_AGGREGATE_ROW,
        "tier": TIER_HOURLY,
        "cron_string": "*/15 * * * *",
        "crontab": {"minute": "*/15", "hour": "*"},
        "description": (
            "Aggregate the hourly dashboard metrics tier from source tables "
            "(Usage, PageUsage, WorkflowExecution, etc.)"
        ),
        "exists": True,
    },
    {
        "name": "dashboard_metrics_aggregate_daily_monthly",
        "tier": TIER_DAILY_MONTHLY,
        "cron_string": "0 * * * *",
        "crontab": {"minute": "0", "hour": "*"},
        "description": (
            "Aggregate the daily and monthly dashboard metrics tiers from source "
            "tables — hourly, since these figures do not need 15-minute freshness"
        ),
        "exists": False,
    },
]


def split_schedules(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PgPeriodicTask = apps.get_model("pg_queue", "PgPeriodicTask")

    for spec in AGGREGATION_SCHEDULES:
        kwargs = {"tier": spec["tier"]}

        if spec["exists"]:
            # Payload only. `enabled` and `pg_owned` say which scheduler fires this
            # row and belong to converge_pg_scheduler; rewriting them here can leave
            # an adopted row with no firer. Its cadence does not change.
            PeriodicTask.objects.filter(name=spec["name"]).update(
                kwargs=json.dumps(kwargs), description=spec["description"]
            )
            PgPeriodicTask.objects.filter(name=spec["name"]).update(task_kwargs=kwargs)
            continue

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=spec["crontab"]["minute"],
            hour=spec["crontab"]["hour"],
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            defaults={"timezone": "UTC"},
        )
        PeriodicTask.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task": AGGREGATE_TASK_NAME,
                "crontab": schedule,
                "queue": AGGREGATE_QUEUE,
                "kwargs": json.dumps(kwargs),
                "enabled": True,
                "description": spec["description"],
            },
        )
        PgPeriodicTask.objects.update_or_create(
            name=spec["name"],
            defaults={
                "task_name": AGGREGATE_TASK_NAME,
                "queue": AGGREGATE_QUEUE,
                "task_args": [],
                "task_kwargs": kwargs,
                "cron_string": spec["cron_string"],
                "org_id": "",
                "enabled": True,
                "pg_owned": False,
            },
        )


def merge_schedules(apps, schema_editor):
    """Restore the single every-15-minutes row that writes all three tiers.

    Leaves `enabled` / `pg_owned` alone, as the forward direction does.
    """
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PgPeriodicTask = apps.get_model("pg_queue", "PgPeriodicTask")

    added = [s["name"] for s in AGGREGATION_SCHEDULES if not s["exists"]]
    PeriodicTask.objects.filter(name__in=added).delete()
    PgPeriodicTask.objects.filter(name__in=added).delete()

    PeriodicTask.objects.filter(name=EXISTING_AGGREGATE_ROW).update(
        kwargs="{}",
        description=(
            "Aggregate metrics from source tables (Usage, PageUsage, etc.) "
            "into hourly, daily, and monthly metrics tables"
        ),
    )
    PgPeriodicTask.objects.filter(name=EXISTING_AGGREGATE_ROW).update(task_kwargs={})


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0005_add_reconciliation_task"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(split_schedules, merge_schedules),
    ]
