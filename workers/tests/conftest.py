"""Shared fixtures for workers tests.

Environment variables are loaded from .env.test at module level
BEFORE any shared package imports.  This is required because
shared/constants/api_endpoints.py raises ValueError at import
time if INTERNAL_API_BASE_URL is not set.
"""

import os
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

_env_test = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(_env_test)


# --- Shared PG-queue integration fixtures (real Postgres) ---
#
# Connect to the dev DB via TEST_DB_* — NOT the generic DB_*, which the
# suite's unit isolation sets to DB_USER=test. Skip gracefully when Postgres
# is unreachable or the pg_queue migration hasn't been applied, so CI without
# a migrated DB doesn't fail (only the real-DB seam is gated).


def integration_pg_conn():
    """Raw psycopg2 connection to the dev DB (host defaults to localhost)."""
    from queue_backend.pg_queue.connection import create_pg_connection

    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    return create_pg_connection(env_prefix="TEST_DB_")


@pytest.fixture
def pg_conn():
    """A real connection; skips if Postgres is unreachable or unmigrated."""
    try:
        conn = integration_pg_conn()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_queue_message')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_queue migration not applied (run backend migrate)")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def pg_client(pg_conn):
    """A :class:`PgQueueClient` over the integration connection."""
    from queue_backend.pg_queue import PgQueueClient

    return PgQueueClient(conn=pg_conn)
