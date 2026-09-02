"""Shape guard for the ``(status, created_at)`` index migration (UN-3972).

``workflow_file_execution`` is ~3.4 GB in production and takes live inserts. A plain
``AddIndex`` — which is what ``makemigrations`` emits from ``Meta.indexes`` — holds a
``SHARE`` lock for the whole build and stalls file processing. ``0007`` is therefore
hand-written: non-atomic, ``CONCURRENTLY``, and split so the ``AddIndex`` updates model
state only.

Nothing else guards that. The suite runs with ``--no-migrations``, so this migration is
never executed in CI; regenerating or "tidying" it would land the locking version with
every test still green. These assertions are what fails instead.

DB-free by design: the migration module is imported and inspected directly.
"""

from __future__ import annotations

import importlib

from django.db import migrations
from django.test import SimpleTestCase

from workflow_manager.file_execution.models import WorkflowFileExecution

_MIGRATION = "workflow_manager.file_execution.migrations.0007_wfe_status_created_idx"

INDEX_NAME = "wfe_status_created_idx"
INDEX_FIELDS = ["status", "created_at"]
TABLE = "workflow_file_execution"


class MigrationShapeTests(SimpleTestCase):
    """The properties that keep the build off the write path."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.migration = importlib.import_module(_MIGRATION).Migration
        cls.operation = cls.migration.operations[0]

    def test_the_migration_has_exactly_one_operation(self) -> None:
        """Every other assertion reads operations[0], so anything appended after the
        SeparateDatabaseAndState is invisible — including a bare AddIndex, which is a
        real lock-taking build on a 3.4 GB table.
        """
        self.assertEqual(len(self.migration.operations), 1)

    def test_no_operation_builds_an_index_against_the_database(self) -> None:
        """The same failure stated directly, so it survives the count changing."""
        for op in self.migration.operations:
            self.assertNotIsInstance(op, migrations.AddIndex)

    def test_migration_is_non_atomic(self) -> None:
        """CREATE/DROP INDEX CONCURRENTLY is rejected inside a transaction block."""
        self.assertIs(self.migration.atomic, False)

    def test_index_is_built_and_dropped_concurrently(self) -> None:
        """Both directions must stay off the write-blocking lock path."""
        create = self.operation.database_operations[0]
        self.assertIn("CREATE INDEX CONCURRENTLY IF NOT EXISTS", create.sql)
        self.assertIn(INDEX_NAME, create.sql)
        # Column order is the point — (created_at, status) cannot serve an equality
        # plus range filter. Whitespace and case are not, and a red test on
        # semantically identical SQL only teaches people to loosen the assertion.
        self.assertRegex(
            create.sql,
            rf"ON\s+{TABLE}\s*\(\s*{INDEX_FIELDS[0]}\s*,\s*{INDEX_FIELDS[1]}\s*\)",
        )
        self.assertIn("DROP INDEX CONCURRENTLY IF EXISTS", create.reverse_sql)
        # A typo here makes rollback a silent no-op through IF EXISTS: Django unapplies
        # the migration while the index stays on the table.
        self.assertIn(INDEX_NAME, create.reverse_sql)

    def test_every_database_operation_is_reversible(self) -> None:
        """One irreversible operation kills the whole rollback, DROP INDEX included."""
        self.assertTrue(
            all(op.reversible for op in self.operation.database_operations)
        )

    def test_pre_existing_index_guard_is_present(self) -> None:
        """``IF NOT EXISTS`` matches on name alone, so the guard carries the rest.

        An interrupted concurrent build leaves an INVALID index, and a hand-built one
        may have different columns; either would be kept while Django recorded the
        migration as applied. The guard turns both into a loud failure, and looks the
        index up in ``current_schema()`` because app tables do not live in ``public``.
        """
        guard = self.operation.database_operations[1].sql
        # Polarity, not presence: `NOT idx_valid` raises on a broken index, `idx_valid`
        # raises on every healthy deploy, and both contain "indisvalid".
        self.assertIn("i.indisvalid", guard)
        self.assertIn("IF NOT idx_valid THEN", guard)
        # Scoped to this index, in this schema.
        self.assertIn(f"c.relname = '{INDEX_NAME}'", guard)
        self.assertIn("n.nspname = current_schema()", guard)
        # Definition, not just validity.
        self.assertIn("pg_get_indexdef", guard)
        self.assertIn(f"USING btree ({', '.join(INDEX_FIELDS)})", guard)
        self.assertIn("NOT LIKE", guard)
        self.assertIn("RAISE EXCEPTION", guard)
        self.assertIn(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}", guard)

    def test_add_index_updates_state_only(self) -> None:
        """``AddIndex`` must not reach the database, or it builds a second time."""
        self.assertIsInstance(self.operation, migrations.SeparateDatabaseAndState)
        self.assertTrue(
            all(
                isinstance(op, migrations.RunSQL)
                for op in self.operation.database_operations
            )
        )
        self.assertEqual(len(self.operation.state_operations), 1)
        state_op = self.operation.state_operations[0]
        self.assertIsInstance(state_op, migrations.AddIndex)
        self.assertEqual(state_op.index.name, INDEX_NAME)
        self.assertEqual(state_op.index.fields, INDEX_FIELDS)

    def test_model_meta_matches_the_migration(self) -> None:
        """Model state and migration state drift silently otherwise."""
        declared = {idx.name: idx.fields for idx in WorkflowFileExecution._meta.indexes}
        self.assertEqual(declared.get(INDEX_NAME), INDEX_FIELDS)
