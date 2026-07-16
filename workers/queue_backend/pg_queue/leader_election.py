"""Leader-election lease for the orchestrator/reaper singleton.

The orchestrator (admit) and reaper (stuck-task recovery, barrier-orphan sweep)
must run as **exactly one** active instance — several would contend on
``SKIP LOCKED`` and double-act on recovery. This module is the HA primitive that
makes that safe: candidate processes race to hold the single
``pg_orchestrator_lock`` row; the holder renews each cycle, and a standby takes
over once the lease goes stale.

**Lease, not advisory lock.** Leadership is a TTL'd ``UPDATE`` (take it if the
``leader`` is free or its ``acquired_at`` is older than the lease window), *not*
``pg_advisory_lock``. Session-scoped advisory locks do not survive the
transaction-pooled PgBouncer the queue connects through — the pooler
hands out a different backend per transaction, so a session-held lock would be
silently dropped. A plain ``UPDATE`` is one transaction → pooling-safe. Every
time comparison is server-side (``now()``), so candidate clock skew can't split
leadership.

**Primitive only.** This module is the lease mechanism — acquiring and driving
the lease is the caller's responsibility (the reaper loop). ``try_acquire`` /
``renew`` / ``release`` return ``bool`` for their *expected* outcomes; an
unexpected DB error propagates (fail-loud, by design for an HA primitive). A
caller must treat a raised exception the same as a ``False`` from ``renew`` —
"leadership state unknown, stop acting" — not assume bool-only.

Usage:

    lease = LeaderLease(default_worker_id())
    if lease.try_acquire():
        try:
            while running:
                do_one_cycle()
                try:
                    still_leader = lease.renew()
                except Exception:
                    break                 # leadership unknown — stop acting
                if not still_leader:      # lost it (we stalled past the TTL)
                    break                 # stop acting immediately
                sleep(cycle)
        finally:
            lease.release()
"""

from __future__ import annotations

import contextlib
import functools
import logging
import os
import socket
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import psycopg2

from .connection import create_pg_connection
from .schema import qualified

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# Lease window: a leader that hasn't renewed within this many seconds is
# considered dead and a standby may take over. The holder must renew well
# inside this window (the reaper loop renews every cycle). Mirrors the labs
# orchestrator's 10s lease.
_DEFAULT_LEASE_SECONDS = 10


def lease_seconds_from_env() -> int:
    """Lease window from ``WORKER_PG_ORCHESTRATOR_LEASE_SECONDS`` (default 10s).

    Read at call time so tests can flip it. Invalid / non-positive values raise,
    matching the barrier-TTL posture — a non-positive lease would let every
    candidate believe leadership is always stale and act simultaneously, which is
    exactly the split-brain this primitive exists to prevent.
    """
    raw = os.getenv("WORKER_PG_ORCHESTRATOR_LEASE_SECONDS")
    if raw is None:
        return _DEFAULT_LEASE_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"WORKER_PG_ORCHESTRATOR_LEASE_SECONDS={raw!r} is not an integer. "
            f"Unset it to default to {_DEFAULT_LEASE_SECONDS}s."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"WORKER_PG_ORCHESTRATOR_LEASE_SECONDS={value} must be a positive "
            f"integer. Unset it to default to {_DEFAULT_LEASE_SECONDS}s."
        )
    return value


