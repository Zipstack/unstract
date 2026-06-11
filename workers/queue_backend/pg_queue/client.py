"""Thin client over the bespoke PG queue (extension-free, ``SKIP LOCKED``).

**Inert in this phase** — nothing in ``dispatch()`` calls this yet (the
routing gate's PG branch still routes to Celery). This is the storage +
dequeue primitive that the enqueue wiring (9b) and the consumer poll
loop (9c) build on.

Dequeue uses the visibility-timeout pattern: :meth:`PgQueueClient.read`
runs a single atomic ``UPDATE … WHERE msg_id IN (SELECT … FOR UPDATE
SKIP LOCKED …) RETURNING …`` (committed immediately), the caller
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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

import psycopg2

from .connection import create_pg_connection

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# Atomic claim. Takes up to %(qty)s ready messages no other transaction
# holds, makes them invisible for %(vt)s seconds, returns them. SKIP LOCKED
# => concurrent readers never claim the same visible row (no concurrent
# double-claim). The caller commits immediately, processes OUTSIDE the txn,
# DELETEs on success; a crash leaves the row to reappear when vt expires
# (at-least-once — a message CAN be processed more than once). No lock held
# during processing -> VACUUM-safe and PgBouncer txn-pooling compatible.
#
# ORDER BY (vt, msg_id) — not just msg_id — so the (queue_name, vt, msg_id)
# index drives an indexed top-N: for a fixed queue the index is ordered by
# (vt, msg_id), so the vt<=now() range scan emits rows already sorted and PG
# applies LIMIT without sorting the whole visible backlog. Still effectively
# FIFO (vt is set to now() at enqueue; msg_id is the deterministic tiebreak).
_DEQUEUE_SQL = """
UPDATE pg_queue_message
   SET vt = now() + make_interval(secs => %s),
       read_ct = read_ct + 1
 WHERE msg_id IN (
     SELECT msg_id
       FROM pg_queue_message
      WHERE queue_name = %s
        AND vt <= now()
      ORDER BY vt, msg_id
        FOR UPDATE SKIP LOCKED
      LIMIT %s
 )
RETURNING msg_id, message
"""


@dataclass(frozen=True, slots=True)
class QueueMessage:
    """A claimed queue message.

    ``message`` is the already-decoded JSONB payload (psycopg2 parses
    ``jsonb`` to a Python ``dict``). ``frozen`` freezes the binding only —
    the ``dict`` itself is mutable, so treat the payload as read-only by
    convention.
    """

    msg_id: int
    message: dict[str, Any]


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
            conn_dead = isinstance(
                exc, (psycopg2.OperationalError, psycopg2.InterfaceError)
            )
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
        self, queue_name: str, message: dict[str, Any], *, org_id: str | None = None
    ) -> int:
        """Enqueue a message; returns its ``msg_id``.

        Immediately visible — ``vt`` is set to ``now()`` (DB clock). The
        timestamp/counter columns are supplied here rather than via DB
        defaults so the schema stays a plain Django migration.
        """
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO pg_queue_message "
                "(queue_name, message, org_id, enqueued_at, vt, read_ct) "
                "VALUES (%s, %s::jsonb, %s, now(), now(), 0) RETURNING msg_id",
                # "" rather than NULL for "no org" — the column is non-null
                # (string fields shouldn't have two empty values; Django S6553).
                (queue_name, json.dumps(message), org_id if org_id is not None else ""),
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
            cur.execute(_DEQUEUE_SQL, (vt_seconds, queue_name, qty))
            rows = cur.fetchall()
        return [QueueMessage(msg_id=int(r[0]), message=r[1]) for r in rows]

    def delete(self, msg_id: int) -> bool:
        """Ack a processed message. Returns ``True`` if a row was removed.

        ``False`` means the row was already gone — typically its visibility
        timeout expired during processing and another worker (re)claimed it,
        i.e. the work may be processed twice. Logged at WARNING so this
        at-least-once condition is visible rather than silently swallowed.
        """
        with self._cursor() as cur:
            cur.execute("DELETE FROM pg_queue_message WHERE msg_id = %s", (msg_id,))
            deleted = cur.rowcount
        if deleted == 0:
            logger.warning(
                "PG-queue: delete(msg_id=%s) removed no row — message was already "
                "gone (vt likely expired during processing; possible re-delivery).",
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
