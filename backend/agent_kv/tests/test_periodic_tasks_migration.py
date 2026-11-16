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

So **0007** deletes those rows and the CronJob is the sole owner -- except
that 0007 scopes its delete to ``pg_owned=False``, to spare a self-hosted
operator who had adopted the rows, on the stated premise that nothing
automated ever sets that flag. **That premise is false, and the collision
above stopped being hypothetical.** The cloud chart's
``backend.pgScheduleMirror`` hook runs ``converge_pg_scheduler --periodics``
on every install, upgrade and rollback; its blanket ``--adopt`` flips every
row in ``pg_periodic_task``; and ``validate-pg-worker-fleet.yaml`` refuses to
render with the hook off. Deploying snapshot.415 to a dev namespace found both
rows ``pg_owned=t`` with the PG scheduler firing ``agent_kv_sweep`` at
``*/10`` alongside the CronJob's ``*/15``. 0007's guard spares precisely the
rows that are double-firing, so **0009** repeats the delete by name alone.

0004 is left seeding, and 0007 is left guarding, deliberately: Django records a migration as applied and never re-runs
it, so editing 0004 would have had no effect in the environments that actually
have the rows (every dev namespace that applied it) while silently rewriting
history for fresh ones. The first cut of this fix did exactly that and claimed
in its own docstring to clean up environments it could not reach. Verified both
ways against a real database -- a fresh install seeds then deletes, an
already-seeded one just deletes, and both land on zero rows with the five
dashboard_metrics periodics untouched.

What these tests defend is that arrangement, in the ways it can be undone:
someone pointing 0007's forward operation at the restore function, someone
dropping its reverse and making it one-way, someone "simplifying" either
removal back into an edit of an earlier migration, or someone re-introducing
an ownership scope on 0009. The replay tests at the end are the behavioural
ones -- they run the whole chain against a fake row store and assert the end
state is zero ``agent_kv*`` rows whichever owner the hook left behind, with
the ``dashboard_metrics`` neighbours intact.

