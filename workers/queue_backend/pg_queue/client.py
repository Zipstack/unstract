"""Thin client over the bespoke PG queue (extension-free, ``SKIP LOCKED``).

This is the storage + dequeue primitive the enqueue wiring (9b) and the
consumer poll loop (9c) build on; ``dispatch()`` routes PG-opted tasks here.

Dequeue uses the visibility-timeout pattern: :meth:`PgQueueClient.read`
runs a single atomic statement — candidate rows are locked in a CTE
(``SELECT … FOR UPDATE SKIP LOCKED LIMIT n``) and that CTE is joined into
the ``UPDATE … FROM locked`` (the EvalPlanQual-safe shape; see
``_DEQUEUE_SQL``) — committed immediately, the caller
processes the message *outside* the transaction, then
:meth:`PgQueueClient.delete` acks on success. A crash before delete
leaves the row to reappear once its ``vt`` expires — **at-least-once**
delivery: SKIP LOCKED stops two *concurrent* readers from claiming the
same visible row, but a message can still be delivered more than once if
a reader crashes before ``delete()`` and the row's ``vt`` expires, so the
consumer must be idempotent. The whole queue contract lives here, in one place;
the schema (``pg_queue_message`` table + dequeue index) is a plain
Django migration with no DB-side function.

The cached connection is kept usable across calls: every operation rolls
back on error, and a connection that goes bad (dropped socket / PgBouncer
recycle) is discarded so the next call reconnects — so one blip can't
permanently wedge the 9c consumer.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Self

from ..fairness import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY
from .connection import CONN_DEAD_ERRORS as _CONN_DEAD_ERRORS
from .connection import create_pg_connection
from .schema import qualified

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)


# ``_CONN_DEAD_ERRORS`` (the "is this a connection death?" test, shared by
# ``_cursor`` discarding the cached handle and ``send`` deciding retry eligibility)
# is imported from ``.connection`` so the dispatch/result/barrier sites can't drift.


# Atomic claim. Takes up to %(qty)s ready messages no other transaction
# holds, makes them invisible for %(vt)s seconds, returns them. SKIP LOCKED
# => concurrent readers never claim the same visible row (no concurrent
# double-claim). The caller commits immediately, processes OUTSIDE the txn,
# DELETEs on success; a crash leaves the row to reappear when vt expires
# (at-least-once — a message CAN be processed more than once). No lock held
# during processing -> VACUUM-safe and PgBouncer txn-pooling compatible.
#
# ORDER BY (priority DESC, msg_id) — the (queue_name, priority DESC, msg_id)
# index drives an indexed top-N: for a fixed queue the index is ordered by
# (priority DESC, msg_id), so PG walks rows highest-priority-first, applies the
# vt<=now() visibility filter as it goes, and stops at LIMIT — no sort of the
# whole visible backlog. Higher priority is claimed sooner; msg_id ASC is the
# FIFO tiebreak within a priority (monotonic, and unlike vt it never moves when
# a row is re-claimed). Fairness L1 (org tier) / L2 (workload) + burst_max
# admission are deferred to the fair-admission orchestrator (a later phase).
# The inner ORDER BY selects WHICH rows are claimed (the top-N by priority when
# LIMIT < available). The outer SELECT re-applies it because UPDATE ... RETURNING
# yields rows in an unspecified order — so for batch_size > 1 the caller still
# gets the batch in priority order, not physical/update order. (At the default
# batch_size = 1 only the single highest-priority row is claimed, so the outer
# sort is a no-op there.)
# Canonical PGMQ-safe shape: lock the candidate rows in a CTE, then UPDATE by
# JOINING that CTE (``UPDATE ... FROM locked WHERE msg_id = locked.msg_id``).
# The alternative — ``UPDATE ... WHERE msg_id IN (SELECT ... FOR UPDATE SKIP
# LOCKED LIMIT n)`` — can over-claim under concurrent writers: EvalPlanQual
# re-evaluates the LIMIT subquery when a row it tried to lock was concurrently
# touched, so a single claim can return more than ``n`` rows. The FROM-join form
# locks exactly ``n`` rows once and updates precisely those. The trailing SELECT
# re-applies the order because UPDATE ... RETURNING is otherwise unordered.
#
# Ordering is an index walk over (queue_name, priority DESC, msg_id) with
# ``vt <= now()`` applied as a per-row filter — not a guaranteed top-N: vt is
# not in the index, so claimed-but-unacked rows (future vt) at the front of a
# priority band are scanned past on each claim. Cheap at low in-flight depth.
def _dequeue_sql() -> str:
    """Build the atomic-claim SQL, schema-qualifying ``pg_queue_message``.

    Built per call (not a module constant) so the schema is resolved from the
    live ``DB_SCHEMA`` — the table is named ``"<schema>".pg_queue_message`` so
    it resolves through PgBouncer transaction pooling without ``search_path``
    (see :mod:`queue_backend.pg_queue.schema`). Cost is a trivial f-string vs.
    the DB round trip that follows.
    """
    msg = qualified("pg_queue_message")
    return f"""
