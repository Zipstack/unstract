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

# psycopg2 errors that mean the connection itself is dead (dropped socket /
# PgBouncer recycle / server termination), as opposed to a logical/data error on
# a live connection. Single source of truth for every PG-queue site that decides
# "was this a connection death?" — the dispatch ``send`` reused-guard
# (``pg_queue.client``, UN-3654), the ``store_result`` retry
# (``pg_queue.result_backend``, UN-3659) and the barrier enqueue/decrement
# (``pg_barrier``, UN-3651/UN-3660). Hoisted here (the module all of them already
# import) so the three call sites can't drift apart.
CONN_DEAD_ERRORS: tuple[type[Exception], ...] = (
    psycopg2.OperationalError,
    psycopg2.InterfaceError,
)

# Bounded retry for *transient* connect failures (DB restart, PgBouncer pool
# wait, brief network partition, "too many clients" spikes) — the common cloud
# blips. Opening a connection is side-effect-free, so retrying it is safe and
# purely additive. Note we deliberately do NOT auto-retry the enqueue INSERT
# (queue_backend.pg_queue.client.send): an ambiguous commit-time failure could
# double-enqueue → double-dispatch, so that path stays fail-and-surface.
_DEFAULT_CONNECT_RETRIES = 3  # total attempts (1 = no retry)
_MAX_CONNECT_RETRIES = 10  # sane upper bound — a fat-fingered value can't wedge startup
_DEFAULT_CONNECT_BACKOFF = 0.5  # base seconds between attempts; doubles each retry
_CONNECT_BACKOFF_CAP = (
    5.0  # fixed ceiling on a single inter-attempt sleep (not env-tunable)
)


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


def _connect_retry_policy() -> tuple[int, float]:
    """Resolve ``(attempts, base_backoff)`` from env, clamping out-of-range values.

    Out-of-range knobs are clamped *and warned* (not silently coerced), mirroring
    the unparseable-value path: attempts to ``[1, _MAX_CONNECT_RETRIES]``, backoff
    to ``>= 0``. The per-sleep ``_CONNECT_BACKOFF_CAP`` is a separate fixed ceiling.
    """
    raw_retries = _connect_env("RETRIES", _DEFAULT_CONNECT_RETRIES, int)
    attempts = min(_MAX_CONNECT_RETRIES, max(1, raw_retries))
    if attempts != raw_retries:
        logger.warning(
            "PG-queue: WORKER_PG_QUEUE_CONNECT_RETRIES=%d out of range [1, %d]; "
            "clamped to %d",
            raw_retries,
            _MAX_CONNECT_RETRIES,
            attempts,
        )
    raw_backoff = _connect_env("BACKOFF", _DEFAULT_CONNECT_BACKOFF, float)
    backoff = max(0.0, raw_backoff)
    if backoff != raw_backoff:
        logger.warning(
            "PG-queue: WORKER_PG_QUEUE_CONNECT_BACKOFF=%s is negative; clamped to "
            "0.0 (retry without sleep)",
            raw_backoff,
        )
    return attempts, backoff


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
    ``WORKER_PG_QUEUE_CONNECT_BACKOFF`` seconds, each sleep capped at
    ``_CONNECT_BACKOFF_CAP``). Non-operational errors (e.g. a bad ``options``
    string) are not transient and raise immediately. **Permanent** misconfigs
    (auth failure, unknown database, bad host) also surface as ``OperationalError``,
    so they are retried-then-raised — the final ``logger.error`` makes them obvious.
    """
    host = os.getenv(f"{env_prefix}HOST", "unstract-db")
    port = os.getenv(f"{env_prefix}PORT", "5432")
    dbname = os.getenv(f"{env_prefix}NAME", "unstract_db")
    user = os.getenv(f"{env_prefix}USER", "unstract_dev")
    schema = os.getenv(f"{env_prefix}SCHEMA", "unstract")

    attempts, backoff = _connect_retry_policy()

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
            if attempt >= attempts:
                # Every attempt exhausted — keep the failure self-identifying so a
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
