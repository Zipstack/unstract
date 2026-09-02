"""Guard: ``we_created_at_idx`` keeps the shape that makes it safe to deploy.

The backend suite runs with ``--no-migrations``, so migration 0029 never executes in
CI. Regenerating it with ``makemigrations``, or dropping ``atomic = False`` while
tidying, lands a plain ``AddIndex`` — which holds a SHARE lock for the whole build and
blocks every in-flight execution on a multi-million-row table — with every other test
still green. These assert the properties that keep that from happening.

Model and migration introspection only, no test database, so this runs in the unit tier
alongside ``test_active_execution_index.py`` and ``test_undispatched_execution_index.py``.
"""

from __future__ import annotations

import importlib
import os
import re
from pathlib import Path
from typing import Any, cast

import django
from django.apps import apps
from django.db import migrations, models

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

INDEX_NAME = "we_created_at_idx"
_MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent / "migrations" / "0029_we_created_at_idx.py"
)
_MIGRATION_MODULE = "workflow_manager.workflow_v2.migrations.0029_we_created_at_idx"


def _model_index() -> models.Index | None:
    model = apps.get_model("workflow_v2", "WorkflowExecution")
    return next((i for i in model._meta.indexes if i.name == INDEX_NAME), None)


def _operations() -> list[Any]:
    return cast(
        list[Any], importlib.import_module(_MIGRATION_MODULE).Migration.operations
    )


class TestTheModelDeclaresIt:
    def test_it_is_keyed_on_created_at_alone(self) -> None:
        """A bare created_at range with no leading column value is the whole point —
        the composite indexes lead with workflow_id / pipeline_id and are date-ordered
        only within one workflow or pipeline.
        """
        index = _model_index()
        assert index is not None, f"{INDEX_NAME} is missing from WorkflowExecution.Meta"
        assert index.fields == ["created_at"]

    def test_it_carries_no_condition(self) -> None:
        """A partial index would not serve the prefilter, which bounds nothing but the
        date. we_undispatched_dispatch_idx is the partial one and is a different index.
        """
        assert getattr(_model_index(), "condition", None) is None


class TestTheMigrationIsSafeToDeploy:
    def test_it_is_non_atomic(self) -> None:
        """CREATE/DROP INDEX CONCURRENTLY cannot run inside a transaction block, so
        without this the migration cannot run at all.
        """
        assert re.search(
            r"^\s*atomic\s*=\s*False", _MIGRATION_FILE.read_text(), re.MULTILINE
        )

    def test_it_builds_and_drops_concurrently(self) -> None:
        """Both directions: a plain DROP INDEX takes an ACCESS EXCLUSIVE lock, so a
        rollback would block writes just as a plain build would.
        """
        sql = _MIGRATION_FILE.read_text()
        assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in sql
        assert "DROP INDEX CONCURRENTLY IF EXISTS" in sql

    def test_the_statement_that_runs_names_the_model_table_and_column(self) -> None:
        """Everything else here reads the ``AddIndex`` state operation, which by
        construction never reaches the database, or greps the source for
        ``CONCURRENTLY``. The ``RunSQL`` is the only statement production executes and
        its table and column were cross-checked against nothing — so the index could be
        built on the wrong column while Django's model state claimed otherwise.
        """
        index = _model_index()
        assert index is not None
        model = apps.get_model("workflow_v2", "WorkflowExecution")
        expected = f"{model._meta.db_table} ({', '.join(index.fields)})"

        create = _operations()[0].database_operations[0]
        assert expected in create.sql, f"expected {expected!r} in {create.sql!r}"

    def test_it_guards_against_a_leftover_invalid_index(self) -> None:
        """An interrupted CONCURRENTLY build leaves an INVALID index that costs on every
        write and is never read. IF NOT EXISTS would keep it while Django recorded the
        migration as applied — green, and permanently slower.
        """
        sql = _MIGRATION_FILE.read_text()
        assert "RAISE EXCEPTION" in sql
        assert "indisvalid" in sql

    def test_add_index_is_state_only(self) -> None:
        """The failure mode this whole file exists for. AddIndex outside
        state_operations is a real lock-taking build; inside, it only keeps Django's
        model state in step so makemigrations does not re-add the index.
        """
        ops = _operations()
        assert len(ops) == 1
        wrapper = ops[0]
        assert isinstance(wrapper, migrations.SeparateDatabaseAndState)
        assert all(
            isinstance(op, migrations.RunSQL) for op in wrapper.database_operations
        )
        assert [type(op) for op in wrapper.state_operations] == [migrations.AddIndex]

    def test_the_migration_and_the_model_agree(self) -> None:
        """Two declarations of one index; they must not drift."""
        index = _model_index()
        assert index is not None
        add_index = _operations()[0].state_operations[0]
        assert add_index.index.name == INDEX_NAME
        assert add_index.index.fields == index.fields
