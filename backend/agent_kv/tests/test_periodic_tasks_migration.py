"""One owner for the two maintenance schedules, and it is the CronJob.

History, because the test's shape only makes sense with it: an earlier revision
of migration 0004 SEEDED two ``PgPeriodicTask`` rows to fire
``agent_kv.sweep`` and ``agent_kv.ttl_cleanup``, answering a review finding
about the sweep never running. The finding was real; the fix was redundant.
``templates/backend/agent-kv-cronjobs.yaml`` in the cloud chart already ran the
same two management commands, added earlier on the same branch, so the
migration's stated premise -- "no ``PgPeriodicTask``, no beat entry, no
CronJob" -- was false about its own tree.

The rows were seeded ``pg_owned: False`` and the PG scheduler claims only
``WHERE pg_owned AND enabled``, so nothing double-fired yet. That is the
dangerous kind of correct: the flag exists to be flipped, and a flip would have
put a ``*/10`` sweep against the chart's ``*/15`` -- colliding at ``:30``,
contending on the same job rows -- with TTL cadences disagreeing 24x.

So 0004 now DELETES those rows and the CronJob is the sole owner. What these
tests defend is that decision, in the two ways it can be undone: someone
re-pointing the forward operation at the seeding function, or someone dropping
the reverse and making the migration one-way.

The name/queue assertions are kept rather than deleted -- they still guard the
reverse path, and the same wire names are what the CronJob's management
commands resolve to.
"""

import importlib
import inspect

import pytest
from django.db import migrations

# The module name starts with a digit, so it cannot be a plain `import`.
MIGRATION = importlib.import_module("agent_kv.migrations.0004_pg_periodic_tasks")

#: Wire names registered by `@worker_task(name=...)` in
#: `workers/scheduler/agent_kv_tasks.py`. Duplicated as literals on purpose:
#: the workers package is not importable from the backend's test venv, and an
#: import would make this pass vacuously wherever it is absent -- which is
#: exactly the environment where the two sides drift apart.
WORKER_TASK_NAMES = {"agent_kv.sweep", "agent_kv.ttl_cleanup"}


def _specs() -> dict:
    return {spec["name"]: spec for spec in MIGRATION.PG_PERIODIC_TASKS}


def _run_python_ops() -> list:
    return [
        op
        for op in MIGRATION.Migration.operations
        if isinstance(op, migrations.RunPython)
    ]


# ---------------------------------------------------------------------------
# The ownership decision.
# ---------------------------------------------------------------------------


def test_the_migration_still_has_a_runpython_operation():
    """Guards the empty-operations failure mode.

    Every other assertion in this file reads `PG_PERIODIC_TASKS` or a function's
    source, so `operations = []` would leave the whole suite green while the
    migration did nothing at all -- applying cleanly and leaving the seeded rows
    in place in every environment that already has them.
    """
    assert len(_run_python_ops()) == 1, MIGRATION.Migration.operations


def test_the_forward_operation_removes_the_rows_rather_than_seeding_them():
    """The decision itself.

    If this fails, someone has re-pointed forward at `create_pg_periodic_tasks`
    and there are two owners for one schedule again. Read the migration's
    docstring before changing it: the collision is at `:30`, and only the
    CronJob side carries `concurrencyPolicy: Forbid` and a deadline.
    """
    assert _run_python_ops()[0].code is MIGRATION.remove_pg_periodic_tasks


def test_the_migration_is_reversible():
    """`migrate agent_kv 0003` must land back on the previous tree's state.

    An irreversible data migration here would mean a rollback of this release
    leaves an environment with no rows and no way to restore them except by
    hand -- and the seeding revision is what the previous release shipped.
    """
    op = _run_python_ops()[0]

    assert op.reverse_code is MIGRATION.create_pg_periodic_tasks
    assert op.reverse_code is not migrations.RunPython.noop


def test_removal_is_idempotent_and_targets_only_the_two_seeded_names():
    """A fresh install has no such rows, and re-running must still succeed.

    Equally important: the delete is scoped by name. An unscoped
    `PgPeriodicTask.objects.all().delete()` here would wipe the
    dashboard_metrics periodics this migration sits alongside.
    """
    source = inspect.getsource(MIGRATION.remove_pg_periodic_tasks)

    assert "name__in=" in source, "the delete must be scoped by name"
    assert ".all()" not in source


# ---------------------------------------------------------------------------
# The reverse path's contents, and the names the CronJob commands share.
# ---------------------------------------------------------------------------


def test_both_maintenance_tasks_are_accounted_for():
    assert set(_specs()) == {"agent_kv_sweep", "agent_kv_ttl_cleanup"}


def test_every_row_points_at_a_task_the_worker_registers():
    """A row naming a task nothing registers is a schedule that fires into
    nothing. Still live for the reverse path, and the same wire names back the
    `agent_kv_sweep` / `agent_kv_ttl_cleanup` management commands the CronJob
    invokes.
    """
    declared = {spec["task_name"] for spec in MIGRATION.PG_PERIODIC_TASKS}

    assert declared == WORKER_TASK_NAMES, (
        f"migration names {sorted(declared)} but workers/scheduler/"
        f"agent_kv_tasks.py registers {sorted(WORKER_TASK_NAMES)}"
    )


@pytest.mark.parametrize("name", ["agent_kv_sweep", "agent_kv_ttl_cleanup"])
def test_rows_are_scheduled_onto_the_scheduler_queue(name):
    assert _specs()[name]["queue"] == "scheduler"


@pytest.mark.parametrize("name", ["agent_kv_sweep", "agent_kv_ttl_cleanup"])
def test_cron_strings_are_five_field_and_parseable(name):
    """A malformed cron string is accepted by the column and then never fires."""
    fields = _specs()[name]["cron_string"].split()

    assert len(fields) == 5, _specs()[name]["cron_string"]


def test_the_restored_rows_are_inert():
    """`pg_owned: False` on the reverse path too.

    A reverse that restored them ENABLED would turn a rollback into the
    double-fire this migration exists to prevent.
    """
    source = inspect.getsource(MIGRATION.create_pg_periodic_tasks)

    assert '"pg_owned": False' in source
    assert "update_or_create" in source, "re-running must stay idempotent"


def test_restored_rows_are_platform_wide():
    """Both internal endpoints sweep across every organization (spec §5.4), so a
    non-empty `org_id` would scope them to one tenant and silently leave every
    other org unswept.
    """
    source = inspect.getsource(MIGRATION.create_pg_periodic_tasks)

    assert '"org_id": ""' in source
    assert '"enabled": True' in source