The name/queue assertions are kept rather than deleted -- they still guard the
reverse path, and the same wire names are what the CronJob's management
commands resolve to.
"""

import importlib
import inspect
import pathlib
import re

import pytest
from django.db import migrations

# The module name starts with a digit, so it cannot be a plain `import`.
SEEDER = importlib.import_module("agent_kv.migrations.0004_pg_periodic_tasks")
MIGRATION = importlib.import_module(
    "agent_kv.migrations.0007_remove_agent_kv_periodic_tasks"
)
DROP = importlib.import_module("agent_kv.migrations.0009_drop_agent_kv_periodic_tasks")

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


def test_0007_keeps_the_predicate_it_was_applied_with():
    """0007 is history now; widening it in place would reach nobody.

    Its `pg_owned=False` scope turned out to be wrong on cloud -- the chart's
    schedule-mirror hook adopts every row in `pg_periodic_task` on every
    sync, so the guard spares exactly the pair that is double-firing. The fix
    for that is 0009, NOT an edit here: 0007 is recorded as applied in every
    environment that has an adopted row, so changing this predicate would
    change only what a fresh install does, while the environments with the
    problem keep it. That is the same mistake the first cut of 0007 made
    against 0004, and this pins it shut.
    """
    source = inspect.getsource(MIGRATION.remove_pg_periodic_tasks)

    assert "pg_owned=False" in source, (
        "0007 has already been applied; widening its scope here fixes nothing "
        "in the environments that have the rows. Add a migration instead."
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
    # Idempotency is `get_or_create`, pinned by the test above. It used to be
    # asserted here as a bare `"update_or_create" in source`, which passed on
    # the docstring's own explanation of why that call is NOT used -- a check
    # that could never fail, standing in for one that mattered.


def test_restored_rows_are_platform_wide():
    """Both internal endpoints sweep across every organization (spec §5.4), so a
    non-empty `org_id` would scope them to one tenant and silently leave every
    other org unswept.
    """
    source = inspect.getsource(MIGRATION.restore_pg_periodic_tasks)

    assert '"org_id": ""' in source
    assert '"enabled": True' in source


# ---------------------------------------------------------------------------
# 0009: the delete that is not scoped by ownership.
# ---------------------------------------------------------------------------


def _drop_ops() -> list:
    return [
        op for op in DROP.Migration.operations if isinstance(op, migrations.RunPython)
    ]


def test_the_drop_still_has_a_runpython_operation():
    """Same empty-operations failure mode 0007 is guarded against."""
    assert len(_drop_ops()) == 1, DROP.Migration.operations


def test_the_drop_runs_the_delete_forward():
    assert _drop_ops()[0].code is DROP.drop_pg_periodic_tasks


def test_the_drop_is_a_new_migration_on_top_of_the_leaf():
    """Not an edit to 0007, for the reason 0007 is not an edit to 0004.

    0007 is recorded as applied in every environment holding an adopted row.
    Rewriting its predicate reaches none of them -- it changes only what a
    fresh install does, which is the one case that was never broken.
    """
    assert DROP is not MIGRATION
    assert ("agent_kv", "0008_agentkvjob_files_purged") in DROP.Migration.dependencies


def test_the_drop_restores_nothing_on_reverse():
    """Reversible, but as a no-op -- and that is the decision, not an omission.

    0007's reverse already re-creates both rows inert for a rollback that goes
    back past it, which is what the previous release shipped. Re-creating them
    here too would mean rolling back to 0008 restored the second owner; doing
    it faithfully (restoring them ADOPTED, which is what forward found on
    cloud) would restore it in its firing form.
    """
    op = _drop_ops()[0]

    assert op.reverse_code is migrations.RunPython.noop
    assert op.reverse_code is not None, "a None reverse makes the release one-way"


def test_the_drop_targets_exactly_what_the_seeder_created():
    assert DROP.PG_PERIODIC_TASKS is SEEDER.PG_PERIODIC_TASKS


# ---------------------------------------------------------------------------
# Replaying the chain. These are the behavioural tests: everything above pins
# the shape of a file, these pin what a database ends up looking like.
# ---------------------------------------------------------------------------


class _Selection:
    """What a `.filter(...)` returns: just enough queryset to be deleted."""

    def __init__(self, store: "_Rows", names: list[str]):
        self._store = store
        self._names = names

    def delete(self):
        for name in self._names:
            self._store.rows.pop(name, None)
        return len(self._names), {}

    def exists(self) -> bool:
        return bool(self._names)


class _Rows:
    """A dict standing in for one model's table, keyed by `name`."""

    def __init__(self, rows: dict | None = None):
        self.rows: dict[str, dict] = {k: dict(v) for k, v in (rows or {}).items()}

    def update_or_create(self, name=None, defaults=None, **_kwargs):
        self.rows.setdefault(name, {}).update(defaults or {})
        return self.rows[name], True

    def get_or_create(self, name=None, defaults=None, **_kwargs):
        created = name not in self.rows
        if created:
            self.rows[name] = dict(defaults or {})
        return self.rows[name], created

    def filter(self, name=None, name__in=None, **predicates):
        if name__in is not None:
            candidates = list(name__in)
        elif name is not None:
            candidates = [name]
        else:
            candidates = list(self.rows)
        selected = [
            candidate
            for candidate in candidates
            if candidate in self.rows
            and all(
                self.rows[candidate].get(field) == value
                for field, value in predicates.items()
            )
        ]
        return _Selection(self, selected)


class _Apps:
    def __init__(self, seeded: dict | None = None):
        self.pg = _Rows(seeded)
        self.other = _Rows()

    def get_model(self, app_label, model_name):
        is_periodic_task = (app_label, model_name) == ("pg_queue", "PgPeriodicTask")
        target = self.pg if is_periodic_task else self.other
        return type("_M", (), {"objects": target})


