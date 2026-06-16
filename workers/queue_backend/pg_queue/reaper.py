"""Reaper — the leader-elected recovery process for the PG queue.

A singleton, guarded by :class:`LeaderLease` over ``pg_orchestrator_lock``: only
the elected leader runs recovery work each cycle (several reapers would contend
and double-act). This slice ships the process *harness* (lease-maintenance loop
+ graceful shutdown) plus ONE recovery job — the **barrier-orphan sweep**.

**Barrier-orphan sweep.** Reclaims ``pg_barrier_state`` rows past their
``expires_at`` — a barrier whose header tasks never all completed (the documented
:class:`PgBarrier` backstop). It ``DELETE``s the orphaned row; by PgBarrier's
existing semantics a late in-flight decrement then finds no row and abandons (no
spurious callback). The owning execution is logged loudly. Marking that
execution *terminal* (ERROR) is recovery that needs the backend and the
pipeline's PG shape — that's 9e, not here; this slice is the storage/orphan
backstop only.

**Deferred to 9e.** Pipeline recovery (counter reconstruction from
``WorkflowFileExecution``, per-stage re-enqueue of stuck file executions) is
defined against the coupled pipeline running on PG, which doesn't exist yet — so
it lands with 9e, against a real PG pipeline it can be tested on.

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

from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id
from .liveness import LivenessServer as _BaseLivenessServer

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

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


def sweep_expired_barriers(conn: PgConnection) -> list[str]:
    """Reclaim ``pg_barrier_state`` rows past ``expires_at``. Returns their ids.

    A single atomic ``DELETE … RETURNING``: concurrent sweepers would each
    reclaim a disjoint subset (``RETURNING`` reports only the rows *this*
    statement deleted), so it stays correct even if leadership gating ever fails —
    in practice only the leader calls it. Each reclaimed barrier is logged at
    WARNING: an orphaned barrier means an execution's header tasks never all
    completed, worth surfacing even though deleting the row is the right backstop.

    ``conn`` runs in manual-commit mode, so on any error we roll back before
    re-raising — otherwise the connection is left in an aborted-transaction state
    and every later statement on it fails with ``InFailedSqlTransaction``.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM pg_barrier_state WHERE expires_at < now() "
                "RETURNING execution_id"
            )
            reclaimed = [row[0] for row in cur.fetchall()]
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise
    for execution_id in reclaimed:
        logger.warning(
            "Reaper: reclaimed orphaned barrier for execution %s — header tasks "
            "never all completed before expiry; barrier deleted (no callback "
            "fired). Execution terminal-status recovery is 9e's job.",
            execution_id,
        )
    return reclaimed


class PgReaper:
    """Leader-elected recovery loop. Only the lease holder runs recovery work."""

    def __init__(
        self,
        lease: LeaderLeaseLike,
        *,
        interval_seconds: float | None = None,
        sweep_conn: PgConnection | None = None,
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
            reclaimed = len(sweep_expired_barriers(self._get_sweep_conn()))
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
