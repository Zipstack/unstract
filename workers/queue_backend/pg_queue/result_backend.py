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

Once the blocking caller consumes the reply, :meth:`PgResultBackend.forget` nulls
the payload in place — a third legal shape: ``completed``/``failed`` with
``result`` and ``error`` cleared (a tombstone the reaper deletes at
``expires_at``). Readers must not assume a finished row still carries a payload.

Two deliberate properties:

- **Idempotent writes** (``INSERT … ON CONFLICT DO NOTHING``): the PG queue is
  at-least-once, so a redelivered executor message must not clobber an already
  recorded result. First write wins.
- **Event-driven waiting with a poll fallback** (``PG_RESULT_SIGNAL_BACKEND``):
  polling ``pg_task_result`` once per in-flight task scales DB load with
  *concurrency*, not throughput (every waiter SELECTs on a backoff) — which
  saturated the DB at high concurrency. When ``PG_RESULT_SIGNAL_BACKEND=redis``,
  :meth:`store_result` RPUSHes a tiny ready-token (the reply key ONLY — never the
  payload/PII) to a per-key Redis list and :meth:`wait_for_result` BLPOPs it, then
  does ONE authoritative SELECT — so DB load scales with throughput. The DB stays
  the source of truth: a slow fallback SELECT still runs, so a lost/absent signal
  (Redis restart, missed publish) costs only latency, never correctness. PG
  ``LISTEN``/``NOTIFY`` was rejected because the *receiver* side cannot survive
  transaction-pooled PgBouncer (a session-scoped registration on a connection the
  pool reassigns each txn — the same constraint that makes the orchestrator hold a
  TTL lease rather than ``pg_advisory_lock``). With ``PG_RESULT_SIGNAL_BACKEND=poll``
  (the default) the behaviour is exactly the historical backoff poll.

Connection discipline mirrors :class:`~queue_backend.pg_queue.client.PgQueueClient`:
an injected connection is the caller's (tests); otherwise one is created lazily
from the backend ``DB_*`` env and owned here (rolled back on error, discarded +
reconnected when it goes bad). The executor consumer caches one backend for its
lifetime, so the write connection sits idle between tasks and PgBouncer can reap
it; :meth:`store_result` therefore retries once on a dead connection so the
result is still written (and the blocking caller unblocked) rather than dropped
— see :meth:`_store_with_reconnect`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, Final, Self

from unstract.core.cache.redis_client import create_redis_client
from unstract.core.data_models import PgTaskStatus
from unstract.core.polling import poll_for_row

from .connection import CONN_DEAD_ERRORS as _CONN_DEAD_ERRORS
from .connection import create_pg_connection
from .schema import qualified

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# ``_CONN_DEAD_ERRORS`` (the "is this a connection death?" test, shared by
# ``_cursor`` discarding the cached handle and ``_store_with_reconnect`` deciding
# retry eligibility) is imported from ``.connection`` so the dispatch/result/barrier
# sites can't drift.

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


