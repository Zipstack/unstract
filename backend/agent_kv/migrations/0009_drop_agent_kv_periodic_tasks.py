"""Finish what 0007 started: drop the Agent-KV periodics whatever their owner.

0007 deletes the two rows 0004 seeded, but only ``WHERE pg_owned = False``. On
a cloud deployment that guard spares **exactly** the rows that are
double-firing, so the collision 0007 exists to prevent is live in every
namespace that applied 0004 before 0007 landed. Observed on
``vishnu-unstract-dev`` running snapshot.415, with both owners in place::

    pg_periodic_task  agent_kv_sweep  pg_owned=t  */10
                      last_run = 2026-10-12 11:00:02
                      next_run = 2026-10-12 11:10:00
    CronJob  unstract-backend-agent-kv-sweep-cronjob  */15  (ran ~10:57)
    pod/unstract-worker-pg-scheduler  1/1  Running

Both tick. They meet at ``:30``, which is the collision the chart's offset
comment says it avoids, and ttl-cleanup disagrees with itself by 24x -- daily
on the PG row, hourly on the CronJob.

**Why 0007's guard does not hold: its premise is false.** 0007 reasons that
``pg_owned=True`` can only be a self-hosted operator's deliberate act, because
"nothing automated ever sets ``pg_owned=True``". Something does. The cloud
chart's ``backend.pgScheduleMirror`` hook runs ``converge_pg_scheduler
--periodics`` on post-install, post-upgrade AND post-rollback, which calls
``mirror_pg_periodic_tasks --adopt`` with no names -- and an empty name list
means ``PgPeriodicTask.objects.all()`` (``_set_ownership``), every row in the
table. ``templates/validate-pg-worker-fleet.yaml`` fails the render if that
hook is disabled, so it is not an opt-in an environment can decline.

That is the table's contract, not a bug in the hook: ``pg_periodic_task`` is
where the PG scheduler's rollout looks for what it owns, and
``dashboard_metrics`` seeds rows there inert precisely so the hook can turn
them on. A row in this table is a declaration that the PG scheduler should
fire it. The mistake was 0004 putting the Agent-KV schedules there while the
chart was already running them as CronJobs.

**So ``pg_owned=False`` is not a stable state here.** Setting the flag back
would last until the next ``helm upgrade`` re-adopted the row, which means
deletion is the only end state that holds. This is also why the fix cannot be
a values change or a one-off ``UPDATE``.

**Why the self-hosted operator 0007 protects cannot exist.** 0004 and its
removals ship in the SAME release; no released version has ever carried 0004
without one. At the moment this runs, therefore, the only rows named
``agent_kv_sweep`` / ``agent_kv_ttl_cleanup`` are rows 0004 seeded minutes (or,
for a dev namespace, weeks) earlier -- there was no published release in which
an operator could have found these names and adopted them deliberately.

The operator 0007 describes is a FUTURE one, who upgrades to this release and
then follows ``docs/agent-kv-api.md`` §12 and creates their own rows. Django
records a migration as applied and never re-runs it, so by the time they do,
this migration is already recorded and cannot touch what they create. The
guard protects nobody and spares the one case that needs fixing.

**Why a new migration rather than an edit to 0007.** The same reason 0007 is
not an edit to 0004, and the same mistake this branch has now made twice:
0007 is recorded as applied in every environment that has an adopted row, so
rewriting its predicate reaches none of them. The rule is cheap to restate --
a migration already applied is a historical record, and the only way to change
what a deployed database looks like is to add to the chain.

0007 stays as it is. Its docstring carries a pointer here.

**Reverse is a no-op, deliberately.** 0007's reverse already re-creates both
rows (inert) for a rollback that goes back past it, which is the state the
previous release shipped. Re-creating them here as well would mean a rollback
to 0008 restored the second owner -- turning the rollback into the double-fire
this migration removes -- and restoring them *adopted*, which is what forward
actually found, would restore it in its firing form. There is nothing this
step can put back that is safe to put back.

Self-hosted operators enabling the Agent-KV API still have to schedule
``manage.py agent_kv_sweep`` and ``manage.py agent_kv_ttl_cleanup``
themselves; see 0007's docstring and ``docs/agent-kv-api.md`` §12. Doing it
with their own ``PgPeriodicTask`` rows is still fine -- and on a deployment
with no CronJob, having the mirror hook adopt them is the correct outcome.
"""

import importlib

from django.db import migrations

#: Read from 0004 rather than re-declared, so this cannot drift into deleting a
#: different set than was seeded. `importlib` because the module name starts
#: with a digit. Same source 0007 reads.
PG_PERIODIC_TASKS = importlib.import_module(
    "agent_kv.migrations.0004_pg_periodic_tasks"
).PG_PERIODIC_TASKS


def drop_pg_periodic_tasks(apps, schema_editor):
    """Delete both rows by name, whatever ``pg_owned`` says.

    Scoped by name and nothing else. The name scope is load-bearing in the
    other direction from 0007's ownership scope: this table is shared with the
    five ``dashboard_metrics`` periodics, which the PG scheduler legitimately
    owns, so an unscoped delete would take the metrics pipeline down with it.

    Idempotent: 0007 has normally already removed the inert pair, and a fresh
    install matches nothing.
    """
    # snake_case for the historical model, as in 0004 and 0007: sonar's S117
    # reads the usual CamelCase local as a naming violation.
    periodic_task = apps.get_model("pg_queue", "PgPeriodicTask")
    names = [spec["name"] for spec in PG_PERIODIC_TASKS]
    periodic_task.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0008_agentkvjob_files_purged"),
    ]

    operations = [
        migrations.RunPython(drop_pg_periodic_tasks, migrations.RunPython.noop),
    ]
