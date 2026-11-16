"""Shape guards for the two index migrations added by UN-4672.

Both tables take live writes, so each index is built ``CONCURRENTLY`` in a
hand-written, non-atomic migration whose ``AddIndex`` updates model state only. The
suite runs with ``--no-migrations``, so the migration SQL is never executed in CI;
regenerating either migration from ``Meta.indexes`` would land a write-blocking build
with every other test green. The shape tests fail instead.

The guard tests run each migration's ``_ASSERT_INDEX_MATCHES`` block against the index
the test database builds from ``Meta.indexes``: it must pass there and raise on a
mismatched or INVALID index.
"""

from __future__ import annotations

import importlib

from account_v2.models import PlatformKey
from django.db import DatabaseError, connection, migrations, transaction
from django.db.utils import ProgrammingError
from django.test import SimpleTestCase, TestCase
from usage_v2.models import Usage

_CASES = [
    {
        "module": "usage_v2.migrations.0007_usage_org_created_idx",
        "model": Usage,
        "name": "idx_usage_org_created",
        "fields": ["organization", "-created_at"],
        "columns": "(organization_id, created_at DESC)",
        "table": "usage",
        "other_column": "created_at",
    },
    {
        "module": "account_v2.migrations.0012_platform_key_key_idx",
        "model": PlatformKey,
        "name": "platform_key_key_idx",
        "fields": ["key"],
        "columns": "(key)",
        "table": "platform_key",
        "other_column": "key_name",
    },
]


class IndexMigrationShapeTests(SimpleTestCase):
    def _each(self):
        for case in _CASES:
            module = importlib.import_module(case["module"])
            with self.subTest(migration=case["module"]):
                yield case, module

    def test_non_atomic_with_one_state_only_operation(self) -> None:
        for _case, module in self._each():
            migration = module.Migration
            self.assertIs(migration.atomic, False)
            self.assertEqual(len(migration.operations), 1)
            self.assertIsInstance(
                migration.operations[0], migrations.SeparateDatabaseAndState
            )
            for op in migration.operations[0].database_operations:
                self.assertNotIsInstance(op, migrations.AddIndex)

    def test_built_and_dropped_concurrently(self) -> None:
        for case, module in self._each():
            create, guard = module.Migration.operations[0].database_operations
            self.assertIn(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {case['name']}", create.sql
            )
            self.assertIn(case["columns"], create.sql)
            self.assertIn(
                f"DROP INDEX CONCURRENTLY IF EXISTS {case['name']}", create.reverse_sql
            )
            # The guard is what turns an INVALID or mismatched index into an error.
            self.assertIs(guard.sql, module._ASSERT_INDEX_MATCHES)
            self.assertIn("indisvalid", guard.sql)
            self.assertIn(f"USING btree {case['columns']}", guard.sql)

    def test_state_matches_the_model(self) -> None:
        for case, module in self._each():
            add = module.Migration.operations[0].state_operations[0]
            self.assertIsInstance(add, migrations.AddIndex)
            self.assertEqual(add.index.name, case["name"])
            self.assertEqual(list(add.index.fields), case["fields"])
            declared = {i.name: list(i.fields) for i in case["model"]._meta.indexes}
            self.assertEqual(declared.get(case["name"]), case["fields"])


class IndexGuardTests(TestCase):
    """Run each guard block against real indexes, not just its text."""

    def _guard(self, module) -> None:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(module._ASSERT_INDEX_MATCHES)

    def _each(self):
        for case in _CASES:
            module = importlib.import_module(case["module"])
            with self.subTest(migration=case["module"]):
                yield case, module

    def test_passes_on_the_index_the_model_declares(self) -> None:
        for _case, module in self._each():
            self._guard(module)

    def test_raises_on_an_index_with_another_definition(self) -> None:
        for case, module in self._each():
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP INDEX "{case["name"]}"')
                    cursor.execute(
                        f'CREATE INDEX "{case["name"]}" '
                        f'ON "{case["table"]}" ({case["other_column"]})'
                    )
                with self.assertRaisesRegex(DatabaseError, "unexpected definition"):
                    self._guard(module)
                transaction.set_rollback(True)

    def test_raises_on_a_missing_index(self) -> None:
        for case, module in self._each():
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP INDEX "{case["name"]}"')
                with self.assertRaisesRegex(DatabaseError, "is missing"):
                    self._guard(module)
                transaction.set_rollback(True)

    def test_raises_on_an_invalid_index(self) -> None:
        # What an interrupted CREATE INDEX CONCURRENTLY leaves behind. Marking it
        # INVALID by hand needs write access to pg_index (a superuser).
        for case, module in self._each():
            with transaction.atomic():
                try:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE pg_index SET indisvalid = false "
                            "WHERE indexrelid = %s::regclass",
                            [case["name"]],
                        )
                except ProgrammingError:
                    self.skipTest("needs a superuser to mark an index INVALID")
                with self.assertRaisesRegex(DatabaseError, "INVALID"):
                    self._guard(module)
                transaction.set_rollback(True)
