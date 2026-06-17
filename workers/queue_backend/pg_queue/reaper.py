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
from typing import TYPE_CHECKING, NamedTuple, Protocol

from unstract.core.data_models import ExecutionStatus

from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id
from .liveness import LivenessServer as _BaseLivenessServer

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection
    from shared.api import InternalAPIClient

logger = logging.getLogger(__name__)

# Cadence: how often the leader renews + runs recovery. Enforced shorter than
# the lease window in PgReaper.__init__.
_DEFAULT_REAPER_INTERVAL_SECONDS = 5.0


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
    api_client.update_workflow_execution_status(
        execution_id=execution_id,
        status=ExecutionStatus.ERROR.value,
        error_message=f"[reaper-recovery] Execution stranded: {reason}.",
        organization_id=organization_id,
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

    Returns False without deleting when the org is unknown (can't call the
    org-scoped API → the row is LEFT, not erased, so the only recovery handle
    survives for ops) — this should never happen (enqueue always stamps the org).
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
    if status is not None and ExecutionStatus.is_completed(status):
        logger.warning(
            "Reaper: barrier for execution %s expired but the execution is already "
            "%s — cleaning up the orphaned row only (no status overwrite).",
            execution_id,
            status,
        )
    else:
        _mark_stranded_error(api_client, execution_id, organization_id, remaining)

    # Queue-infra cleanup (direct PG), re-guarded against a concurrent re-arm.
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM pg_barrier_state WHERE execution_id = %s "
            "AND expires_at < now()",
            (execution_id,),
        )
        deleted = cur.rowcount > 0
        if deleted:
            cur.execute(
                "DELETE FROM pg_batch_dedup WHERE execution_id = %s", (execution_id,)
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
    conn: PgConnection, api_client: InternalAPIClient
) -> list[str]:
    """Recover executions stranded by an expired barrier. Returns recovered ids.

    SELECT the expired rows (the reaper is leader-elected → a single active
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
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT execution_id, organization_id, remaining "
                "FROM pg_barrier_state WHERE expires_at < now()"
            )
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise

    recovered: list[str] = []
    for execution_id, organization_id, remaining in rows:
        try:
            if _recover_one_barrier(
                conn, api_client, execution_id, organization_id, remaining
            ):
                recovered.append(execution_id)
        except Exception:
            # Keep the connection usable for the next row, and leave THIS barrier
            # row in place so the next sweep retries its recovery.
            with contextlib.suppress(Exception):
                conn.rollback()
            logger.exception(
                "Reaper: failed to recover stranded barrier for execution %s — "
                "leaving the row for the next sweep to retry.",
                execution_id,
            )

    if rows:
        unrecovered = len(rows) - len(recovered)
        if recovered and not unrecovered:
            logger.info("Reaper: recovered %d stranded execution(s).", len(recovered))
        elif recovered:
            logger.warning(
                "Reaper: recovered %d/%d stranded execution(s); %d left for retry.",
                len(recovered),
                len(rows),
                unrecovered,
            )
        else:
            logger.error(
                "Reaper: recovered NONE of %d expired barrier(s) this cycle — "
                "likely systemic (internal API down / bad migration / missing org).",
                len(rows),
            )
    return recovered


class PgReaper:
    """Leader-elected recovery loop. Only the lease holder runs recovery work."""

    def __init__(
        self,
        lease: LeaderLeaseLike,
        *,
        interval_seconds: float | None = None,
        sweep_conn: PgConnection | None = None,
        api_client: InternalAPIClient | None = None,
    ) -> None:
        self._lease = lease
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
                recover_expired_barriers(self._get_sweep_conn(), self._get_api_client())
            )
        except Exception:
            self._discard_owned_sweep_conn()
            raise
        return TickOutcome(was_leader=True, reclaimed=reclaimed)

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
