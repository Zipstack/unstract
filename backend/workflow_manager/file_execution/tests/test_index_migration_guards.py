"""Both index migrations' ``DO $$`` guard blocks, executed by a real server.

The suite runs under ``--no-migrations``, so neither migration is ever applied and
no Postgres ever parses these blocks. Their assertions are otherwise checked only
as Python substrings, which cannot tell valid PL/pgSQL from invalid: breaking
``BEGIN`` to ``BEGINN`` in both migrations leaves the whole suite green while
``migrate`` would fail outright on the deploy this guard exists to protect.

Both migrations are covered here rather than in their own apps because the guard
is one shape written twice, and a divergence between the two copies is exactly
what a single exerciser catches.

Each block is run twice: once against the index it expects, and once against an
index of the same name with a different definition — the ``(created_at DESC)``
slip its own comment calls out. A guard that never fires is not a guard.

DB-bound, so conftest marks it integration.
"""

from __future__ import annotations

import os

import django
from django.apps import apps as django_apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not django_apps.ready:
    django.setup()

from importlib import import_module  # noqa: E402

from django.db import connection  # noqa: E402
from django.db.utils import InternalError  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402

_MIGRATIONS = {
    "wfe_status_created_idx": (
        "workflow_manager.file_execution.migrations.0007_wfe_status_created_idx",
        "workflow_file_execution",
        "(status, created_at)",
    ),
    "we_created_at_idx": (
        "workflow_manager.workflow_v2.migrations.0029_we_created_at_idx",
        "workflow_execution",
        "(created_at)",
    ),
}


class TestTheIndexGuardsAreRunnableSql(TransactionTestCase):
    """The guard blocks parse and behave, against a live server."""

    def _module(self, index_name):
        return import_module(_MIGRATIONS[index_name][0])

    def _run_guard(self, index_name):
        with connection.cursor() as cur:
            cur.execute(self._module(index_name)._ASSERT_INDEX_MATCHES)

    def _replace_with_a_wrong_index(self, index_name):
        """Same name, descending — the slip the migration's own comment names."""
        _, table, columns = _MIGRATIONS[index_name]
        descending = columns.replace(")", " DESC)").replace(", ", " DESC, ")
        with connection.cursor() as cur:
            cur.execute(f"DROP INDEX IF EXISTS {index_name}")
            cur.execute(f"CREATE INDEX {index_name} ON {table} {descending}")

    def test_the_guards_pass_against_the_index_they_expect(self):
        """Also the parse check: invalid PL/pgSQL cannot reach a passing result."""
        for index_name in _MIGRATIONS:
            with self.subTest(index=index_name):
                self._run_guard(index_name)

    def test_each_guard_rejects_an_index_of_the_same_name_built_descending(self):
        """IF NOT EXISTS matches on name alone, which is why this case exists."""
        for index_name, (_, table, columns) in _MIGRATIONS.items():
            with self.subTest(index=index_name):
                self._replace_with_a_wrong_index(index_name)
                try:
                    with self.assertRaises(InternalError) as caught:
                        self._run_guard(index_name)
                    assert "unexpected definition" in str(caught.exception), (
                        f"{index_name}: the guard raised, but not for the reason it "
                        f"claims to:\n{caught.exception}"
                    )
                finally:
                    with connection.cursor() as cur:
                        cur.execute(f"DROP INDEX IF EXISTS {index_name}")
                        cur.execute(
                            f"CREATE INDEX {index_name} ON {table} {columns}"
                        )

    def test_each_guard_rejects_a_missing_index(self):
        for index_name, (_, table, columns) in _MIGRATIONS.items():
            with self.subTest(index=index_name):
                with connection.cursor() as cur:
                    cur.execute(f"DROP INDEX IF EXISTS {index_name}")
                try:
                    with self.assertRaises(InternalError) as caught:
                        self._run_guard(index_name)
                    assert "is missing from schema" in str(caught.exception)
                finally:
                    with connection.cursor() as cur:
                        cur.execute(
                            f"CREATE INDEX IF NOT EXISTS {index_name} "
                            f"ON {table} {columns}"
                        )
