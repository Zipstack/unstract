"""Split the metrics aggregation into two schedules by tier (UN-3974).

The hourly tier keeps its 15-minute cadence; the daily and monthly tiers move to
hourly, taking the expensive DAY-granularity half of the work from 96 runs a day to
24. Both rows run the same task and differ only in their ``tier`` kwargs — a second
task name would need its own worker registration and internal endpoint.

Beat and PG rows are declared here from one spec, so this pair cannot drift the way
0002 and 0004 can. Beat stores kwargs as a JSON string, PgPeriodicTask decoded. The
new row inherits whichever scheduler owns the row it is split from, rather than
hardcoding Beat: it is one half of that row, and the same process should fire it.

The new row runs at minute 20 — off the ``*/15`` grid — so it never starts alongside
the hourly-tier run, whose per-tier lock is deliberately unable to block it.

**Rolling back the code past this release requires reversing this migration too.**
After it runs both scheduler rows carry a ``tier`` kwarg that the previous release's
zero-argument signatures reject with ``TypeError``, which ``autoretry_for`` does not
cover — aggregation would stop for both tiers until ``migrate dashboard_metrics 0005``
restores the single row.
"""

import json

from django.db import migrations
from django.utils import timezone

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
        # Off the */15 grid (:00 :15 :30 :45): the per-tier locks are built so the
        # two runs cannot block each other, so a shared minute means two full
        # prefilter scans and two per-org loops at once. Same cadence, no overlap.
        "cron_string": "20 * * * *",
        "crontab": {"minute": "20", "hour": "*"},
        "description": (
            "Aggregate the daily and monthly dashboard metrics tiers from source "
            "tables — hourly, since these figures do not need 15-minute freshness"
        ),
        "exists": False,
    },
]


def _inherited_ownership(periodic_task_model, pg_periodic_task_model):
    """Which scheduler fires the row being split, so its other half matches.

    Hardcoding Beat would leave the daily/monthly tier with no firer wherever the
    metrics periodics are already PG-adopted: the adopted row's Beat twin is disabled
    and Beat may not be running at all.
    """
    beat = periodic_task_model.objects.filter(name=EXISTING_AGGREGATE_ROW).first()
    pg = pg_periodic_task_model.objects.filter(name=EXISTING_AGGREGATE_ROW).first()
    return {
        "beat_enabled": True if beat is None else beat.enabled,
        "pg_enabled": True if pg is None else pg.enabled,
        "pg_owned": False if pg is None else pg.pg_owned,
    }


def split_schedules(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PgPeriodicTask = apps.get_model("pg_queue", "PgPeriodicTask")
    owner = _inherited_ownership(PeriodicTask, PgPeriodicTask)

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
                "enabled": owner["beat_enabled"],
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
                "enabled": owner["pg_enabled"],
                "pg_owned": owner["pg_owned"],
            },
        )

    _bump_beat_change_tracker(apps)


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
    _bump_beat_change_tracker(apps)


def _bump_beat_change_tracker(apps):
    """Make a running Beat reload instead of keeping the pre-split schedule.

    django-celery-beat's post_save receiver binds the concrete PeriodicTask, so writes
    through a historical model never bump PeriodicTasks.last_update and
    DatabaseScheduler keeps its in-memory copy: the existing row would go on firing
    with no tier and the new row would never fire at all — the whole saving silently
    not happening. Same fix and reason as scheduler/ownership.py and
    mirror_pg_periodic_tasks.py.
    """
    periodic_tasks_model = apps.get_model("django_celery_beat", "PeriodicTasks")
    periodic_tasks_model.objects.update_or_create(
        ident=1, defaults={"last_update": timezone.now()}
    )


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard_metrics", "0005_add_reconciliation_task"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("pg_queue", "0003_pgperiodictask"),
    ]

    operations = [
        migrations.RunPython(split_schedules, merge_schedules),
    ]