#: The five periodics this table is shared with, read from their own migration
#: rather than copied, so a rename there cannot leave this testing names that
#: no longer exist.
_NEIGHBOURS = {
    spec["name"]: {"pg_owned": False, "enabled": True}
    for spec in importlib.import_module(
        "dashboard_metrics.migrations.0004_pg_periodic_tasks"
    ).PG_PERIODIC_TASKS
}


def _agent_kv_migration_modules() -> list[str]:
    directory = pathlib.Path(SEEDER.__file__).parent
    stems = sorted(
        path.stem for path in directory.glob("*.py") if re.match(r"^\d{4}_", path.stem)
    )
    assert stems, "no migrations discovered -- the glob is wrong, not the app"
    return [f"agent_kv.migrations.{stem}" for stem in stems]


def _replay(*, hook_adopts: bool) -> dict[str, dict]:
    """Apply every agent_kv data migration in order; return the surviving rows.

    `hook_adopts` reproduces what the cloud chart does between releases: the
    `backend.pgScheduleMirror` post-upgrade hook runs `converge_pg_scheduler
    --periodics`, whose blanket `--adopt` flips `pg_owned` on EVERY row in
    `pg_periodic_task` (`mirror_pg_periodic_tasks._set_ownership` with an empty
    name list is `PgPeriodicTask.objects.all()`). It is applied after 0004 --
    the window a dev namespace actually sat in, having deployed the seeding
    release before the removals existed.
    """
    apps = _Apps(_NEIGHBOURS)
    for dotted in _agent_kv_migration_modules():
        for op in importlib.import_module(dotted).Migration.operations:
            if isinstance(op, migrations.RunPython):
                op.code(apps, None)
        if hook_adopts and dotted.endswith("0004_pg_periodic_tasks"):
            for row in apps.pg.rows.values():
                row["pg_owned"] = True
    return apps.pg.rows


def test_the_replay_is_not_vacuous():
    """Guards the guard: every assertion below is about rows being ABSENT, so a
    harness that silently applied nothing would make all of them pass.
    """
    apps = _Apps(_NEIGHBOURS)
    seeder_op = [
        op for op in SEEDER.Migration.operations if isinstance(op, migrations.RunPython)
    ][0]
    seeder_op.code(apps, None)

    assert set(apps.pg.rows) == set(_NEIGHBOURS) | {
        "agent_kv_sweep",
        "agent_kv_ttl_cleanup",
    }


def test_a_fresh_install_ends_with_no_agent_kv_periodics():
    """Seed, then delete, then delete again. 0004 is honest and costs two writes."""
    survivors = _replay(hook_adopts=False)

    assert not [name for name in survivors if name.startswith("agent_kv")]


def test_rows_the_mirror_hook_adopted_are_removed_TOO():
    """The regression 0009 exists for.

    A namespace that deployed the seeding release and was then `helm upgrade`d
    had both rows flipped to `pg_owned=True` by the schedule-mirror hook, so
    0007's `pg_owned=False` delete matched neither and the PG scheduler fired
    `agent_kv_sweep` at `*/10` against the CronJob's `*/15`. If this fails,
    an ownership scope has come back and that double-fire is live again.
    """
    survivors = _replay(hook_adopts=True)

    assert not [name for name in survivors if name.startswith("agent_kv")]


@pytest.mark.parametrize("hook_adopts", [False, True])
def test_the_dashboard_metrics_neighbours_are_untouched(hook_adopts):
    """The delete is scoped by NAME, and that scope is the load-bearing one now
    that the ownership scope is gone. `PgPeriodicTask.objects.all().delete()`
    here would take the metrics pipeline down with it.
    """
    survivors = _replay(hook_adopts=hook_adopts)

    assert set(_NEIGHBOURS) <= set(survivors)
