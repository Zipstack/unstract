"""Guard: the undispatched-execution partial index stays in sync with reality.

``we_undispatched_dispatch_idx`` (``WorkflowExecution.Meta.indexes``) hardcodes the literal
``'PENDING'`` and the two dispatch-handle columns. The same predicate is written a
second time in migration 0026's ``RunSQL``, and a third time as the sweep's WHERE clause
in ``undispatched_sweep.py`` — migrations cannot import app enums, so the literal cannot
simply reference ``ExecutionStatus``.

Three copies of one predicate is exactly how an index silently stops matching the query
it exists for: the sweep keeps working, just without the index, and nobody notices until
it is scanning a multi-million-row table every 5 minutes. These assert the copies agree.

Model introspection only — no test database required, so this runs in the unit tier
alongside ``test_active_execution_index.py``, which does the same job for 0023.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from unstract.core.data_models import ExecutionStatus  # noqa: E402

INDEX_NAME = "we_undispatched_dispatch_idx"
_MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "0026_workflowexecution_undispatched_idx.py"
)


def _index():
    model = apps.get_model("workflow_v2", "WorkflowExecution")
    return next((i for i in model._meta.indexes if i.name == INDEX_NAME), None)


def _condition_children() -> dict:
    index = _index()
    assert index is not None, f"{INDEX_NAME} is missing from WorkflowExecution.Meta"
    return {c[0]: c[1] for c in index.condition.children if isinstance(c, tuple)}


class TestTheModelIndexMatchesTheEnum:
    def test_the_status_literal_is_the_pending_enum_value(self):
        """If ExecutionStatus.PENDING's *value* ever changes, the index silently stops
        matching every row the sweep looks for."""
        assert _condition_children()["status"] == ExecutionStatus.PENDING.value

    def test_all_three_dispatch_signals_are_in_the_predicate(self):
        """Dropping any makes the index non-matching for the sweep's WHERE clause
        (Postgres needs the query predicate to imply the index predicate), so the sweep
        would quietly fall back to scanning.

        Three, not two: `dispatched_at` is the authoritative test (0027), and the two
        handle checks are retained so the rollout is single-phase — a row dispatched by
        an old pod mid-deploy has no stamp but does have a handle, and must not be swept.
        """
        children = _condition_children()
        assert children.get("dispatched_at__isnull") is True
        assert children.get("task_id__isnull") is True
        assert children.get("queue_message_id__isnull") is True

    def test_it_is_keyed_on_created_at(self):
        """The sweep's only range predicate and its ORDER BY for the batch limit."""
        assert _index().fields == ["created_at"]


class TestTheMigrationMatchesTheModel:
    """The migration's raw SQL is the copy that actually builds the index; the model's
    Index() is only Django state. They must not disagree.
    """

    def test_the_migration_sql_uses_the_same_status_literal(self):
        sql = _MIGRATION.read_text()
        assert f"status = '{ExecutionStatus.PENDING.value}'" in sql

    def test_the_migration_sql_carries_both_handle_conditions(self):
        sql = _MIGRATION.read_text()
        assert "task_id IS NULL" in sql
        assert "queue_message_id IS NULL" in sql

    def test_the_migration_builds_concurrently_and_is_non_atomic(self):
        """workflow_execution is multi-million-row in production — a plain AddIndex
        holds a SHARE lock for the whole build and blocks every in-flight execution.
        """
        sql = _MIGRATION.read_text()
        assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in sql
        assert re.search(r"^\s*atomic\s*=\s*False", sql, re.MULTILINE)

    def test_it_guards_against_a_leftover_invalid_index(self):
        """IF NOT EXISTS no-ops over an INVALID index from an interrupted build, and
        Django would record the migration as applied over something unusable.
        """
        sql = _MIGRATION.read_text()
        assert "RAISE EXCEPTION" in sql
        assert "indisvalid" in sql


class TestTheSweepQueryMatchesTheIndex:
    def test_the_sweep_predicate_uses_the_same_columns(self):
        """The third copy. If the sweep's SQL drifts from the index predicate, Postgres
        can no longer prove the implication and the partial index becomes unusable —
        the sweep still returns correct rows, just by scanning.
        """
        from workflow_manager.workflow_v2 import undispatched_sweep

        sql = undispatched_sweep._CLAIM_SQL
        assert "task_id IS NULL" in sql
        assert "queue_message_id IS NULL" in sql
        assert "created_at <" in sql
        assert "ORDER BY created_at" in sql

    def test_the_predicate_appears_TWICE__inner_select_and_outer_recheck(self):
        """The race guard, and the one thing a substring check silently misses.

        The inner SELECT picks and locks candidates; the OUTER WHERE re-carries the same
        predicate so Postgres re-evaluates it at write time under those locks. Drop it
        from the outer clause and the statement still looks right — the strings are all
        still present, courtesy of the inner SELECT — but a row dispatched between the
        two is now marked ERROR *while it runs*.

        Verified: removing the outer re-check passed every other test in this file.
        """
        from workflow_manager.workflow_v2 import undispatched_sweep

        sql = undispatched_sweep._CLAIM_SQL
        for clause in ("task_id IS NULL", "queue_message_id IS NULL"):
            assert sql.count(clause) >= 2, (
                f"{clause!r} appears {sql.count(clause)}x — it must be in BOTH the "
                "inner SELECT and the outer re-check, or the claim is racy"
            )
        # The status check likewise: %s placeholders, so count the column instead.
        assert sql.count("status = %s") >= 2, "status must be re-checked in the UPDATE"

    def test_it_locks_candidates_with_skip_locked(self):
        """Without FOR UPDATE the outer re-check reads unlocked rows and the race
        reopens; without SKIP LOCKED an overlapping sweeper blocks instead of yielding.
        """
        from workflow_manager.workflow_v2 import undispatched_sweep

        assert "FOR UPDATE SKIP LOCKED" in undispatched_sweep._CLAIM_SQL
