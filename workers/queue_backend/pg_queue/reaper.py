"""Reaper — the leader-elected recovery process for the PG queue.

A singleton, guarded by :class:`LeaderLease` over ``pg_orchestrator_lock``: only
the elected leader runs recovery work each cycle (several reapers would contend
and double-act). It ships the process *harness* (lease-maintenance loop +
graceful shutdown) plus the **barrier-orphan recovery** job.

**Barrier-orphan recovery.** Handles ``pg_barrier_state`` rows past their
``expires_at`` — a barrier whose header tasks never all completed (the documented
:class:`PgBarrier` backstop). For each, the leader (:func:`recover_expired_barriers`):

1. **Marks the execution ERROR** via the internal API — the same path the normal
   callback uses for terminal status (business state never goes direct-DB) — with
   a message distinguishing ``remaining>0`` (work incomplete) from ``remaining==0``
   (all batches done, callback never fired). It reads status first and **skips the
   mark if the execution is already terminal** (a ``remaining==0`` row can belong
   to a COMPLETED execution whose best-effort row-delete merely failed, and the
   backend status update has no terminal guard) or if the row carries no org.
2. **Reclaims the queue-infra rows** (``pg_batch_dedup`` + ``pg_barrier_state``)
   directly in PG — same boundary as the rest of ``queue_backend``.

Recovery is best-effort and per-execution: a failure (e.g. the API is
unreachable) leaves that barrier row for the next sweep to retry, and never
blocks the others. **This is the recovery net PG-queue execution rollout depends
on** — without it the un-catchable strand windows (a worker SIGKILL mid-batch, or
a crash after the final decrement but before the callback enqueues) would bottom
out silently at the ~6h barrier expiry.

**Deferred (follow-up).** *Callback re-fire* for the ``remaining==0`` strand
(heal → COMPLETED instead of ERROR) needs the ``callback_descriptor`` stored on
the barrier row; until then those strands are marked ERROR. Per-stage re-enqueue
of stuck file executions is a larger pipeline-recovery effort beyond this net.

**Lease maintenance.** Each cycle the leader renews; if ``renew()`` returns
``False`` (or raises) it lost / can't confirm the lease and steps down to
standby. A standby tries to acquire each cycle. The cycle interval MUST be
shorter than the lease window, or the leader would lose the lease between
renews — enforced in :meth:`PgReaper.__init__`.

**Ships dark.** Launched explicitly (``python -m queue_backend.pg_queue.reaper``
or, later, ``run-worker.sh``); never part of the default worker set. With
``WORKER_BARRIER_BACKEND`` left at ``chord`` (default) there are no
``pg_barrier_state`` rows, so the sweep is a no-op until the PG barrier is used.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple, Protocol, TypeVar

from unstract.core.data_models import ExecutionStatus

from ..barrier import barrier_stuck_timeout_seconds
from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id
from .liveness import LivenessServer as _BaseLivenessServer
from .pg_scheduler import dispatch_due_schedules
from .schema import qualified

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection
    from shared.api import InternalAPIClient

logger = logging.getLogger(__name__)

# Cadence: how often the leader renews + runs recovery. Enforced shorter than
# the lease window in PgReaper.__init__.
_DEFAULT_REAPER_INTERVAL_SECONDS = 5.0
# Retention sweep cadence — far rarer than the tick (cleanup, not recovery), so
# the per-cycle DELETE doesn't run every few seconds.
_DEFAULT_SWEEP_INTERVAL_SECONDS = 300.0
# Default age before an orphaned ``pg_batch_dedup`` marker is swept. Should be set
# (here / via WORKER_PG_DEDUP_RETENTION_SECONDS) above the longest possible
# execution, else a still-in-flight marker could be swept out from under a running
# fan-out — this is operator-enforced, not coupled in code to the actual bound. 24h
# is comfortably above any single execution.
_DEFAULT_DEDUP_RETENTION_SECONDS = 86400

# A barrier is "stranded" when it has made no progress for the stuck-timeout (the
# fast, per-progress signal — UN-3661) OR it has passed its absolute ``expires_at``
# cap (the last-resort backstop). Both feed the SAME recovery. Defined once so the
# detection SELECT, the pre-mark re-check, and the cleanup DELETE can't drift.
# Binds one ``%s`` — the stuck-timeout in seconds (``barrier_stuck_timeout_seconds``).
_STRANDED_PREDICATE = (
    "(last_progress_at < now() - make_interval(secs => %s) OR expires_at < now())"
)

_N = TypeVar("_N", int, float)


class LeaderLeaseLike(Protocol):
    """Structural contract :class:`PgReaper` needs from a lease.

    The dependency is structural (the tests substitute a duck-typed fake), so the
    param is typed against this Protocol — :class:`LeaderLease` satisfies it, and
    a fake conforms without inheritance. Same convention as the ``Barrier``
    Protocol elsewhere in the package.
    """

    @property
    def lease_seconds(self) -> int: ...

    @property
    def worker_id(self) -> str: ...

    def try_acquire(self) -> bool: ...

    def renew(self) -> bool: ...

    def release(self) -> None: ...


class TickOutcome(NamedTuple):
    """Result of one :meth:`PgReaper.tick` — keeps "was I leader" and "how much
    work" on separate channels (an ``int`` sentinel like ``-1`` is truthy and
    conflates the two).
    """

    was_leader: bool
    reclaimed: int  # 0 when standby


def reaper_interval_from_env() -> float:
    """Cycle interval from ``WORKER_PG_REAPER_INTERVAL_SECONDS`` (default 5s).

    Read at call time. Invalid / non-positive values raise (loud-on-misconfig,
    matching the lease/barrier-TTL posture).
    """
    raw = os.getenv("WORKER_PG_REAPER_INTERVAL_SECONDS")
    if raw is None:
        return _DEFAULT_REAPER_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"WORKER_PG_REAPER_INTERVAL_SECONDS={raw!r} is not a number. "
            f"Unset it to default to {_DEFAULT_REAPER_INTERVAL_SECONDS}s."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"WORKER_PG_REAPER_INTERVAL_SECONDS={value} must be positive. "
            f"Unset it to default to {_DEFAULT_REAPER_INTERVAL_SECONDS}s."
        )
    return value


def _positive_duration_from_env(name: str, default: _N, cast: Callable[[str], _N]) -> _N:
    """Read a positive duration env var (default on unset; raise on invalid/<=0).

    Same loud-on-misconfig posture as :func:`reaper_interval_from_env`, shared by
    the sweep-cadence and dedup-retention knobs.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = cast(raw)
    except ValueError as exc:
        # Include the cause: an int knob given "1.5" IS a number, just not an int —
        # "is not a number" would mislead. The cause spells out the real reason.
        raise ValueError(
            f"{name}={raw!r} cannot be parsed: {exc}. Unset it to default to {default}."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"{name}={value} must be positive. Unset it to default to {default}."
        )
    return value


