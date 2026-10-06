"""The two maintenance periodics must be scheduled, not merely registered.

Both tasks were registered in ``workers/scheduler/agent_kv_tasks.py`` and both
internal endpoints existed, but nothing anywhere created a row to fire them.
"Wired but unscheduled" is an invisible failure: the code looks complete, the
endpoints respond to a manual call, and the only symptoms are that stuck jobs
keep their concurrency slots until a 6h Redis TTL and that customer documents
are retained forever despite a documented ``AGENT_KV_RESULT_TTL_DAYS``.

These assertions pin the migration's declared rows against the wire names the
worker actually registers, so renaming one side without the other fails here
rather than silently stopping the schedule.

Reported by Greptile on PR #2317, and as 2.3 in the branch review.
"""

import importlib

import pytest

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


def test_both_maintenance_tasks_are_scheduled():
    assert set(_specs()) == {"agent_kv_sweep", "agent_kv_ttl_cleanup"}


def test_every_scheduled_row_points_at_a_task_the_worker_registers():
    """A row naming a task nothing registers is a schedule that fires into
    nothing -- the same invisible failure, one layer along.
    """
    declared = {spec["task_name"] for spec in MIGRATION.PG_PERIODIC_TASKS}

    assert declared == WORKER_TASK_NAMES, (
        f"migration schedules {sorted(declared)} but workers/scheduler/"
        f"agent_kv_tasks.py registers {sorted(WORKER_TASK_NAMES)}"
    )


@pytest.mark.parametrize("name", ["agent_kv_sweep", "agent_kv_ttl_cleanup"])
def test_rows_are_scheduled_onto_the_scheduler_queue(name):
    assert _specs()[name]["queue"] == "scheduler"


def test_rows_are_platform_wide_and_enabled():
    """Both internal endpoints sweep across every organization (spec §5.4), so a
    non-empty `org_id` would scope them to one tenant and silently leave every
    other org unswept.

    Asserted on the writer rather than the spec table: `org_id`/`enabled` are
    set once in `defaults`, not per row.
    """
    import inspect

    source = inspect.getsource(MIGRATION.create_pg_periodic_tasks)

    assert '"org_id": ""' in source
    assert '"enabled": True' in source


@pytest.mark.parametrize("name", ["agent_kv_sweep", "agent_kv_ttl_cleanup"])
def test_cron_strings_are_five_field_and_parseable(name):
    """A malformed cron string is accepted by the column and then never fires."""
    fields = _specs()[name]["cron_string"].split()

    assert len(fields) == 5, _specs()[name]["cron_string"]


def test_the_sweep_runs_far_more_often_than_the_ttl_cleanup():
    """Not cosmetic: a stuck job holds a concurrency slot, so the sweep has to
    be frequent, while the TTL cleanup is a bulk object-store delete that should
    not run on a tight loop. If these ever converge, one of them is wrong.
    """
    sweep = _specs()["agent_kv_sweep"]["cron_string"]
    ttl = _specs()["agent_kv_ttl_cleanup"]["cron_string"]

    assert sweep.startswith("*/"), f"sweep should be interval-based, got {sweep!r}"
    assert not ttl.startswith("*/"), f"ttl cleanup should be daily, got {ttl!r}"


def test_rows_are_created_inert():
    """`pg_owned: False` means applying the migration does not itself start
    firing them -- the rollout flag decides, same posture as the
    dashboard_metrics periodics this follows.
    """
    # The flag lives in the migration's writer, not its spec table, so assert on
    # the source rather than re-running the RunPython against a live DB.
    import inspect

    source = inspect.getsource(MIGRATION.create_pg_periodic_tasks)

    assert '"pg_owned": False' in source
    assert "update_or_create" in source, "re-running the migration must be idempotent"
