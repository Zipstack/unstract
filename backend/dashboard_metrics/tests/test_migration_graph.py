"""Guard: the migration graph builds (UN-3974).

Django builds the **entire** graph before executing anything, so one migration
depending on a node that does not exist aborts `migrate`, `makemigrations` and
`showmigrations` for every app in the project — the deploy's migrate step fails, not
just this app's.

Nothing else catches it. The backend suite runs with `--no-migrations`, so test-DB
creation never builds the graph, and every migration test in this app reaches its
module through `importlib.import_module`, which resolves a file path rather than a
graph node. GitHub also reports a stacked branch as mergeable, because a missing
dependency is not a textual conflict.

DB-free: building the graph reads the migration files, not the database.
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django.test import SimpleTestCase, override_settings  # noqa: E402


def _build_graph() -> MigrationLoader:
    """Build the real graph, whatever the suite's own flags say.

    `--no-migrations` works by pointing MIGRATION_MODULES at a mapping that returns
    None for every app, so a loader built under it finds nothing and every assertion
    below would pass against an empty graph. Restoring the setting is what makes this
    guard mean anything in the tier it runs in.
    """
    with override_settings(MIGRATION_MODULES={}):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        loader.build_graph()
    return loader


class MigrationGraphTests(SimpleTestCase):
    def test_the_graph_builds(self) -> None:
        """A dependency on an absent migration raises NodeNotFoundError here."""
        loader = _build_graph()
        self.assertTrue(loader.graph.nodes, "no migrations loaded — the guard is inert")

    def test_every_app_has_exactly_one_leaf(self) -> None:
        """Two leaves in one app block `migrate` for every app, not just that one.

        This is what a merge of two branches that each added a migration produces, and
        it is invisible until deploy for the same `--no-migrations` reason.
        """
        loader = _build_graph()

        leaves: dict[str, list[str]] = {}
        for app_label, name in loader.graph.leaf_nodes():
            leaves.setdefault(app_label, []).append(name)

        conflicts = {app: names for app, names in leaves.items() if len(names) > 1}
        self.assertEqual(conflicts, {}, f"apps with multiple leaf migrations: {conflicts}")
