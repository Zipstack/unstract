"""Read-only latency readers over the backend DB.

Why DB-side and not just client wall-clock: the server-measured
``execution_time`` is the truest cross-transport number (it excludes the
harness's own HTTP/poll overhead), and per-file ``execution_time`` exposes
*parallelism* — the single most important PG-vs-Celery signal for fan-out work.

Transport is classified post-hoc from columns that survive on the execution row
even after the (ephemeral) queue message is deleted:

- ``queue_message_id IS NOT NULL`` → PG transport
- ``task_id IS NOT NULL``          → Celery transport
- neither                          → inline / synchronous (no async dispatch)

Deliberately NOT read here: ``pg_queue_message.enqueued_at`` / ``vt`` and
``pg_task_result`` — those rows are deleted on ack / swept on expiry, so
enqueue→pickup latency is only observable by *live sampling* during a run (see
``sampler`` — a later slice), never post-hoc.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import psycopg2

from .config import DbConfig


class Transport(enum.Enum):
    """Which transport carried an execution, inferred from persistent columns."""

    PG = "pg"
    CELERY = "celery"
    INLINE = "inline"

    @classmethod
    def classify(cls, *, has_queue_message_id: bool, has_task_id: bool) -> Transport:
        if has_queue_message_id:
            return cls.PG
        if has_task_id:
            return cls.CELERY
        return cls.INLINE


@dataclass(frozen=True, slots=True)
class ExecutionLatency:
    """One execution's measured latencies (server-side, persistent)."""

    execution_id: str
    transport: Transport
    status: str
    total_files: int
    server_execution_time: float | None
    file_times: list[float] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("COMPLETED", "ERROR", "STOPPED")

    @property
    def parallelism(self) -> float | None:
        """Effective parallelism = sum(file_times) / server_execution_time.

        ``≈ N`` means all N files overlapped (ideal fan-out); ``≈ 1`` means they
        ran serially. ``None`` when it can't be computed (no files / no timing).
        """
        if not self.file_times or not self.server_execution_time:
            return None
        return sum(self.file_times) / self.server_execution_time


def connect(config: DbConfig) -> psycopg2.extensions.connection:
    """Open a read-only-intent connection (autocommit; we only SELECT)."""
    conn = psycopg2.connect(**config.dsn_kwargs())
    conn.autocommit = True
    return conn


_RECENT_SQL = """
SELECT
    e.id::text,
    (e.queue_message_id IS NOT NULL) AS has_qmid,
    (e.task_id IS NOT NULL)          AS has_taskid,
    e.status,
    e.total_files,
    e.execution_time,
    COALESCE(
        ARRAY(
            SELECT f.execution_time
            FROM workflow_file_execution f
            WHERE f.workflow_execution_id = e.id
              AND f.execution_time IS NOT NULL
            ORDER BY f.created_at
        ),
        ARRAY[]::double precision[]
    ) AS file_times
FROM workflow_execution e
{where}
ORDER BY e.created_at DESC
LIMIT %(limit)s
"""


def fetch_recent(
    conn: psycopg2.extensions.connection,
    *,
    limit: int = 100,
    transport: Transport | None = None,
    terminal_only: bool = True,
) -> list[ExecutionLatency]:
    """Return the most recent executions as ``ExecutionLatency`` records.

    ``transport`` filters to one transport (server-side); ``terminal_only``
    restricts to finished runs so ``execution_time`` is populated.
    """
    clauses: list[str] = []
    params: dict[str, object] = {"limit": limit}
    if terminal_only:
        clauses.append("e.status IN ('COMPLETED', 'ERROR', 'STOPPED')")
    if transport is Transport.PG:
        clauses.append("e.queue_message_id IS NOT NULL")
    elif transport is Transport.CELERY:
        clauses.append("e.queue_message_id IS NULL AND e.task_id IS NOT NULL")
    elif transport is Transport.INLINE:
        clauses.append("e.queue_message_id IS NULL AND e.task_id IS NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = _RECENT_SQL.format(where=where)

    rows: list[ExecutionLatency] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for (
            execution_id,
            has_qmid,
            has_taskid,
            status,
            total_files,
            exec_time,
            file_times,
        ) in cur:
            rows.append(
                ExecutionLatency(
                    execution_id=execution_id,
                    transport=Transport.classify(
                        has_queue_message_id=has_qmid, has_task_id=has_taskid
                    ),
                    status=status,
                    total_files=total_files or 0,
                    server_execution_time=exec_time,
                    file_times=list(file_times or []),
                )
            )
    return rows


_TERMINAL_STATUSES = ("COMPLETED", "ERROR", "STOPPED")

_ONE_SQL = _RECENT_SQL.format(where="WHERE e.id = %(execution_id)s::uuid")


def fetch_status(conn: psycopg2.extensions.connection, execution_id: str) -> str | None:
    """Return an execution's current status, or ``None`` if the row is absent.

    Used by the load probe to poll for terminality straight from the DB (no auth,
    cheaper than the REST status endpoint).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM workflow_execution WHERE id = %s::uuid",
            (execution_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def fetch_one(
    conn: psycopg2.extensions.connection, execution_id: str
) -> ExecutionLatency | None:
    """Return the full ``ExecutionLatency`` for one execution, or ``None``."""
    with conn.cursor() as cur:
        cur.execute(_ONE_SQL, {"execution_id": execution_id, "limit": 1})
        row = cur.fetchone()
    if row is None:
        return None
    execution_id_, has_qmid, has_taskid, status, total_files, exec_time, file_times = row
    return ExecutionLatency(
        execution_id=execution_id_,
        transport=Transport.classify(
            has_queue_message_id=has_qmid, has_task_id=has_taskid
        ),
        status=status,
        total_files=total_files or 0,
        server_execution_time=exec_time,
        file_times=list(file_times or []),
    )


def is_terminal_status(status: str | None) -> bool:
    return status in _TERMINAL_STATUSES


def queue_depth(conn: psycopg2.extensions.connection) -> dict[str, int]:
    """Current live ``pg_queue_message`` count per queue (load-monitoring aid)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT queue_name, count(*) FROM pg_queue_message GROUP BY queue_name"
        )
        return {name: count for name, count in cur}
