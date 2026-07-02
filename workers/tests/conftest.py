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

# Pristine baseline: the environment right after .env.test loads, captured before
# pytest collection imports any worker module. Some worker modules call
# ``load_dotenv(<workers>/.env)`` at import time, so on a developer machine the
# ambient dev ``.env`` (e.g. WORKER_BARRIER_KEY_TTL_SECONDS=180) bleeds into the
# process during collection and silently overrides test defaults — green in CI
# (no ``.env``), red locally. ``_restore_os_environ`` resets to this baseline
# around every test so the suite is deterministic regardless of ambient ``.env``.
_PRISTINE_ENVIRON = dict(os.environ)


# --- Collection: separate real-Postgres tests from the unit lane ---


def pytest_collection_modifyitems(config, items):
    """Auto-mark real-Postgres tests as ``integration``.

    Any test that requests a real-Postgres fixture needs a live database.
    Marking those ``integration`` here — rather than by hand on each of ~100 tests
    scattered across mixed unit/integration files — lets the fast lane run
    ``-m "not integration"`` (DB-free, deterministic) while a dedicated
    integration lane runs ``-m integration`` against a provisioned Postgres.

    The set lists every fixture that opens a real connection directly; fixtures
    layered on top of these (e.g. ``pg_client``/``result_backend`` build on
    ``pg_conn``) are covered transitively because ``fixturenames`` includes the
    whole dependency graph.
    """
    pg_fixtures = {
        "pg_conn",
        "pg_client",
        "barrier_db",
        "dedup_db",
        "lock_db",
        "barrier_conn",
    }
    for item in items:
        if pg_fixtures & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.integration)


# --- Isolation: keep the suite deterministic in a single process ---


@pytest.fixture(autouse=True)
def _restore_os_environ():
    """Reset ``os.environ`` to the ``.env.test`` baseline around every test.

    Two leaks are neutralised: (1) a test that mutates the environment (a bare
    ``os.environ[...] =`` rather than ``monkeypatch.setenv``) leaking into later
    tests, and (2) the ambient dev ``.env`` pulled in during collection (see
    ``_PRISTINE_ENVIRON``) silently overriding test defaults. Resetting to the
    pristine baseline both before and after each test makes every test start from
    the same environment regardless of run order or the developer's ``.env``.
    Defined first so it wraps every other autouse fixture.
    """

    def _reset_to_pristine():
        # Preserve pytest's own bookkeeping (e.g. PYTEST_CURRENT_TEST, which
        # pytest sets per-test and deletes itself at teardown) — clearing it
        # would make pytest's teardown KeyError.
        preserved = {k: v for k, v in os.environ.items() if k.startswith("PYTEST")}
        os.environ.clear()
        os.environ.update(_PRISTINE_ENVIRON)
        os.environ.update(preserved)

    _reset_to_pristine()
    try:
        yield
    finally:
        _reset_to_pristine()


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


def _skip_or_fail_no_pg(reason: str):
    """Skip the test, or fail loudly when ``REQUIRE_PG_TESTS`` is set.

    The unit lane skips real-Postgres tests when no DB is around. The dedicated
    integration lane sets ``REQUIRE_PG_TESTS=1`` so a missing/misconfigured
    Postgres is a hard failure instead of a green-but-silent skip — otherwise the
    integration lane could pass having run nothing.
    """
    if os.getenv("REQUIRE_PG_TESTS"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def pg_conn():
    """A real connection; skips if Postgres is unreachable or unmigrated.

    Fails instead of skipping when ``REQUIRE_PG_TESTS`` is set (integration lane).
    """
    try:
        conn = integration_pg_conn()
    except psycopg2.OperationalError as exc:
        _skip_or_fail_no_pg(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_queue_message')")
        if cur.fetchone()[0] is None:
            conn.close()
            _skip_or_fail_no_pg("pg_queue migration not applied (run backend migrate)")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def pg_client(pg_conn):
    """A :class:`PgQueueClient` over the integration connection."""
    from queue_backend.pg_queue import PgQueueClient

    return PgQueueClient(conn=pg_conn)


# --- Test-isolation fixtures (deterministic single-process runs) ---
#
# The workers suite carries several process-global registries/singletons that
# leak state across tests when the whole suite runs in one process (green in
# isolation, order-dependent failures / hangs together). The fixtures below
# snapshot-and-restore them so the suite is deterministic regardless of order.


@pytest.fixture
def isolated_celery_registry():
    """Give the test a genuinely empty Celery task registry.

    A truly empty ``Celery(...)`` app is impossible once any ``@shared_task``
    has been imported: Celery keeps a *process-global* finalizer backlog
    (``celery._state._on_app_finalizers``) and injects every declared shared
    task into every *new* app on finalize. So ``Celery("empty")`` created in a
    full-suite run actually carries the worker's shared tasks — which silently
    defeats the consumer's empty-registry guard (the guard passes, ``run()``
    enters its poll loop, and the test hangs).

    This fixture snapshots and clears that backlog for the test's duration, so a
    ``Celery(...)`` created inside the test starts with only ``celery.*``
    built-ins, then restores it so the backlog isn't mutated for other tests.
    """
    import celery._state as celery_state

    saved = set(celery_state._on_app_finalizers)
    celery_state._on_app_finalizers.clear()
    try:
        yield
    finally:
        celery_state._on_app_finalizers.clear()
        celery_state._on_app_finalizers.update(saved)


@pytest.fixture(autouse=True)
def _reset_queue_backend_state():
    """Reset process-global queue_backend state after every test.

    ``queue_backend`` caches a PG dispatch client and a barrier connection in
    thread-locals, and trips one-shot "log this once" flags (routing allow-list,
    per-task PG-routing notice). These are lazily populated on first use, so a
    test that seeds a fake client or trips a log-once flag would otherwise change
    what every later test in the same process observes — making the suite
    order-dependent (green alone, failing in a full run). Reset on teardown so
    each test starts from the same clean module state regardless of order.

    Each reset is guarded independently: a module that fails to import (missing
    optional dep in a given lane) must not break the autouse fixture for the
    whole suite.
    """
    yield
    try:
        import queue_backend.routing as _routing

        _routing._allow_list_logged = False
    except Exception:
        pass
    try:
        import queue_backend.dispatch as _dispatch

        _dispatch._pg_routing_logged.clear()
        if hasattr(_dispatch._pg_local, "client"):
            del _dispatch._pg_local.client
    except Exception:
        pass
    try:
        import queue_backend.pg_barrier as _pg_barrier

        if hasattr(_pg_barrier._local, "conn"):
            del _pg_barrier._local.conn
    except Exception:
        pass
