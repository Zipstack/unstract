"""Shape guards for the two index migrations added by UN-4672.

``usage`` (3.2 GB on prod) takes constant writes, and ``platform_key`` follows the same
pattern so both are safe to build at deploy time; each index is built ``CONCURRENTLY`` in a hand-written, non-atomic migration whose ``AddIndex``
updates model state only. The suite runs with ``--no-migrations``, so the SQL is never
executed in CI; regenerating either migration from ``Meta.indexes`` would land a
write-blocking build with every other test green. These assertions fail instead.

DB-free: the migration modules are imported and inspected directly.
"""

from __future__ import annotations

import importlib

from account_v2.models import PlatformKey
from django.db import migrations
from django.test import SimpleTestCase
from usage_v2.models import Usage

_CASES = [
    {
        "module": "usage_v2.migrations.0007_usage_org_created_idx",
        "model": Usage,
        "name": "idx_usage_org_created",
        "fields": ["organization", "-created_at"],
        "columns": "(organization_id, created_at DESC)",
    },
    {
        "module": "account_v2.migrations.0012_platform_key_key_idx",
        "model": PlatformKey,
        "name": "platform_key_key_idx",
        "fields": ["key"],
        "columns": "(key)",
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
