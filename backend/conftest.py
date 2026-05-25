"""Top-level pytest conftest for the backend service.

Loads environment variables from ``test.env`` before pytest collects any
test modules. This replaces the unmaintained ``pytest-dotenv`` plugin
(last release: Feb 2020) which monkey-patched private pytest internals
and was a recurring concern across pytest major upgrades.

Behavior matches the previous ``env_files = "test.env"`` setting in
``[tool.pytest.ini_options]``: variables already set in the process
environment are preserved (``override=False``).
"""

from pathlib import Path

from dotenv import load_dotenv

# Load test.env from this directory (the backend service root). Missing
# file is silently tolerated, matching pytest-dotenv's behavior — tests
# that need specific vars should assert on them in fixtures.
load_dotenv(Path(__file__).parent / "test.env", override=False)
