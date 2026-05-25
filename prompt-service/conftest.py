"""Top-level pytest conftest for the prompt-service.

Loads environment variables from ``.env`` before pytest collects any
test modules. This replaces the unmaintained ``pytest-dotenv`` plugin
(last release: Feb 2020) which monkey-patched private pytest internals
and was a recurring concern across pytest major upgrades.

The prompt-service pyproject did not configure ``env_files``, so the
plugin's default was to load ``.env`` from the rootdir; this preserves
that exact behavior. Variables already set in the process environment
are preserved (``override=False``).
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=False)