def reaper_sweep_interval_from_env() -> float:
    """Retention-sweep cadence from ``WORKER_PG_REAPER_SWEEP_SECONDS`` (default 300s)."""
    return _positive_duration_from_env(
        "WORKER_PG_REAPER_SWEEP_SECONDS", _DEFAULT_SWEEP_INTERVAL_SECONDS, float
    )


def dedup_retention_from_env() -> int:
    """Dedup-orphan age from ``WORKER_PG_DEDUP_RETENTION_SECONDS`` (default 24h)."""
    return _positive_duration_from_env(
        "WORKER_PG_DEDUP_RETENTION_SECONDS", _DEFAULT_DEDUP_RETENTION_SECONDS, int
    )


def _rollback_after_sweep_failure(conn: PgConnection, table: str) -> None:
    """Roll back after a failed sweep DELETE; surface a rollback that itself fails.

    The caller re-raises the original error regardless — but a rollback that also
    raises (broken socket / admin-terminated backend) signals a dead connection, so
    log it rather than swallow it silently (which would hide why the next cycle's
    reconnect is needed).
    """
    try:
        conn.rollback()
    except Exception:
        logger.warning(
            "Reaper: rollback after a failed %s sweep also failed "
            "(connection likely dead)",
            table,
            exc_info=True,
        )