WITH locked AS (
    SELECT msg_id
      FROM {msg}
     WHERE queue_name = %s
       AND vt <= now()
     ORDER BY priority DESC, msg_id
       FOR UPDATE SKIP LOCKED
     LIMIT %s
), claimed AS (
    UPDATE {msg} q
       SET vt = now() + make_interval(secs => %s),
           read_ct = read_ct + 1
      FROM locked
     WHERE q.msg_id = locked.msg_id
    RETURNING q.msg_id, q.message, q.read_ct, q.priority
)
SELECT msg_id, message, read_ct
  FROM claimed
 ORDER BY priority DESC, msg_id
"""


@dataclass(frozen=True, slots=True)
class QueueMessage:
    """A claimed queue message.

    ``message`` is the already-decoded JSONB payload (psycopg2 parses
    ``jsonb`` to a Python ``dict``). ``frozen`` freezes the binding only —
    the ``dict`` itself is mutable, so treat the payload as read-only by
    convention. ``read_ct`` is the post-claim delivery count — always ``>= 1``
    from the dequeue (``read_ct = read_ct + 1 RETURNING``), so consumers can
    cap redelivery of a poison message. No default: a ``0`` ("never claimed")
    can't come from the dequeue and would silently bypass the poison guard.
    """

    msg_id: int
    message: dict[str, Any]
    read_ct: int


# The whole enqueue contract (columns + their defaults) in one place. `send()`
# appends ``RETURNING msg_id``; the PG scheduler (pg_scheduler.py) executes this
# verbatim inside its own transaction so the enqueue + next_run advance commit
# atomically (it can't call send(), which commits internally). Keep callers in
# sync by calling this helper rather than copying the SQL. Built per call so
# ``pg_queue_message`` is schema-qualified from the live ``DB_SCHEMA`` (resolves
# through PgBouncer txn pooling without ``search_path`` — see
# :mod:`queue_backend.pg_queue.schema`).
def insert_message_sql() -> str:
    return (
        f"INSERT INTO {qualified('pg_queue_message')} "
        "(queue_name, message, org_id, priority, enqueued_at, vt, read_ct) "
        "VALUES (%s, %s::jsonb, %s, %s, now(), now(), 0)"
    )


# Pause duration before send()'s single reconnect-retry (see send()). This is
# the length of the pause, NOT the retry count — the one-shot bound is enforced
# structurally by send()'s single ``except`` + single retry call, not by this
# value. A literal rather than env-driven so the pause can't be tuned into a
# long blocking stall on the enqueue hot path. Note the sleep penalises the
# common idle-reap path (which reconnects instantly) purely to buy a self-heal
# window for the rarer brief DB failover, and to avoid re-hammering a struggling
# server. Caveat: this is a blocking ``time.sleep``; if send() is ever pulled
# into an async context it becomes an event-loop stall and must move to
# ``asyncio.sleep``.
_SEND_RETRY_BACKOFF_SECONDS: Final = 0.5


class PgQueueClient:
    """``send`` / ``read`` / ``delete`` over ``pg_queue_message``.

    A connection may be injected (tests); otherwise one is created lazily
    from the backend ``DB_*`` env on first use and owned by this client
    (closed by :meth:`close`, recovered automatically after a connection
    error). Usable as a context manager.
    """

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
        """Yield a cursor; commit on success, roll back + recover on error.

        Keeps the cached connection usable: a failed statement leaves the
        connection in an aborted transaction, so we always roll back; a
        dead connection can't be reused, so (when we own it) we drop the
        cached handle and the next call reconnects.
        """
        conn = self.conn
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception as exc:
            # A failed rollback proves the connection is unusable, regardless
            # of which psycopg2 error subclass was raised (a server-side
            # termination mid-statement can surface as a bare DatabaseError).
            # NOTE: ``send()``'s retry deliberately catches only
            # ``_CONN_DEAD_ERRORS``; a server death that surfaces as a *bare*
            # ``psycopg2.DatabaseError`` is still treated as dead here (via the
            # failed-rollback branch below, which drops the handle) but is
            # intentionally NOT retried by ``send()`` — it's left to the next
            # call's reconnect.
            conn_dead = isinstance(exc, _CONN_DEAD_ERRORS)
            try:
                conn.rollback()
            except Exception:
                conn_dead = True
            # Discard an unusable connection so the next call reconnects —
            # only when we own it (an injected connection is the caller's).
            if self._owns_conn and (conn_dead or conn.closed):
                with contextlib.suppress(Exception):
                    conn.close()
                self._conn = None
            raise

    def send(
        self,
        queue_name: str,
        message: dict[str, Any],
        *,
        org_id: str | None = None,
        priority: int = DEFAULT_PRIORITY,
    ) -> int:
        """Enqueue a message; returns its ``msg_id``.

        Immediately visible — ``vt`` is set to ``now()`` (DB clock). The
        timestamp/counter columns are supplied here rather than via DB
        defaults so the schema stays a plain Django migration.

        ``priority`` (fairness L3) controls dequeue order — higher is claimed
        sooner. Defaults to the neutral ``DEFAULT_PRIORITY`` for tasks dispatched
        without a fairness key (leaf tasks). Must be in ``[MIN_PRIORITY,
        MAX_PRIORITY]`` — out of range raises (it would silently jump/sink the
        row in the ``priority DESC`` claim order), mirroring ``read()``'s guards.
        The DB ``CheckConstraint`` is the backstop for any ORM/raw writer.

        Reconnect-retry: the cached connection can be reaped server-side
        (PgBouncer ``server_idle_timeout`` / DB failover) while idle BETWEEN
        sends, and ``conn.closed`` is a client-side flag only — so the first
        ``execute`` after the idle gap fails (this aborted whole executions at
        the barrier's header dispatch). We retry ONCE, but only on
        ``_CONN_DEAD_ERRORS`` and only when the failing connection was
        **reused**. The ``reused`` gate only distinguishes "cached BEFORE this
        call" from "created DURING it" (captured before the attempt, which is
        correct) — it makes the retry safe for the **idle-reap** case: a conn
        reaped while idle dies on its first statement, so the ``INSERT`` never
        ran and re-inserting can't duplicate. A **fresh** connection failing is
        a genuine error → re-raise, never retry.

        This is NOT exactly-once. A connection that dies AFTER the server has
        committed the row but BEFORE psycopg2 read back ``RETURNING msg_id``
        (the commit-loss / PgBouncer server-recycle case this very feature
        targets) is indistinguishable here from an idle reap, so the retry would
        re-insert an already-committed row. The enqueue is therefore
        **at-least-once**: the ``reused`` gate removes the *common* duplicate
        (idle reap) but cannot remove the *rare* one (post-commit death). That
        residual duplicate leans on the module's at-least-once / idempotent-
        consumer contract (see the module docstring header) as the GENERAL
        backstop — every consumer here must already tolerate redelivery.
        ``claim_batch`` / ``pg_batch_dedup`` is only the **batch-header-specific**
        instance of that idempotency: it dedups duplicate batch *headers*, but
        does NOT gate leaf tasks or the aggregating callback (which also reach
        this ``send()`` via dispatch.py) — so it does not absorb every duplicate,
        only batch-header ones.
        """
        if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
            raise ValueError(
                f"priority out of range [{MIN_PRIORITY}, {MAX_PRIORITY}]: {priority!r}"
            )
        # Capture BEFORE the attempt: a fresh conn has self._conn is None here.
        reused = self._conn is not None and self._owns_conn
        try:
            return self._insert_message(
                queue_name, message, org_id=org_id, priority=priority
            )
        except _CONN_DEAD_ERRORS as exc:
            if not reused:
                raise
            # Describe what we observed, not a verdict: a connection-level error
            # on a reused conn is usually a stale idle reap, but a real DB
            # outage looks the same here — don't assert "stale" as fact.
            logger.warning(
                "PG-queue: send to queue=%r failed with a connection-level error "
                "on a reused cached connection (%s: %s); dropping it and retrying "
                "once (stale reap or DB unavailable)",
                queue_name,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            time.sleep(_SEND_RETRY_BACKOFF_SECONDS)
            # _cursor already dropped the dead owned conn, so this reconnects.
            msg_id = self._insert_message(
                queue_name, message, org_id=org_id, priority=priority
            )
            # Positive breadcrumb: the primary hazard is a silent duplicate
            # enqueue (at-least-once, see docstring) — record the reconnect with
            # the returned msg_id so a duplicate is correlatable after the fact.
            logger.info(
                "PG-queue: send to queue=%r succeeded on reconnect (msg_id=%s)",
                queue_name,
                msg_id,
            )
            return msg_id

    def _insert_message(
        self,
        queue_name: str,
        message: dict[str, Any],
        *,
        org_id: str | None,
        priority: int,
    ) -> int:
        """One INSERT of a queue row, returning its ``msg_id`` (see :meth:`send`)."""
        with self._cursor() as cur:
            cur.execute(
                insert_message_sql() + " RETURNING msg_id",
                # "" rather than NULL for "no org" — the column is non-null
                # (string fields shouldn't have two empty values; Django S6553).
                (
                    queue_name,
                    json.dumps(message),
                    org_id if org_id is not None else "",
                    priority,
                ),
            )
            msg_id = cur.fetchone()[0]
        return int(msg_id)

    def read(
        self, queue_name: str, *, vt_seconds: int = 30, qty: int = 1
    ) -> list[QueueMessage]:
        """Atomically claim up to ``qty`` ready messages, hiding them for ``vt_seconds``.

        Commits immediately so the row lock is released and the ``vt``
        bump persists — claimed messages are then invisible to other
        readers until ``vt`` expires or :meth:`delete` removes them.

        Raises ``ValueError`` for non-positive ``vt_seconds`` (which would
        make a claimed message immediately re-visible — a double-delivery
        window) or ``qty`` (a pointless / erroring ``LIMIT``).
        """
        if vt_seconds <= 0:
            raise ValueError(f"vt_seconds must be positive, got {vt_seconds}")
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        with self._cursor() as cur:
            # Param order matches the %s positions in _dequeue_sql():
            # queue_name (locked CTE), qty (LIMIT), vt_seconds (UPDATE SET).
            cur.execute(_dequeue_sql(), (queue_name, qty, vt_seconds))
            rows = cur.fetchall()
        return [
            QueueMessage(msg_id=int(r[0]), message=r[1], read_ct=int(r[2])) for r in rows
        ]

    def set_vt(self, msg_id: int, vt_seconds: int) -> bool:
        """Re-park a claimed message: hide it for another ``vt_seconds``.

        Returns ``True`` if a row was updated (``False`` = the row is already gone,
        e.g. its vt expired and another reader deleted it). Does NOT touch
        ``read_ct`` — the increment happens on the next :meth:`read` when the row
        reappears, so a re-park loop is naturally bounded by ``read_ct`` climbing.

        Used by the consumer to defer a poison message whose terminal-ERROR mark
        could not be confirmed (backend down), so the drop never races a dead
        backend and the payload isn't discarded into a void.
        """
        if vt_seconds <= 0:
            raise ValueError(f"vt_seconds must be positive, got {vt_seconds}")
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_queue_message')} "
                "SET vt = now() + make_interval(secs => %s) WHERE msg_id = %s",
                (vt_seconds, msg_id),
            )
            return cur.rowcount == 1

    def delete(self, msg_id: int) -> bool:
        """Ack a processed message. Returns ``True`` if a row was removed.

        ``False`` means the row was already gone — typically its visibility
        timeout expired during processing and another worker (re)claimed it,
        i.e. the work may be processed twice. Logged at DEBUG here; the
        consumer emits the contextual WARNING (it names the task), so this
        avoids a duplicate warning per double-run.

        Reconnect-retry (mirrors :meth:`send`): the consumer connection idles for
        the ENTIRE wall-clock of the in-process task before this ack — minutes for
        a file-processing batch — so the ack is the single statement most likely to
        meet a PgBouncer-reaped connection. Without a retry the ack is lost and an
        ALREADY-COMPLETED message redelivers at vt expiry: duplicate work (a re-run
        of the leaf, or the sharp case — re-firing the aggregating callback's
        webhooks + subscription-usage billing). We retry ONCE, on ``_CONN_DEAD_
        ERRORS`` and only when the failing connection was **reused** (a fresh conn
        failing is a genuine error). Unlike :meth:`send`'s at-least-once INSERT this
        DELETE is idempotent — a re-run can only no-op (the row is already gone),
        never duplicate — so the retry is safe even in the ambiguous post-commit
        case (it just returns ``False``, "already gone", within the contract above).
        """
        reused = self._conn is not None and self._owns_conn
        try:
            return self._delete_row(msg_id)
        except _CONN_DEAD_ERRORS as exc:
            if not reused:
                raise
            logger.warning(
                "PG-queue: delete(msg_id=%s) failed with a connection-level error "
                "on a reused cached connection (%s: %s); dropping it and retrying "
                "the ack once so the completed message isn't redelivered",
                msg_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            time.sleep(_SEND_RETRY_BACKOFF_SECONDS)
            # _cursor already dropped the dead owned conn, so this reconnects.
            return self._delete_row(msg_id)

    def _delete_row(self, msg_id: int) -> bool:
        """One DELETE of a queue row by ``msg_id`` (see :meth:`delete`)."""
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {qualified('pg_queue_message')} WHERE msg_id = %s",
                (msg_id,),
            )
            deleted = cur.rowcount
        if deleted == 0:
            logger.debug(
                "PG-queue: delete(msg_id=%s) removed no row — already gone "
                "(vt likely expired; consumer logs the contextual warning).",
                msg_id,
            )
        return deleted == 1

    def close(self) -> None:
        """Close the connection if this client owns it (no-op if injected)."""
        if self._owns_conn and self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