def _forget_sql() -> str:
    # Null BOTH payload channels but KEEP the row: ``result`` (success payload) and
    # ``error`` (failure text — an extraction error can embed document content too),
    # so the PII scrub covers the failure channel, not just the success one. The
    # tombstone makes a redelivered ``store_result`` a ``ON CONFLICT DO NOTHING``
    # no-op (can't re-insert the payload); ``status`` still distinguishes the outcome
    # and ``expires_at`` is left untouched so the reaper still deletes the row at
    # retention.
    return (
        f"UPDATE {qualified('pg_task_result')} "
        "SET result = NULL, error = '' WHERE task_id = %s"
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

# One reconnect-retry for the IDEMPOTENT result write (see _store_with_reconnect).
# Literals (not env-driven) so the one-shot bound can't be widened operationally.
_STORE_RETRY_ATTEMPTS: Final = 2  # total attempts: 1 initial + 1 retry
_STORE_RETRY_BACKOFF_SECONDS: Final = 0.5


# --- Event-driven result signal (Redis) -------------------------------------
# ``PG_RESULT_SIGNAL_BACKEND=redis`` swaps the per-task DB poll for a Redis
# ready-token (RPUSH producer / BLPOP consumer), collapsing DB load from ~N
# SELECTs per in-flight task to ~1. Default ``poll`` preserves the historical
# backoff-poll behaviour byte-for-byte, so producer and consumer can be rolled
# independently — a flag mismatch merely degrades to the fallback poll, never wrong.
_SIGNAL_BACKEND_ENV: Final = "PG_RESULT_SIGNAL_BACKEND"
_SIGNAL_REDIS: Final = "redis"
_SIGNAL_POLL: Final = "poll"
# BLPOP wakes instantly on the token; this is the SAFETY-NET SELECT cadence for a
# lost/missed signal (Redis restart, publish before the consumer subscribed). Large
# because it should almost never fire — the token normally arrives first.
_REDIS_FALLBACK_POLL_SECONDS: Final = 30.0
# The ready-token only has to outlive the RPUSH -> BLPOP gap (normally ms). A
# generous, self-cleaning TTL covers a slow consumer; the fallback SELECT is the
# real backstop, so this need not match the result retention.
_READY_TOKEN_TTL_SECONDS: Final = 300


def _signal_backend() -> str:
    """``redis`` or ``poll`` (default), read per call so a flag flip needs no
    redeploy and producer/consumer roll independently.
    """
    value = os.environ.get(_SIGNAL_BACKEND_ENV, _SIGNAL_POLL).strip().lower()
    return _SIGNAL_REDIS if value == _SIGNAL_REDIS else _SIGNAL_POLL


def _ready_key(task_id: str) -> str:
    """Redis list key carrying the ready-token for one reply key. The task_id (a
    UUID) is the ONLY thing that ever touches Redis — never the result/PII.
    """
    return f"pg_result:ready:{task_id}"


# Process-cached Redis client for the ready-signal (redis-py pools are
# thread-safe; a first-call race just orphans one short-lived pool — not a
# correctness issue). ``None`` once we've failed to build it, so the caller
# degrades to the poll path without retrying the build every wait.
_redis_client_singleton: Any = None
_redis_client_unavailable = False


def _get_result_redis_client() -> Any:
    """Return the process-cached Redis client, or ``None`` if it can't be built.

    Mirrors ``redis_barrier._get_redis_client``: use the canonical ``REDIS_``
    prefix so Sentinel/SSL config is inherited (``create_redis_client``'s getenv
    fallback does NOT cross-fall-back SENTINEL_MODE/SSL). The token value is
    ignored — only its arrival matters — so ``decode_responses`` is irrelevant.
    """
    global _redis_client_singleton, _redis_client_unavailable
    if _redis_client_singleton is None and not _redis_client_unavailable:
        try:
            _redis_client_singleton = create_redis_client(
                env_prefix="REDIS_",
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        except Exception:
            _redis_client_unavailable = True
            logger.warning(
                "PgResultBackend: could not build the Redis client for the result "
                "signal; result waits fall back to poll",
                exc_info=True,
            )
    return _redis_client_singleton


def _signal_ready(task_id: str) -> None:
    """Best-effort wake-up: RPUSH a ready-token + (re)set its TTL. NEVER raises —
    the result is already durably committed to ``pg_task_result``, so a failed
    signal only means the waiter falls back to its slow poll. Only the reply key is
    sent to Redis (no result payload / PII).
    """
    client = _get_result_redis_client()
    if client is None:
        return
    key = _ready_key(task_id)
    try:
        pipe = client.pipeline()
        pipe.rpush(key, b"1")
        pipe.expire(key, _READY_TOKEN_TTL_SECONDS)
        pipe.execute()
    except Exception:
        logger.warning(
            "PgResultBackend: result ready-signal RPUSH failed for task_id=%s; the "
            "waiter's fallback poll will still deliver the result",
            task_id,
            exc_info=True,
        )


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
            conn_dead = isinstance(exc, _CONN_DEAD_ERRORS)
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

    def _store_with_reconnect(self, operation: Callable[[Any], None]) -> None:
        """Run an idempotent write ``operation(cur)`` in a committed cursor,
        retrying ONCE if the cached connection was reaped while idle.

        The executor consumer caches one ``PgResultBackend`` for its lifetime
        (``consumer.py``), so this connection sits idle BETWEEN tasks and can be
        dropped server-side (PgBouncer ``server_idle_timeout`` / failover) — and
        ``conn.closed`` is a client-side flag only. ``_cursor``'s discard only
        heals the *next* call, so without a retry the *current* ``store_result``
        fails, the result is silently dropped, and the blocking caller is
        stranded forever (the exec-b11ba2f3 hang). On a dead-connection error
        ``_cursor`` (when it OWNS the connection) has already dropped the handle,
        so the retry reconnects.

        Only **owned** connections are retried: ``_cursor`` clears a dead handle
        only when ``_owns_conn`` (an injected connection is the caller's), so for
        an injected connection the retry would re-acquire the same dead handle and
        buy nothing — re-raise immediately. Production is always owned (the
        executor consumer constructs ``PgResultBackend()``).

        Safe to retry unconditionally (no reused-vs-fresh guard needed, unlike
        the non-idempotent ``PgQueueClient.send``) because **every** write routed
        through here is idempotent: ``store_result``'s
        ``INSERT … ON CONFLICT (task_id) DO NOTHING`` and ``forget``'s
        ``UPDATE … SET result = NULL, error = ''`` (re-nulling an already-nulled
        tombstone is a no-op). Re-running either after an ambiguous failure can
        neither duplicate nor clobber a recorded result. Keep this invariant if a
        third caller is added — a non-idempotent write must NOT use this helper.
        """
        for attempt in range(1, _STORE_RETRY_ATTEMPTS + 1):
            try:
                with self._cursor() as cur:
                    operation(cur)
                return
            except _CONN_DEAD_ERRORS:
                # Last attempt, or an injected (non-owned) conn _cursor won't
                # have dropped — retrying can't reconnect, so re-raise.
                if attempt >= _STORE_RETRY_ATTEMPTS or not self._owns_conn:
                    raise
                # Describe what was observed, not an inferred cause: this catch
                # also covers deadlock / statement-timeout / admin-shutdown, not
                # only a stale idle reap. exc_info carries the type + message.
                logger.warning(
                    "PgResultBackend: result write failed with a connection-level "
                    "error; dropping the cached connection and retrying once",
                    exc_info=True,
                )
                time.sleep(_STORE_RETRY_BACKOFF_SECONDS)

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
        for the same key (at-least-once redelivery) is a no-op. Survives a stale
        cached connection via a one-shot reconnect-retry (see
        :meth:`_store_with_reconnect`).

        In ``PG_RESULT_SIGNAL_BACKEND=redis`` mode, once the row is committed it
        RPUSHes a ready-token so the blocking waiter wakes immediately instead of
        polling. Best-effort: a signal failure only slows the waiter (its fallback
        poll still delivers). A redelivery re-signals harmlessly — a stale token
        just expires.
        """
        if result is not None:
            status, result_json, error_text = STATUS_COMPLETED, json.dumps(result), ""
        else:
            status, result_json, error_text = STATUS_FAILED, None, error or ""
        self._store_with_reconnect(
            lambda cur: cur.execute(
                _store_sql(),
                (str(task_id), status, result_json, error_text, retention_seconds),
            )
        )
        # Row is committed above → wake any blocking waiter (redis mode only).
        if _signal_backend() == _SIGNAL_REDIS:
            _signal_ready(str(task_id))

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """Return ``{status, result, error}`` if the row exists, else ``None``.

        ``result`` is the decoded JSONB dict (psycopg2 parses ``jsonb`` to a
        Python ``dict``) or ``None``. A *missing* row (this returns ``None``) means
        the task has not finished. A *present* row with ``result is None`` is either
        a ``failed`` outcome or a ``completed`` **tombstone** whose payload was
        already cleared by :meth:`forget` post-consume — ``status`` distinguishes
        them, so a payload-poll must not treat a completed row as carrying a result.

        No reconnect-retry here (unlike :meth:`store_result`). The invariant it
        relies on: the connection is never idle long enough to be reaped when
        ``get_result`` runs. In ``poll`` mode the wait polls every ~0.2–2s so the
        connection stays warm; in ``redis`` mode :meth:`_wait_via_redis` ``close``s
        the connection before each (possibly long) ``BLPOP``, so every
        ``get_result`` runs on a freshly-opened connection. Either way a failure
        here is a genuine error, not a stale reap. If a long-lived backend ever
        gains a one-shot ``get_result`` lookup that can sit idle, revisit this.
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

        Returns the ``{status, result, error}`` dict, or ``None`` on timeout.

        ``PG_RESULT_SIGNAL_BACKEND=redis`` waits on a Redis ready-token (``BLPOP``)
        and does one authoritative :meth:`get_result` on wake — DB load scales with
        throughput, not concurrency. The DB stays the source of truth: an immediate
        check closes the publish-before-wait race, a slow fallback ``get_result``
        every ``_REDIS_FALLBACK_POLL_SECONDS`` backstops a lost signal, and any Redis
        error degrades to the poll path for the rest of the wait. ``=poll`` (default)
        is exactly the historical capped-exponential backoff poll (PgBouncer-safe),
        shared with the backend's ``DjangoQueueTransport`` poller.
        """
        if _signal_backend() != _SIGNAL_REDIS:
            return self._poll_for_result(task_id, timeout, poll_interval)
        return self._wait_via_redis(task_id, timeout, poll_interval)

    def _poll_for_result(
        self, task_id: str, timeout: float, poll_interval: float
    ) -> dict[str, Any] | None:
        """The historical backoff poll — primary path in ``poll`` mode and the
        degradation target when Redis is unavailable mid-wait.
        """
        return poll_for_row(
            lambda: self.get_result(task_id),
            timeout,
            initial=poll_interval,
            maximum=_POLL_MAX_SECONDS,
        )

    def forget(self, task_id: str) -> None:
        """Drop the stored payload once the blocking caller has consumed it.

        Nulls both payload columns (``result`` and ``error``) but keeps the row as a
        tombstone (see :func:`_forget_sql`), so a redelivered executor message can't
        re-insert the payload and the reaper still flushes the empty row at
        ``expires_at``. Cutting the payload here shrinks the window that customer
        extraction data (PII) sits in ``pg_task_result`` from the full retention TTL
        down to the read-and-clear latency; the TTL sweep remains the backstop for
        any result that is never consumed (caller crash / timeout).

        Runs through :meth:`_store_with_reconnect` because the UPDATE is idempotent
        (same rationale as ``store_result``): a transient dead-connection blip
        self-heals on the one-shot retry rather than silently costing the full TTL.

        **Best-effort by contract — never raises.** Every caller must sit under a
        never-raises guard (today: ``PgExecutionDispatcher.dispatch``'s
        ``except Exception -> failure``), because ``forget`` runs AFTER the caller
        already holds the result — a raise here would turn a successful RPC into a
        failure. A failure that survives the retry is logged and swallowed; the
        retention sweep still bounds the exposure. A *systematic* failure (revoked
        UPDATE privilege, recurring errors) is therefore observable only as a stream
        of this WARNING — alert on the ``"could not clear result"`` string until a
        ``forget_failures`` metric is wired (deferred to the pg_queue metrics work).
        """
        try:
            self._store_with_reconnect(
                lambda cur: cur.execute(_forget_sql(), (str(task_id),))
            )
        except Exception:
            logger.warning(
                "PgResultBackend.forget: could not clear result for task_id=%s "
                "after retry; the retention sweep will flush it at expires_at",
                task_id,
                exc_info=True,
            )

    def _wait_via_redis(
        self, task_id: str, timeout: float, poll_interval: float
    ) -> dict[str, Any] | None:
        """Redis ``BLPOP`` fast-path + DB-source-of-truth fallback poll.

        Correctness never depends on the signal: every wake does an authoritative
        ``get_result``, and a missed/absent token is caught by the fallback SELECT
        (bounded by ``_REDIS_FALLBACK_POLL_SECONDS``) or the final check at deadline.
        """
        deadline = time.monotonic() + timeout
        # Close the publish-before-wait race: the row may already be committed
        # (executor finished + RPUSHed before we started waiting).
        row = self.get_result(task_id)
        if row is not None:
            return row
        client = _get_result_redis_client()
        if client is None:
            return self._poll_for_result(task_id, timeout, poll_interval)
        key = _ready_key(task_id)
        while True:
            # Do NOT pin the DB connection across the (possibly long) BLPOP: an
            # idle server connection would be reaped by PgBouncer and the next
            # get_result (no reconnect-retry) would fail. Closing here means each
            # get_result below runs on a freshly-opened connection — preserving the
            # "fresh, never idle-reaped" invariant get_result relies on.
            self.close()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self.get_result(task_id)  # final authoritative check
            # BLPOP wakes instantly on the token; cap the block at the fallback
            # cadence so a missed signal still triggers a backstop SELECT. Timeout
            # is > 0 here (remaining > 0), and 0 would mean "block forever".
            block = min(remaining, _REDIS_FALLBACK_POLL_SECONDS)
            try:
                client.blpop([key], timeout=block)
            except Exception:
                # Redis blip mid-wait → degrade to the poll path for the remainder.
                logger.warning(
                    "PgResultBackend: BLPOP failed for task_id=%s; falling back to "
                    "poll for the rest of the wait",
                    task_id,
                    exc_info=True,
                )
                return self._poll_for_result(
                    task_id, max(0.0, deadline - time.monotonic()), poll_interval
                )
            row = self.get_result(task_id)
            if row is not None:
                return row
            # Woken but row not yet visible (rare) or a fallback tick → loop.

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