def sweep_expired_results(conn: PgConnection) -> int:
    """Delete expired executor-RPC result rows; return the number deleted.

    ``pg_task_result`` rows carry ``expires_at = now() + retention`` (written by
    the consumer's ``store_result``, ``DEFAULT_RETENTION_SECONDS``). Once past it no
    caller is still waiting **by default** — that retention matches the caller-
    timeout default (``EXECUTOR_RESULT_TIMEOUT``), so the result has outlived any
    wait. (An operator who raises the caller timeout ABOVE the store retention could
    in principle have a result swept mid-wait; size the retention >= the longest
    caller timeout.) The table has no other reader once expired, so this is the only
    thing keeping it from growing unbounded with each RPC. Idempotent
    (``DELETE … WHERE``) and uses the ``pg_task_result_expires_idx`` index. Rolls
    back on error so the manual-commit connection isn't left in an aborted-txn state.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {qualified('pg_task_result')} WHERE expires_at <= now()"
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        _rollback_after_sweep_failure(conn, "pg_task_result")
        raise


def sweep_orphan_dedup(conn: PgConnection, retention_seconds: int) -> int:
    """Delete orphaned per-batch dedup markers older than *retention_seconds*.

    ``pg_batch_dedup`` markers are normally cleared on barrier teardown / reaper
    barrier-recovery, but a partial-failure execution can leave them behind. A
    marker only matters while its execution is in flight, so anything older than
    the longest possible execution (*retention_seconds*) is a safe-to-drop orphan.
    Filters on ``created_at``, which is deliberately **unindexed** (see
    ``backend/pg_queue/models.py``), so each sweep seq-scans — fine at the 5-min
    cadence on a normally-near-empty table; add an index if the dedup table grows.
    Idempotent; rolls back on error.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {qualified('pg_batch_dedup')} "
                "WHERE created_at <= now() - make_interval(secs => %s)",
                (retention_seconds,),
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        _rollback_after_sweep_failure(conn, "pg_batch_dedup")
        raise


def _execution_status(
    api_client: InternalAPIClient, execution_id: str, organization_id: str
) -> str | None:
    """Current execution status via the org-scoped internal API.

    **Raises** when the read fails. The client catches all errors and returns a
    ``success=False`` response (it does NOT raise), so a transient blip would
    yield ``status=None`` — which is not terminal, and the caller would then mark
    a possibly-COMPLETED execution ERROR. Treating "couldn't read" as a hard stop
    (the caller's ``except`` retains the row for retry) is what keeps the
    terminal-skip guard honest.
    """
    response = api_client.get_workflow_execution(
        execution_id, organization_id=organization_id, file_execution=False
    )
    if not getattr(response, "success", False):
        raise RuntimeError(
            f"status read failed for execution {execution_id} "
            f"(refusing to mark ERROR on an unconfirmed status)"
        )
    return getattr(response, "status", None)


