"""One owner for the two maintenance schedules, and it is the CronJob.

History, because the test's shape only makes sense with it: migration 0004
SEEDS two ``PgPeriodicTask`` rows to fire
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

So **0007** deletes those rows and the CronJob is the sole owner. 0004 is left
seeding, deliberately: Django records a migration as applied and never re-runs
it, so editing 0004 would have had no effect in the environments that actually
have the rows (every dev namespace that applied it) while silently rewriting
history for fresh ones. The first cut of this fix did exactly that and claimed
in its own docstring to clean up environments it could not reach. Verified both
ways against a real database -- a fresh install seeds then deletes, an
already-seeded one just deletes, and both land on zero rows with the five
dashboard_metrics periodics untouched.

What these tests defend is that arrangement, in the three ways it can be
undone: someone pointing 0007's forward operation at the restore function,
someone dropping its reverse and making it one-way, or someone "simplifying"
the removal back into an edit of 0004.

The name/queue assertions are kept rather than deleted -- they still guard the
reverse path, and the same wire names are what the CronJob's management
commands resolve to.
"""

import importlib
import inspect

import pytest
from django.db import migrations

# The module name starts with a digit, so it cannot be a plain `import`.
SEEDER = importlib.import_module("agent_kv.migrations.0004_pg_periodic_tasks")
MIGRATION = importlib.import_module(
    "agent_kv.migrations.0007_remove_agent_kv_periodic_tasks"
)

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

    If this fails, someone has re-pointed forward at the restore function and
    there are two owners for one schedule again. Read the migration's docstring
    before changing it: the collision is at `:30`, and only the CronJob side
    carries `concurrencyPolicy: Forbid` and a deadline.
    """
    assert _run_python_ops()[0].code is MIGRATION.remove_pg_periodic_tasks


def test_the_removal_is_its_own_migration_not_an_edit_to_the_seeder():
    """Django never re-runs an applied migration.

    0004 is recorded as applied in every environment that has these rows, so
    rewriting ITS forward operation cleans up nothing there -- it only changes
    what a fresh install does. That was the first cut of this fix, and its
    docstring claimed to clean environments it could not reach.

    So 0004 must still seed, and the removal must live in a later migration
    that those environments have yet to apply.
    """
    seeder_ops = [
        op
        for op in SEEDER.Migration.operations
        if isinstance(op, migrations.RunPython)
    ]

    assert len(seeder_ops) == 1
    assert seeder_ops[0].code is SEEDER.create_pg_periodic_tasks, (
        "0004 must keep SEEDING. If the removal was folded back into it, every "
        "environment that already applied 0004 keeps its rows forever and this "
        "fix reaches none of them."
    )
    assert MIGRATION is not SEEDER
    assert ("agent_kv", "0006_agentkvjob_adapters") in MIGRATION.Migration.dependencies


def test_the_removal_targets_exactly_what_the_seeder_created():
    """One source of truth for the row names.

    0007 reads `PG_PERIODIC_TASKS` out of 0004 rather than re-declaring it, so
    the two cannot drift into deleting a different set than was seeded. If
    someone copies the list instead, this fails.
    """
    assert MIGRATION.PG_PERIODIC_TASKS is SEEDER.PG_PERIODIC_TASKS


def test_the_migration_is_reversible():
    """`migrate agent_kv 0003` must land back on the previous tree's state.

    An irreversible data migration here would mean a rollback of this release
    leaves an environment with no rows and no way to restore them except by
    hand -- and the seeding revision is what the previous release shipped.
    """
    op = _run_python_ops()[0]

    assert op.reverse_code is MIGRATION.restore_pg_periodic_tasks
    assert op.reverse_code is not migrations.RunPython.noop


def test_the_removal_spares_a_schedule_the_operator_has_taken_OWNERSHIP_of():
    """`pg_owned=True` means a self-hosted operator is relying on this row.

    These rows are seeded inert, so deleting an inert one removes the
    accidental second owner and nothing else. But a self-hosted operator
    running the PG scheduler has every reason to flip `pg_owned: True` -- the
    docs tell them to, and there is no CronJob outside the cloud chart to
    replace it. Deleting by NAME alone would silently remove their only
    maintenance mechanism: stuck jobs stop being swept and hold their
    concurrency slots until the 6 h Redis TTL, and expired customer documents
    stay in the bucket indefinitely, with nothing reporting either.

    Verified end to end against a real database as well (flip one row to
    `pg_owned=True`, migrate, and exactly that row survives); this pins the
    predicate so the scope cannot quietly widen back to name-only.
    """
    source = inspect.getsource(MIGRATION.remove_pg_periodic_tasks)

    assert "pg_owned=False" in source, (
        "the delete must spare rows an operator has taken ownership of; "
        "name-only scoping strands a self-hosted deployment's maintenance"
    )


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


def test_the_reverse_does_not_overwrite_a_row_it_finds():
    """`get_or_create`, never `update_or_create`.

    Forward leaves a row alone when the operator has adopted it
    (`pg_owned=True`), so on a rollback that row is still present. An
    `update_or_create` whose defaults carry `pg_owned: False` would reset it --
    silently disabling a self-hosted operator's only maintenance mechanism as a
    side effect of rolling back an unrelated release.

    The reverse's job is to restore what forward REMOVED, not to normalize what
    it deliberately preserved.

    Verified end to end against a real database too: adopt one row, migrate
    forward (it survives), roll back, and it is still `pg_owned=True` while the
    deleted sibling comes back inert.
    """
    # The CALL, not the prose: the docstring names `update_or_create` to
    # explain why it is not used, so a bare substring check on the source
    # fails on its own explanation.
    source = inspect.getsource(MIGRATION.restore_pg_periodic_tasks)

    assert ".objects.get_or_create(" in source, (
        "the reverse must not overwrite an existing row's ownership"
    )
    assert ".objects.update_or_create(" not in source, (
        "`update_or_create` resets `pg_owned` on a row forward deliberately "
        "preserved, disabling a self-hosted operator's maintenance on rollback"
    )


def test_the_restored_rows_are_inert():
    """`pg_owned: False` on the reverse path too.

    A reverse that restored them ENABLED would turn a rollback into the
    double-fire this migration exists to prevent.
    """
    source = inspect.getsource(MIGRATION.restore_pg_periodic_tasks)

    assert '"pg_owned": False' in source
    assert "update_or_create" in source, "re-running must stay idempotent"


def test_restored_rows_are_platform_wide():
    """Both internal endpoints sweep across every organization (spec §5.4), so a
    non-empty `org_id` would scope them to one tenant and silently leave every
    other org unswept.
    """
    source = inspect.getsource(MIGRATION.restore_pg_periodic_tasks)

    assert '"org_id": ""' in source
    assert '"enabled": True' in source
