"""Split the metrics aggregation into two schedules by tier (UN-3974).

Before this, one schedule ran every 15 minutes and wrote all three tiers. Dashboard
daily and monthly figures do not need 15-minute freshness, so they move to hourly:
96 runs a day becomes 24 for the expensive DAY-granularity half of the work, while the
hourly tier keeps its 15-minute cadence.

Both rows point at the SAME task (``dashboard_metrics.aggregate_from_sources``) and
differ only in ``tier`` kwargs. A second task name would need its own worker-side
registration and internal endpoint for the PG path; a kwarg needs neither.

**Beat and PG rows are declared together here, from one spec.** ``0002_setup_periodic_tasks``
(Beat) and ``0004_pg_periodic_tasks`` (PG) declare the same schedules in two places, and
``tests/test_pg_periodic_task_declarations.py`` exists to catch them drifting apart. One
spec written twice by the same function cannot drift, so this migration needs no such
guard. ``AGGREGATION_SCHEDULES`` is module-level so a future test can import it.

Rows land consistent with how each scheduler expects them:

* Beat ``kwargs`` is a JSON *string*; ``PgPeriodicTask.task_kwargs`` is a JSONField, so
  it is stored decoded.
* The new PG row lands **inert** (``pg_owned=False``, ``next_run_at=NULL``) for the same
  reason as ``0004`` — the PG scheduler skips rows it does not own, and a NULL
  ``next_run_at`` records a baseline next tick rather than firing a catch-up burst.

Reverse restores the pre-split state: the new rows are deleted and the aggregate row's
kwargs are cleared, putting it back to writing all three tiers every 15 minutes.
"""

import json

from django.db import migrations

AGGREGATE_TASK_NAME = "dashboard_metrics.aggregate_from_sources"
AGGREGATE_QUEUE = "dashboard_metric_events"

# Frozen literals — migrations must not import app enums. Kept in step with
# dashboard_metrics.tasks.AggregationTier.
TIER_HOURLY = "hourly"
TIER_DAILY_MONTHLY = "daily_monthly"

# The row that already exists (created by 0002 / 0004); only its kwargs and
# description change, its every-15-minutes schedule does not.
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
            # Keep the existing IntervalSchedule — only the payload changes.
            PeriodicTask.objects.filter(name=spec["name"]).update(
                kwargs=json.dumps(kwargs), description=spec["description"]
            )
        else:
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
    """Restore the single every-15-minutes row that writes all three tiers."""
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
        ("dashboard_metrics", "0004_pg_periodic_tasks"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(split_schedules, merge_schedules),
    ]