def _still_stranded(
    conn: PgConnection, execution_id: str, stuck_timeout_seconds: int
) -> bool:
    """True iff the barrier row is still present AND still stranded.

    Re-checked immediately before the ERROR mark so a same-id re-enqueue (UPSERT
    resets both ``expires_at`` to the future AND ``last_progress_at`` to now())
    between the sweep's SELECT and the mark doesn't get its live run flagged ERROR.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM {qualified('pg_barrier_state')} "
            f"WHERE execution_id = %s AND {_STRANDED_PREDICATE}",
            (execution_id, stuck_timeout_seconds),
        )
        found = cur.fetchone() is not None
    conn.commit()
    return found


def _mark_stranded_error(
    api_client: InternalAPIClient,
    execution_id: str,
    organization_id: str,
    remaining: int,
) -> None:
    """Mark a confirmed-non-terminal stranded execution ERROR (message by remaining)."""
    if remaining > 0:
        reason = (
            f"{remaining} file batch(es) never completed before the barrier "
            f"expired (worker crash / lost task)"
        )
    elif remaining == 0:
        reason = (
            "all file batches completed but the final aggregating callback never "
            "fired before the barrier expired"
        )
    else:  # remaining < 0: a decrement landed after the row was torn down
        reason = (
            "the barrier was already torn down (remaining < 0) yet the execution "
            "was left non-terminal — inconsistent state"
        )
    response = api_client.update_workflow_execution_status(
        execution_id=execution_id,
        status=ExecutionStatus.ERROR.value,
        error_message=f"[reaper-recovery] Execution stranded: {reason}.",
        organization_id=organization_id,
        # Cascade ERROR to the execution's non-terminal file executions in the same
        # backend transaction — else the execution goes ERROR while its files stay
        # EXECUTING (the b11ba2f3 inconsistency).
        cascade_terminal_files=True,
    )
    # Mirror the read path (_execution_status): the internal client returns an
    # APIResponse and may report a failed write via ``success=False`` rather than
    # raising. Treat a non-success as a hard failure so the caller does NOT proceed
    # to DELETE the barrier row (erasing the only recovery handle while the
    # execution stays non-terminal). ``success`` absent → assume raised-on-failure
    # legacy contract (True).
    if not getattr(response, "success", True):
        raise RuntimeError(
            f"status update for stranded execution {execution_id} reported "
            f"success=False (refusing to delete the barrier recovery handle)"
        )
    logger.error(
        "Reaper: marked stranded execution %s ERROR (remaining=%s).",
        execution_id,
        remaining,
    )


def _recover_one_barrier(
    conn: PgConnection,
    api_client: InternalAPIClient,
    execution_id: str,
    organization_id: str,
    remaining: int,
    stuck_timeout_seconds: int,
) -> bool:
    """Recover one stranded execution; return True iff its barrier row was deleted.

    Marks the execution ERROR via the **internal API** (the path the normal
    callback uses for terminal status — business state never goes direct-DB),
    UNLESS the status read shows it's already terminal (``ExecutionStatus
    .is_completed`` — the single source of truth, so a future terminal status
    can't drift from a local copy). A ``remaining==0`` expired row can belong to
    a COMPLETED execution whose best-effort row-delete merely failed, and the
    backend status update has no terminal guard, so the read-first skip prevents
    overwriting a finished execution. Queue-infra cleanup (``pg_batch_dedup`` /
    ``pg_barrier_state``) stays direct-PG.

    The barrier ``DELETE`` is re-guarded on ``expires_at < now()``: between the
    sweep's SELECT and here the same ``execution_id`` could be re-enqueued
    (UPSERT resets ``expires_at`` to the future), and we must not tear down a
    freshly re-armed barrier. If the row was re-armed (``rowcount == 0``) we leave
    it and its dedup markers (the new run owns them); the dedup delete only runs
    when the barrier row was actually reclaimed.

    Returns False (no mark, no delete) when the row can't be safely recovered:
    org unknown (can't call the org-scoped API → the row is LEFT, not erased, so
    the only recovery handle survives for ops; should never happen), a successful
    read with no status (anomalous), or the row was **re-armed** before the mark.
    The mark is gated on a re-check that the row is *still* expired immediately
    before it fires — so a same-id re-enqueue can't get its live run marked ERROR
    (the worst outcome) — and the DELETE is additionally guarded on
    ``expires_at < now()`` so a re-armed barrier is never torn down.
    """
    if not organization_id:
        logger.error(
            "Reaper: stranded barrier for execution %s has NO organization_id — "
            "cannot mark it ERROR via the org-scoped API; leaving the row (not "
            "erasing the only recovery handle). A barrier was enqueued without an "
            "org — investigate.",
            execution_id,
        )
        return False

    status = _execution_status(api_client, execution_id, organization_id)
    if status is None:
        # A successful read with no status is anomalous — don't mark on it; leave
        # the row for the next sweep rather than risk a wrong ERROR.
        logger.warning(
            "Reaper: status read for execution %s returned no status — leaving the "
            "row for the next sweep (not marking ERROR on an indeterminate status).",
            execution_id,
        )
        return False
    if ExecutionStatus.is_completed(status):
        logger.warning(
            "Reaper: barrier for execution %s expired but the execution is already "
            "%s — cleaning up the orphaned row only (no status overwrite).",
            execution_id,
            status,
        )
    elif not _still_stranded(conn, execution_id, stuck_timeout_seconds):
        # Re-armed (same execution_id re-enqueued) between the read and here —
        # do NOT mark a freshly-running execution ERROR; leave it for the new run.
        logger.warning(
            "Reaper: execution %s was re-armed during recovery — skipping the "
            "ERROR mark (its new run owns the barrier).",
            execution_id,
        )
        return False
    else:
        _mark_stranded_error(api_client, execution_id, organization_id, remaining)

    # Queue-infra cleanup (direct PG), re-guarded against a concurrent re-arm.
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {qualified('pg_barrier_state')} WHERE execution_id = %s "
            f"AND {_STRANDED_PREDICATE}",
            (execution_id, stuck_timeout_seconds),
        )
        deleted = cur.rowcount > 0
        if deleted:
            cur.execute(
                f"DELETE FROM {qualified('pg_batch_dedup')} WHERE execution_id = %s",
                (execution_id,),
            )
        else:
            logger.warning(
                "Reaper: barrier for execution %s was re-armed during recovery "
                "(no longer expired) — leaving its rows for the new run.",
                execution_id,
            )
    conn.commit()
    return deleted


def recover_expired_barriers(
    conn: PgConnection,
    api_client: InternalAPIClient,
    stuck_timeout_seconds: int | None = None,
) -> list[str]:
    """Recover stranded executions. Returns recovered ids.

    A barrier is stranded when it has made no progress for
    ``stuck_timeout_seconds`` (the fast per-progress signal — a crashed worker's
    batch, or a runaway) OR it has passed its absolute ``expires_at`` cap; see
    :data:`_STRANDED_PREDICATE`. ``stuck_timeout_seconds`` defaults to
    :func:`~queue_backend.barrier.barrier_stuck_timeout_seconds` (resolved once
    per sweep and threaded through, so the SELECT and the per-row re-check/DELETE
    all use the same value).

    SELECT the stranded rows (the reaper is leader-elected → a single active
    sweeper, so a read-then-act is safe from double-claim), then recover each one
    best-effort: mark the execution ERROR if it isn't already terminal, then
    delete its ``pg_batch_dedup`` + ``pg_barrier_state`` rows. One execution
    failing (e.g. the API is unreachable, or a status read that can't be
    confirmed) is logged and skipped — its row is left for the next sweep to
    retry — so it never blocks the others. A non-empty sweep that recovers
    *nothing* is escalated as a systemic failure (API down / bad migration).

    ``conn`` runs in manual-commit mode; on any error we roll back before
    continuing/re-raising so the connection isn't left in an aborted-txn state.
    """
    if stuck_timeout_seconds is None:
        stuck_timeout_seconds = barrier_stuck_timeout_seconds()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT execution_id, organization_id, remaining "
                f"FROM {qualified('pg_barrier_state')} WHERE {_STRANDED_PREDICATE}",
                (stuck_timeout_seconds,),
            )
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise

    recovered: list[str] = []
    failed = 0  # genuine failures (exceptions) — NOT benign skips
    for execution_id, organization_id, remaining in rows:
        try:
            if _recover_one_barrier(
                conn,
                api_client,
                execution_id,
                organization_id,
                remaining,
                stuck_timeout_seconds,
            ):
                recovered.append(execution_id)
            # else: a benign skip (terminal / re-armed / no-status / no-org) —
            # logged per-row inside; not a failure, not retried-as-error.
        except Exception:
            # Keep the connection usable for the next row, and leave THIS barrier
            # row in place so the next sweep retries its recovery.
            failed += 1
            with contextlib.suppress(Exception):
                conn.rollback()
            logger.exception(
                "Reaper: failed to recover stranded barrier for execution %s — "
                "leaving the row for the next sweep to retry.",
                execution_id,
            )

    if rows:
        skipped = len(rows) - len(recovered) - failed
        summary = (
            f"recovered={len(recovered)}, failed={failed}, skipped={skipped} "
            f"of {len(rows)} expired barrier(s)"
        )
        if failed and not recovered:
            # Genuine failures and nothing got through → systemic (API down / bad
            # migration). Benign skips alone (terminal/re-armed/no-org) don't escalate.
            logger.error(
                "Reaper: %s — likely systemic (internal API down / bad migration).",
                summary,
            )
        elif failed:
            logger.warning("Reaper: %s — failures left for the next sweep.", summary)
        elif recovered:
            logger.info("Reaper: %s.", summary)
        # all-skipped (no recovered, no failed) is fully covered by per-row logs.
    return recovered


class PgReaper:
    """Leader-elected recovery loop. Only the lease holder runs recovery work."""

    def __init__(
        self,
        lease: LeaderLeaseLike,
        *,
        interval_seconds: float | None = None,
        sweep_interval_seconds: float | None = None,
        dedup_retention_seconds: int | None = None,
        stuck_timeout_seconds: int | None = None,
        sweep_conn: PgConnection | None = None,
        api_client: InternalAPIClient | None = None,
    ) -> None:
        self._lease = lease
        # Resolve + validate the barrier stuck-timeout ONCE, at construction, so a
        # garbled WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS crashes loudly at boot rather
        # than raising inside every tick (where run()'s generic "cycle failed" catch
        # would silently disable the whole recovery net, looking like a DB blip).
        self._stuck_timeout_seconds = (
            stuck_timeout_seconds
            if stuck_timeout_seconds is not None
            else barrier_stuck_timeout_seconds()
        )
        if self._stuck_timeout_seconds <= 0:
            raise ValueError("stuck_timeout_seconds must be positive")
        self._interval = (
            interval_seconds
            if interval_seconds is not None
            else reaper_interval_from_env()
        )
        # Load-bearing even though reaper_interval_from_env validates: an
        # explicitly-injected interval_seconds<=0 reaches here unvalidated.
        if self._interval <= 0:
            raise ValueError("interval_seconds must be positive")
        if self._interval >= lease.lease_seconds:
            # A leader that ticks slower than its lease window loses the lease
            # between renews → it would thrash leadership every cycle.
            raise ValueError(
                f"reaper interval {self._interval}s must be shorter than the "
                f"lease window {lease.lease_seconds}s, or the leader loses the "
                f"lease between renews"
            )
        # Retention-sweep cadence + dedup-orphan horizon (validated like interval:
        # an injected non-positive value reaches here unvalidated by the env parser).
        self._sweep_interval = (
            sweep_interval_seconds
            if sweep_interval_seconds is not None
            else reaper_sweep_interval_from_env()
        )
        if self._sweep_interval <= 0:
            raise ValueError("sweep_interval_seconds must be positive")
        self._dedup_retention = (
            dedup_retention_seconds
            if dedup_retention_seconds is not None
            else dedup_retention_from_env()
        )
        if self._dedup_retention <= 0:
            raise ValueError("dedup_retention_seconds must be positive")
        # None → "never swept", so the first leader tick sweeps immediately; set to
        # monotonic() each sweep so the cadence holds thereafter. (A None sentinel,
        # not 0.0, so the gate doesn't lean on monotonic() never returning ~0.)
        self._last_sweep_monotonic: float | None = None
        # Per-table consecutive-failure streak — surfaced in the failure log so a
        # persistently-failing sweep (and which table) is traceable in prod.
        self._sweep_fail_streak: dict[str, int] = {}
        self._sweep_conn = sweep_conn
        self._owns_sweep_conn = sweep_conn is None
        # Lazily built so the reaper can be constructed without env/HTTP set up
        # (tests inject a fake). Recovery marks execution ERROR via this client —
        # business state goes through the internal API, not direct DB.
        self._api_client = api_client
        self._running = False
        self._is_leader = False
        # Liveness heartbeat: monotonic timestamp of the last tick start. A
        # standby tick counts as progress too (the loop is alive), so this tracks
        # loop liveness, not leadership.
        self._last_tick_monotonic = time.monotonic()

    @property
    def is_leader(self) -> bool:
        """Whether this process currently holds leadership (last tick's view)."""
        return self._is_leader

    def seconds_since_last_tick(self) -> float:
        """Seconds since the last tick started — the liveness heartbeat age."""
        return time.monotonic() - self._last_tick_monotonic

    def is_tick_stale(self, stale_after_seconds: float) -> bool:
        """Whether the loop has gone quiet past ``stale_after_seconds``."""
        return self.seconds_since_last_tick() > stale_after_seconds

    def _get_sweep_conn(self) -> PgConnection:
        # Recreate only an OWNED missing/closed connection; an injected one is the
        # caller's and is never swapped (mirrors LeaderLease / PgQueueClient).
        if self._sweep_conn is None or (
            self._owns_sweep_conn and self._sweep_conn.closed
        ):
            self._sweep_conn = create_pg_connection(env_prefix="DB_")
        return self._sweep_conn

    def _get_api_client(self) -> InternalAPIClient:
        # Lazy import + build: keeps reaper construction free of HTTP/env (an
        # injected fake short-circuits this), and avoids a module-load import cycle.
        if self._api_client is None:
            from shared.api import InternalAPIClient

            self._api_client = InternalAPIClient()
        return self._api_client

    def _discard_owned_sweep_conn(self) -> None:
        # After a sweep error, drop an owned connection so the next tick
        # reconnects — covers a poisoned (aborted-txn) or dead-socket handle that
        # `.closed` alone wouldn't catch.
        if self._owns_sweep_conn and self._sweep_conn is not None:
            with contextlib.suppress(Exception):
                self._sweep_conn.close()
            self._sweep_conn = None
            logger.warning(
                "Reaper: discarded sweep connection after a failed sweep; "
                "reconnecting next cycle"
            )

    def tick(self) -> TickOutcome:
        """One cycle: maintain leadership, then sweep iff leader."""
        # Heartbeat at the START of the cycle: a tick that begins but then errors
        # still proves the loop is running (the error path is caught by run()).
        self._last_tick_monotonic = time.monotonic()
        if self._is_leader:
            try:
                still_leader = self._lease.renew()
            except Exception:
                # A raised renew == "leadership unknown": stop acting (honour the
                # lease's documented contract) before letting it propagate.
                self._is_leader = False
                raise
            if not still_leader:
                logger.warning(
                    "Reaper: lost leadership (lease taken over) — stepping down "
                    "to standby"
                )
                self._is_leader = False
        if not self._is_leader and self._lease.try_acquire():
            self._is_leader = True
            logger.info("Reaper: acquired leadership")
        if not self._is_leader:
            return TickOutcome(was_leader=False, reclaimed=0)
        try:
            reclaimed = len(
                recover_expired_barriers(
                    self._get_sweep_conn(),
                    self._get_api_client(),
                    self._stuck_timeout_seconds,
                )
            )
        except Exception:
            self._discard_owned_sweep_conn()
            raise
        # Orchestrator's second job: fire due PG-owned schedules (Beat
        # replacement). Ordered AFTER recovery so this cycle's recovery has
        # already completed before any scheduler error can propagate (the except
        # below still re-raises + discards the conn). Dark by default — fires
        # nothing until rows are pg_owned.
        try:
            dispatch_due_schedules(self._get_sweep_conn())
        except Exception:
            self._discard_owned_sweep_conn()
            raise
        # Orchestrator's third job: retention cleanup (cadence-gated, so it does
        # NOT run every tick). Last so a sweep error can't skip recovery/schedules.
        self._maybe_sweep()
        return TickOutcome(was_leader=True, reclaimed=reclaimed)

    def _maybe_sweep(self) -> None:
        """Run the retention sweep at most once per ``_sweep_interval``.

        Leader-only (called from :meth:`tick` after recovery + schedules). Deletes
        expired ``pg_task_result`` rows and orphaned ``pg_batch_dedup`` markers so
        neither table grows unbounded as the gate ramps. The two sweeps run
        **independently** (via :meth:`_run_sweep`): they cover different tables, so
        a persistent fault in one must not skip — and then cadence-gate out — the
        other. The cadence is advanced BEFORE sweeping so a failure waits one
        interval before retry rather than hammering the DB every tick.
        """
        now = time.monotonic()
        if (
            self._last_sweep_monotonic is not None
            and now - self._last_sweep_monotonic < self._sweep_interval
        ):
            return
        self._last_sweep_monotonic = now
        results = self._run_sweep("pg_task_result", sweep_expired_results)
        dedup = self._run_sweep(
            "pg_batch_dedup",
            lambda conn: sweep_orphan_dedup(conn, self._dedup_retention),
        )
        if results or dedup:
            logger.info(
                "Reaper: retention sweep deleted %s pg_task_result + "
                "%s pg_batch_dedup row(s)",
                results,
                dedup,
            )

    def _run_sweep(self, table: str, fn: Callable[[PgConnection], int]) -> int:
        """Run one retention sweep best-effort; return its row count (0 on failure).

        A cleanup failure is NOT propagated (it must not fail the tick) and must not
        starve the sibling sweep — it is logged at this boundary with the table name
        and a consecutive-failure streak (so a bloated ``pg_task_result`` /
        ``pg_batch_dedup`` in prod is traceable, distinct from the generic
        tick-failure log), and the owned conn is discarded so the next cycle
        reconnects. A clean run resets the streak.
        """
        try:
            count = fn(self._get_sweep_conn())
        except Exception:
            streak = self._sweep_fail_streak.get(table, 0) + 1
            self._sweep_fail_streak[table] = streak
            logger.exception(
                "Reaper: retention sweep of %s failed (%s consecutive) — will retry "
                "after the next sweep interval",
                table,
                streak,
            )
            self._discard_owned_sweep_conn()
            return 0
        self._sweep_fail_streak[table] = 0
        return count

    def run(self, *, install_signals: bool = True) -> None:
        """Lease-maintenance + recovery loop until stopped; releases on exit."""
        self._running = True
        if install_signals:
            self._install_signal_handlers()
        logger.info(
            "Reaper started (interval=%ss, lease=%ss, worker_id=%s)",
            self._interval,
            self._lease.lease_seconds,
            self._lease.worker_id,
        )
        try:
            while self._running:
                try:
                    self.tick()
                except Exception:
                    # A transient DB blip must not tear the loop down — the lease
                    # connection rolls back + discards a dead handle, and a failed
                    # sweep discards its owned connection, so log and keep cycling.
                    logger.exception("Reaper: cycle failed; continuing")
                time.sleep(self._interval)
        finally:
            # Hand the lease over promptly so a standby takes leadership without
            # waiting out the full lease window.
            if self._is_leader:
                try:
                    self._lease.release()
                except Exception:
                    logger.warning(
                        "Reaper: failed to release lease on shutdown; a standby "
                        "will take over after the lease window (~%ss) instead of "
                        "immediately",
                        self._lease.lease_seconds,
                        exc_info=True,
                    )
            # Close our owned sweep connection (an injected one is the caller's).
            # Harmless for the main() process — the OS reclaims it — but keeps the
            # class clean if it's ever embedded / driven from a test.
            if self._owns_sweep_conn and self._sweep_conn is not None:
                with contextlib.suppress(Exception):
                    self._sweep_conn.close()
                self._sweep_conn = None
            logger.info("Reaper stopped")

    def stop(self, *_: object) -> None:
        """Request a graceful stop after the current cycle."""
        self._running = False

    def _install_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self.stop)
            signal.signal(signal.SIGINT, self.stop)
        except ValueError:
            # signal.signal raises ValueError off the main thread — assert that
            # cause rather than mislabelling an unrelated ValueError.
            if threading.current_thread() is threading.main_thread():
                raise
            logger.warning(
                "Reaper: signal handlers not installed (non-main thread) — "
                "SIGTERM/SIGINT will not trigger graceful shutdown"
            )


