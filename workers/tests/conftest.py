"""Shared fixtures for workers tests.

Environment variables are loaded from .env.test at module level
BEFORE any shared package imports.  This is required because
shared/constants/api_endpoints.py raises ValueError at import
time if INTERNAL_API_BASE_URL is not set.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

_env_test = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(_env_test)

# Worker Celery apps build a Postgres result backend from DB_*/CELERY_BACKEND_DB_*.
# Strip these before any app is imported so tests don't reach (or leak) a live DB
# the unit tier has no server for; eager results then stay in-memory.
for _var in (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "CELERY_BACKEND_DB_HOST",
    "CELERY_BACKEND_DB_PORT",
    "CELERY_BACKEND_DB_NAME",
    "CELERY_BACKEND_DB_USER",
    "CELERY_BACKEND_DB_PASSWORD",
):
    os.environ.pop(_var, None)


@pytest.fixture(autouse=True)
def _restore_current_celery_app():
    """Pin celery's default app as current_app around each test. Worker modules
    build their own apps at import and set them current, so `@worker_task` proxies
    otherwise fail to resolve (`NotRegistered`) against a drifted current_app.
    Finalize so every shared task is registered on it.
    """
    from celery._state import default_app

    default_app.finalize()
    default_app.set_current()
    try:
        yield
    finally:
        default_app.set_current()
