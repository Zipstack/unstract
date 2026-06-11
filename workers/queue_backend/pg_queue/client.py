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
leaves the row to reappear once its ``vt`` expires — at-least-once
delivery, no double-delivery (SKIP LOCKED guarantees a row is claimed by
at most one reader). The whole queue contract lives here, in one place;
the schema (``pg_queue_message`` table + dequeue index) is a plain
Django migration with no DB-side function.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .connection import create_pg_connection

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

# Atomic claim. Takes up to %(qty)s ready messages no other transaction
# holds, makes them invisible for %(vt)s seconds, returns them. SKIP LOCKED
# => concurrent readers never claim the same row (no double-delivery). The
# caller commits immediately, processes OUTSIDE the txn, DELETEs on success;
# a crash leaves the row to reappear when vt expires (at-least-once). No lock
# held during processing -> VACUUM-safe and PgBouncer txn-pooling compatible.
_DEQUEUE_SQL = """
UPDATE pg_queue_message
   SET vt = now() + make_interval(secs => %s),
       read_ct = read_ct + 1
 WHERE msg_id IN (
     SELECT msg_id
       FROM pg_queue_message
      WHERE queue_name = %s
        AND vt <= now()
      ORDER BY msg_id
        FOR UPDATE SKIP LOCKED
      LIMIT %s
 )
RETURNING msg_id, message
"""


@dataclass(frozen=True)
class QueueMessage:
    """A claimed queue message."""

    msg_id: int
    message: dict[str, Any]


class PgQueueClient:
    """``send`` / ``read`` / ``delete`` over ``pg_queue_message``.

    A connection may be injected (tests); otherwise one is created lazily
    from the backend ``DB_*`` env on first use.
    """

    def __init__(self, conn: PgConnection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> PgConnection:
        if self._conn is None:
            self._conn = create_pg_connection()
        return self._conn

    def send(
        self, queue_name: str, message: dict[str, Any], *, org_id: str | None = None
    ) -> int:
        """Enqueue a message; returns its ``msg_id``.

        Immediately visible — ``vt`` is set to ``now()`` (DB clock). The
        timestamp/counter columns are supplied here rather than via DB
        defaults so the schema stays a plain Django migration.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_queue_message "
                "(queue_name, message, org_id, enqueued_at, vt, read_ct) "
                "VALUES (%s, %s::jsonb, %s, now(), now(), 0) RETURNING msg_id",
                (queue_name, json.dumps(message), org_id),
            )
            msg_id = cur.fetchone()[0]
        self.conn.commit()
        return int(msg_id)

    def read(
        self, queue_name: str, *, vt_seconds: int = 30, qty: int = 1
    ) -> list[QueueMessage]:
        """Atomically claim up to ``qty`` ready messages, hiding them for ``vt_seconds``.

        Commits immediately so the row lock is released and the ``vt``
        bump persists — claimed messages are then invisible to other
        readers until ``vt`` expires or :meth:`delete` removes them.
        """
        with self.conn.cursor() as cur:
            cur.execute(_DEQUEUE_SQL, (vt_seconds, queue_name, qty))
            rows = cur.fetchall()
        self.conn.commit()
        return [QueueMessage(msg_id=int(r[0]), message=r[1]) for r in rows]

    def delete(self, msg_id: int) -> bool:
        """Ack a processed message. Returns ``True`` if a row was removed."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM pg_queue_message WHERE msg_id = %s", (msg_id,))
            deleted = cur.rowcount
        self.conn.commit()
        return deleted == 1
