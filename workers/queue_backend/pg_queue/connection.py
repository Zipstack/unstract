"""Direct Postgres connection for the PG-queue client.

The PG queue is the first worker component to open a *direct* Postgres
connection — workers otherwise reach state via the Internal API, with
Redis the only other direct store. It reuses the **backend's** ``DB_*``
env so the target follows the deployment: in cloud those vars point at
PgBouncer (connection pooling); in OSS / on-prem they point straight at
Postgres (UN-3533 decision).

``search_path`` is set to ``DB_SCHEMA`` so the bespoke
``pg_queue_message`` table resolves in the same schema the backend
manages.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# Bounded retry for *transient* connect failures (DB restart, PgBouncer pool
# wait, brief network partition, "too many clients" spikes) — the common cloud
# blips. Opening a connection is side-effect-free, so retrying it is safe and
# purely additive. Note we deliberately do NOT auto-retry the enqueue INSERT
# (queue_backend.pg_queue.client.send): an ambiguous commit-time failure could
# double-enqueue → double-dispatch, so that path stays fail-and-surface.
_DEFAULT_CONNECT_RETRIES = 3  # total attempts (1 = no retry)
_DEFAULT_CONNECT_BACKOFF = 0.5  # base seconds between attempts; doubles each retry
_CONNECT_BACKOFF_CAP = 5.0  # ceiling on a single inter-attempt sleep


def _connect_env[T](suffix: str, default: T, cast: Callable[[str], T]) -> T:
    """Read ``WORKER_PG_QUEUE_CONNECT_{suffix}``; fall back to ``default``.

    Empty/unset → default; an unparseable value warns and uses the default
    (a bad knob must not wedge the only direct-DB worker path).
    """
    raw = os.getenv(f"WORKER_PG_QUEUE_CONNECT_{suffix}")
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logger.warning(
            "PG-queue: invalid WORKER_PG_QUEUE_CONNECT_%s=%r; using default %r",
            suffix,
            raw,
            default,
        )
        return default


def create_pg_connection(env_prefix: str = "DB_") -> PgConnection:
    """Open a direct Postgres connection from ``{env_prefix}*`` env.

    The default ``DB_`` prefix reads the same variable *names* the backend
    uses (``DB_HOST`` / ``DB_PORT`` / ``DB_NAME`` / ``DB_USER`` /
    ``DB_PASSWORD`` / ``DB_SCHEMA``), so the queue connects to the
    backend's database and schema. Tests pass ``env_prefix="TEST_DB_"`` to
    target a dev DB. The fallbacks below are dev-compose values (the host
    is the compose service name); real deployments always set the env
    explicitly, so the fallback host intentionally differs from the
    backend's own ``base.py`` default.

    A transient ``OperationalError`` is retried with exponential backoff
    (``WORKER_PG_QUEUE_CONNECT_RETRIES`` total attempts, base
    ``WORKER_PG_QUEUE_CONNECT_BACKOFF`` seconds). Non-operational errors
    (e.g. a bad ``options`` string) are not transient and raise immediately.
    """
    host = os.getenv(f"{env_prefix}HOST", "unstract-db")
    port = os.getenv(f"{env_prefix}PORT", "5432")
    dbname = os.getenv(f"{env_prefix}NAME", "unstract_db")
    user = os.getenv(f"{env_prefix}USER", "unstract_dev")
    schema = os.getenv(f"{env_prefix}SCHEMA", "unstract")

    attempts = max(1, _connect_env("RETRIES", _DEFAULT_CONNECT_RETRIES, int))
    backoff = max(0.0, _connect_env("BACKOFF", _DEFAULT_CONNECT_BACKOFF, float))

    for attempt in range(1, attempts + 1):
        try:
            return psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=os.getenv(f"{env_prefix}PASSWORD", "unstract_pass"),
                options=f"-c search_path={schema}",
            )
        except psycopg2.OperationalError:
            if attempt < attempts:
                sleep_for = min(backoff * (2 ** (attempt - 1)), _CONNECT_BACKOFF_CAP)
                logger.warning(
                    "PG-queue: connect attempt %d/%d failed "
                    "(host=%s port=%s dbname=%s schema=%s); retrying in %.2fs",
                    attempt,
                    attempts,
                    host,
                    port,
                    dbname,
                    schema,
                    sleep_for,
                )
                time.sleep(sleep_for)
                continue
            # Final attempt exhausted — keep the failure self-identifying so a
            # misconfigured DB_* var is obvious. Secrets (password) omitted.
            logger.error(
                "PG-queue: failed to connect to Postgres after %d attempt(s) "
                "(host=%s port=%s dbname=%s schema=%s, env_prefix=%r)",
                attempts,
                host,
                port,
                dbname,
                schema,
                env_prefix,
            )
            raise
    raise AssertionError("unreachable: loop returns or raises")  # pragma: no cover
