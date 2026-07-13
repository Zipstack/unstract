"""Top-level pytest conftest for the backend service.

Loads environment variables from ``test.env`` before pytest collects any
test modules. This replaces the ``pytest-dotenv`` plugin, which has been
unreleased since Feb 2020 and is a recurring break risk across pytest
majors.

Behavior matches the previous ``env_files = "test.env"`` setting under
``[tool.pytest.ini_options]``: variables already in the process
environment are preserved (``override=False``); a missing file is
silently tolerated.

Note: backend tests do not run under tox in CI today (no ``backend``
testenv); this file only takes effect in local/IDE runs.
"""

from pathlib import Path

from dotenv import load_dotenv

# `-s` is set in pyproject so prints surface — log when test.env is absent
# to make a mis-located file debuggable instead of silently empty.
if not load_dotenv(Path(__file__).parent / "test.env", override=False):
    print("[conftest] backend/test.env not found; using ambient environment", flush=True)


def pytest_collection_modifyitems(items):
    """Auto-mark every DB-bound test as ``integration`` so the rig's unit tier
    (``-m 'not integration'``) skips it while the integration tier (live
    Postgres) runs it. Detects Django ``TestCase``/``TransactionTestCase``
    subclasses and any item using the ``django_db`` marker — the two ways a
    backend test needs a database. Kept central so tests declare their DB need
    by how they're written, not by a hand-maintained marker on each file.
    """
    import pytest
    from django.test import TestCase, TransactionTestCase

    for item in items:
        cls = getattr(item, "cls", None)
        needs_db = item.get_closest_marker("django_db") is not None or (
            cls is not None and issubclass(cls, (TestCase, TransactionTestCase))
        )
        if needs_db:
            item.add_marker(pytest.mark.integration)