# Default staleness window for the liveness probe. Comfortably above the default
# tick interval (_DEFAULT_REAPER_INTERVAL_SECONDS) so a single slow cycle (a long
# sweep / DB blip) doesn't flap the probe; the durable rationale is the headroom
# ratio — an operator tightening the interval should tighten this too.
_DEFAULT_HEALTH_STALE_SECONDS = 30.0


class ReaperLivenessServer(_BaseLivenessServer):
    """Reaper tick-loop liveness — a thin wrapper over the shared
    :class:`queue_backend.pg_queue.liveness.LivenessServer`, bound to the reaper's
    heartbeat (``seconds_since_last_tick``) and surfacing ``is_leader`` (which pod
    holds the lease — informational; the 200/503 verdict is purely the heartbeat,
    so a standby is healthy).
    """

    def __init__(self, reaper: PgReaper, *, port: int, stale_after: float) -> None:
        super().__init__(
            freshness_fn=reaper.seconds_since_last_tick,
            stale_after=stale_after,
            port=port,
            check_name="pg_reaper_tick",
            age_key="seconds_since_last_tick",
            extra_status_fn=lambda: {"is_leader": reaper.is_leader},
            thread_name="pg-reaper-liveness",
            log_label="pg-queue reaper",
        )


def _reaper_health_stale_from_env() -> float:
    raw = os.getenv("WORKER_PG_REAPER_HEALTH_STALE_SECONDS")
    if raw is None or raw == "":
        return _DEFAULT_HEALTH_STALE_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"WORKER_PG_REAPER_HEALTH_STALE_SECONDS={raw!r} is not a number."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"WORKER_PG_REAPER_HEALTH_STALE_SECONDS={value} must be positive."
        )
    return value


