"""Pytest configuration for unit tests.

Unit tests should not require external dependencies or the full app.
This conftest intentionally does NOT import Flask app components.

WARNING: This file is NOT auto-loaded when running via tox because
--noconftest is used to skip the parent tests/conftest.py (which
imports Flask blueprints and triggers the full adapter import chain).
If you add shared fixtures here, either remove --noconftest from
tox.ini and fix the parent conftest's eager imports, or define
fixtures directly in test files.
"""
