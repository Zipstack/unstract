"""Postgres request-reply result store for the executor RPC (Phase 9).

Replaces Celery's ``AsyncResult`` / result backend for the *blocking* executor
dispatch when it rides the PG transport. The PG executor consumer
(``worker-pg-executor``) writes a finished task's outcome here, keyed by the
caller-chosen reply key; the blocking caller polls :meth:`wait_for_result`
until the row appears or its timeout elapses.

A row appears ONLY when the task finishes — ``status="completed"`` carrying the
``ExecutionResult.to_dict()`` payload, or ``status="failed"`` carrying the error
text if the task raised. Absence of a row means "not done yet"; there is
deliberately no ``pending`` state to maintain.

Two deliberate properties:

- **Idempotent writes** (``INSERT … ON CONFLICT DO NOTHING``): the PG queue is
  at-least-once, so a redelivered executor message must not clobber an already
  recorded result. First write wins.
- **Poll-based waiting, NOT ``LISTEN``/``NOTIFY``**: ``NOTIFY`` does not survive
  transaction-pooled PgBouncer (the same constraint that makes the orchestrator
  lock a TTL lease rather than ``pg_advisory_lock``). Polling with backoff is
  pooling-safe and needs no persistent listener connection.

Connection discipline mirrors :class:`~queue_backend.pg_queue.client.PgQueueClient`:
an injected connection is the caller's (tests); otherwise one is created lazily
from the backend ``DB_*`` env and owned here (rolled back on error, discarded +
reconnected when it goes bad).
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Self

import psycopg2

from unstract.core.data_models import PgTaskStatus
from unstract.core.polling import poll_for_row

from .connection import create_pg_connection
from .schema import qualified

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# How long a stored result lives before the reaper's retention sweep may delete
# it. Defaults to the executor caller-timeout default so a result always
# outlives any caller still waiting on it.
DEFAULT_RETENTION_SECONDS = 3600


# First write wins — an at-least-once redelivery of the executor message must
# not overwrite a recorded result. Built per call so ``pg_task_result`` is
# schema-qualified from the live ``DB_SCHEMA`` (resolves through PgBouncer txn
# pooling without ``search_path`` — see :mod:`queue_backend.pg_queue.schema`).
def _store_sql() -> str:
    return (
        f"INSERT INTO {qualified('pg_task_result')} "
        "(task_id, status, result, error, created_at, expires_at) "
        "VALUES (%s, %s, %s::jsonb, %s, now(), now() + make_interval(secs => %s)) "
        "ON CONFLICT (task_id) DO NOTHING"
    )


def _get_sql() -> str:
    return (
        f"SELECT status, result, error FROM {qualified('pg_task_result')} "
        "WHERE task_id = %s"
    )


# Poll cadence for wait_for_result: start tight (low latency for fast tasks),
# back off to a ceiling so a long-running task doesn't hammer the DB.
_POLL_INITIAL_SECONDS = 0.2
_POLL_MAX_SECONDS = 2.0

# Status vocabulary — sourced from the shared enum in unstract.core so the writer
# (here) and the backend reader agree across the process boundary. Re-exported as
# plain strings for the SQL/tests.
STATUS_COMPLETED = PgTaskStatus.COMPLETED.value
STATUS_FAILED = PgTaskStatus.FAILED.value


class PgResultBackend:
    """``store_result`` / ``get_result`` / ``wait_for_result`` over ``pg_task_result``."""

    def __init__(self, conn: PgConnection | None = None) -> None:
        self._conn = conn
        # Injected connections belong to the caller — never close/recycle them.
        self._owns_conn = conn is None

    @property
    def conn(self) -> PgConnection:
        if self._conn is None:
            self._conn = create_pg_connection()
        return self._conn

    @contextlib.contextmanager
    def _cursor(self) -> Iterator[Any]:
        """Yield a cursor; commit on success, roll back + recover on error."""
        conn = self.conn
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception as exc:
            conn_dead = isinstance(
                exc, (psycopg2.OperationalError, psycopg2.InterfaceError)
            )
            try:
                conn.rollback()
            except Exception:
                # A failed rollback proves the connection is unusable regardless
                # of the original error subclass — recycle it (and surface why,
                # rather than swallowing it silently).
                logger.warning(
                    "PgResultBackend: rollback failed; treating connection as dead",
                    exc_info=True,
                )
                conn_dead = True
            if self._owns_conn and (conn_dead or conn.closed):
                with contextlib.suppress(Exception):
                    conn.close()
                self._conn = None
            raise

    def store_result(
        self,
        task_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        retention_seconds: int = DEFAULT_RETENTION_SECONDS,
    ) -> None:
        """Record a finished task's outcome under *task_id* (the reply key).

        ``result`` (a dict, e.g. ``ExecutionResult.to_dict()``) → ``completed``.
        Otherwise → ``failed`` with ``error`` text. Idempotent: a second write
        for the same key (at-least-once redelivery) is a no-op.
        """
        if result is not None:
            status, result_json, error_text = STATUS_COMPLETED, json.dumps(result), ""
        else:
            status, result_json, error_text = STATUS_FAILED, None, error or ""
        with self._cursor() as cur:
            cur.execute(
                _store_sql(),
                (str(task_id), status, result_json, error_text, retention_seconds),
            )

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """Return ``{status, result, error}`` if the row exists, else ``None``.

        ``result`` is the decoded JSONB dict (psycopg2 parses ``jsonb`` to a
        Python ``dict``); ``None`` means the task has not finished yet.
        """
        with self._cursor() as cur:
            cur.execute(_get_sql(), (str(task_id),))
            row = cur.fetchone()
        if row is None:
            return None
        status, result, error = row
        return {"status": status, "result": result, "error": error}

    def wait_for_result(
        self,
        task_id: str,
        timeout: float,
        *,
        poll_interval: float = _POLL_INITIAL_SECONDS,
    ) -> dict[str, Any] | None:
        """Block until the result row appears or *timeout* seconds elapse.

        Returns the ``{status, result, error}`` dict, or ``None`` on timeout. Uses
        the shared :func:`~unstract.core.polling.poll_for_row` backoff (capped
        exponential, PgBouncer-safe; the final sleep is clamped to the deadline) — the
        same skeleton the backend's ``DjangoQueueTransport`` poller uses, so the
        backoff lives in one place.
        """
        return poll_for_row(
            lambda: self.get_result(task_id),
            timeout,
            initial=poll_interval,
            maximum=_POLL_MAX_SECONDS,
        )

    def close(self) -> None:
        """Close an owned connection (injected connections are the caller's)."""
        if self._owns_conn and self._conn is not None and not self._conn.closed:
            with contextlib.suppress(Exception):
                self._conn.close()
        self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
