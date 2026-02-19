"""Shared fixtures for workers tests.

Environment variables are loaded from .env.test at module level
BEFORE any shared package imports.  This is required because
shared/constants/api_endpoints.py raises ValueError at import
time if INTERNAL_API_BASE_URL is not set.
"""

from pathlib import Path

from dotenv import load_dotenv

_env_test = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(_env_test)