def _reaper_health_port_from_env() -> int | None:
    """Liveness port from ``WORKER_PG_REAPER_HEALTH_PORT`` (unset/empty → None,
    i.e. no server). Validates + names the var here so a garbled value (a common
    run-worker.sh shell-fallback mistake) fails with a clear message rather than a
    context-free ``int('abc')`` crash — and so an out-of-range value is rejected
    at parse time rather than escaping the bind catch as ``OverflowError`` inside
    ``start()``.
    """
    raw = os.getenv("WORKER_PG_REAPER_HEALTH_PORT")
    if raw is None or raw == "":
        return None
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid WORKER_PG_REAPER_HEALTH_PORT={raw!r}: {exc}") from exc
    if not (0 <= port <= 65535):
        raise ValueError(f"WORKER_PG_REAPER_HEALTH_PORT={port} out of range 0-65535")
    return port


def _maybe_start_health_server(
    reaper: PgReaper, *, port: int | None, stale_after: float
) -> ReaperLivenessServer | None:
    """Start the liveness server when ``port`` is not None; else ``None``.

    A bind failure degrades gracefully — the probe is auxiliary and must never
    stop the reaper from running; we log and continue probe-less.
    """
    if port is None:
        logger.info(
            "PG-queue reaper: WORKER_PG_REAPER_HEALTH_PORT unset — liveness "
            "server disabled"
        )
        return None
    server = ReaperLivenessServer(reaper, port=port, stale_after=stale_after)
    try:
        server.start()
    except OSError:
        logger.exception(
            "PG-queue reaper: liveness server could not bind :%s — continuing "
            "WITHOUT a probe",
            port,
        )
        return None
    logger.info(
        "PG-queue reaper: liveness server on :%s/health (stale after %ss)",
        server.bound_port,
        stale_after,
    )
    return server


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    lease = LeaderLease(default_worker_id())
    reaper = PgReaper(lease)
    health = _maybe_start_health_server(
        reaper,
        port=_reaper_health_port_from_env(),
        stale_after=_reaper_health_stale_from_env(),
    )
    try:
        reaper.run()
    finally:
        if health is not None:
            health.stop()


if __name__ == "__main__":
    main()