@functools.cache
def default_worker_id() -> str:
    """The process's candidate id (``host:pid:rand``), fixed on first call.

    ``functools.cache`` makes this idempotent: every call within a process returns the
    same id, so ``renew``/``release`` match the row this process wrote even if a
    caller passes ``default_worker_id()`` inline in a retry/restart loop rather
    than capturing it once. The random suffix disambiguates two candidates that
    share a host+pid across container restarts. Lazy (computed on first call, not
    at import) so it's fixed after any fork rather than shared across children.
    """
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class LeaderLease:
    """A single candidate's handle on the ``pg_orchestrator_lock`` lease.

    One instance owns one Postgres connection (lazily opened, self-recovering on
    a dropped socket / PgBouncer recycle — same posture as ``PgBarrier`` /
    ``PgQueueClient``). Construct one per candidate process; in tests, inject a
    connection to race two instances.
    """

    def __init__(
        self,
        worker_id: str,
        *,
        lease_seconds: int | None = None,
        conn: PgConnection | None = None,
    ) -> None:
        if not worker_id or not worker_id.strip():
            # "" is the free sentinel — a candidate must never identify as "".
            raise ValueError("LeaderLease worker_id must be a non-empty string")
        self._worker_id = worker_id
        if lease_seconds is None:
            # lease_seconds_from_env already rejects <= 0.
            self._lease_seconds = lease_seconds_from_env()
        else:
            if lease_seconds <= 0:
                raise ValueError("lease_seconds must be a positive integer")
            self._lease_seconds = lease_seconds
        self._conn = conn
        # An injected connection belongs to the caller — never close/recycle it
        # (mirrors PgQueueClient). Critical: without this, a transient error
        # would silently swap an injected TEST_DB_ / caller connection for a
        # fresh DB_-env one, re-pointing the lease at a different database.
        self._owns_conn = conn is None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def lease_seconds(self) -> int:
        return self._lease_seconds

    def _get_conn(self) -> PgConnection:
        # Recreate only an OWNED connection that's missing/closed. An injected
        # (caller-owned) connection is never swapped — if it's dead, the next
        # statement raises rather than silently re-pointing at the DB_ env.
        if self._conn is None or (self._owns_conn and self._conn.closed):
            self._conn = create_pg_connection(env_prefix="DB_")
        return self._conn

    @contextlib.contextmanager
    def _cursor(self) -> Iterator[Any]:
        """Yield a cursor; commit on success, roll back + recover on error."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception as exc:
            # A failed rollback proves the connection is unusable regardless of
            # the psycopg2 error subclass (a server-side termination can surface
            # as a bare DatabaseError).
            conn_dead = isinstance(
                exc, (psycopg2.OperationalError, psycopg2.InterfaceError)
            )
            try:
                conn.rollback()
            except Exception:
                conn_dead = True
            # Discard an unusable connection so the next call reconnects — only
            # when we own it (an injected connection is the caller's). A silent
            # rebuild on the orchestrator/reaper singleton correlates with missed
            # renew cycles, so log it rather than swallowing the transition.
            if self._owns_conn and (conn_dead or conn.closed):
                logger.warning(
                    "LeaderLease[%s]: connection error (%s) — discarding the "
                    "owned connection; the next call will reconnect.",
                    self._worker_id,
                    type(exc).__name__,
                )
                with contextlib.suppress(Exception):
                    conn.close()
                self._conn = None
            raise

    def try_acquire(self) -> bool:
        """Take leadership if the lease is free or stale. Returns whether we won.

        Wins iff ``leader`` is empty (free) OR ``acquired_at`` is older than the
        lease window (previous holder died). The current holder re-affirming
        leadership uses :meth:`renew`, not this — a fresh, held lease returns
        ``False`` here by design.
        """
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_orchestrator_lock')} "
                "   SET leader = %s, acquired_at = now() "
                " WHERE id = 1 "
                "   AND (leader = '' "
                "        OR acquired_at < now() - make_interval(secs => %s)) "
                "RETURNING id",
                (self._worker_id, self._lease_seconds),
            )
            won = cur.fetchone() is not None
        if won:
            logger.info("LeaderLease: %s acquired leadership", self._worker_id)
        return won

    def renew(self) -> bool:
        """Extend our lease. Returns ``False`` if we are no longer the leader.

        A ``False`` is the critical safety signal: it means a standby took over
        while we stalled past the lease window. The caller **must stop acting**
        immediately — continuing would double-drive recovery against the new
        leader. A raised DB error means leadership state is *unknown* and must be
        treated the same as ``False`` (stop acting) — see the module docstring.
        """
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_orchestrator_lock')} SET acquired_at = now() "
                "WHERE id = 1 AND leader = %s RETURNING id",
                (self._worker_id,),
            )
            still_leader = cur.fetchone() is not None
        if not still_leader:
            # Fires both when a held lease was taken over (stale → standby won)
            # and when a non-holder calls renew — phrase it for both.
            logger.warning(
                "LeaderLease: %s renew failed — not the current leader "
                "(taken over by another candidate, or the lease was never held)",
                self._worker_id,
            )
        return still_leader

    def release(self) -> None:
        """Free the lease on graceful shutdown so a standby takes over at once.

        Only frees it if we still hold it (``leader = us``); if we already lost
        leadership this is a no-op, so a late release can't wipe the new holder.
        """
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_orchestrator_lock')} "
                "SET leader = '', acquired_at = now() "
                "WHERE id = 1 AND leader = %s",
                (self._worker_id,),
            )
            freed = cur.rowcount == 1
        if freed:
            logger.info("LeaderLease: %s released leadership", self._worker_id)
        else:
            # We already lost the lease to a standby — don't misreport that this
            # process freed it (misleading in the split-brain post-mortem this
            # primitive exists to support).
            logger.debug(
                "LeaderLease: %s release was a no-op (not the current holder)",
                self._worker_id,
            )
