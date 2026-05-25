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
