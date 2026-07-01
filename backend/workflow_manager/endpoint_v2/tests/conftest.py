import os

import pytest

_HERE = os.path.dirname(__file__)


def pytest_collection_modifyitems(items):
    # These tests use django.test.TestCase — a live Postgres is required, so the
    # whole subtree belongs to the integration tier, not unit. Scope to this
    # dir: the hook receives the full session's items, not just local ones.
    for item in items:
        if str(item.path).startswith(_HERE):
            item.add_marker(pytest.mark.integration)
