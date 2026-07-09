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

**Orchestration-claim GC + recovery (UN-3679).** The orchestration idempotency
claim (``pg_orchestration_claim``) is taken BEFORE the barrier is armed, so a
crash in the claim→arm window leaves a claim with no barrier row — invisible to
the barrier sweep above — and a successful claim's tombstone has no natural GC.
The retention sweep's :func:`sweep_orphan_claims` closes both: for a claim with no
matching barrier row older than the stuck-timeout, it GC's a terminal execution's
tombstone and marks a non-terminal (crash-window) execution ERROR (org-scoped,
same best-effort per-row posture).

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
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Protocol, TypeVar

from unstract.core.data_models import ExecutionStatus, QueueMessageState

from ..barrier import barrier_stuck_timeout_seconds
from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id
from .liveness import LivenessServer as _BaseLivenessServer
from .metrics import ReaperMetrics
from .pg_scheduler import dispatch_due_schedules
from .recovery import mark_execution_error
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

# Orphan-claim recovery outcomes (a closed domain — a typo in a returned literal
# or a caller comparison would otherwise silently fall through to the skip path
# and mis-count the sweep). Shared by _recover_one_claim (producer) and
# sweep_orphan_claims (consumer).
_CLAIM_RECOVERED: Final = "recovered"  # execution marked ERROR (crash-window)
_CLAIM_GC: Final = "gc"  # terminal execution's tombstone deleted
_ClaimOutcome = Literal["recovered", "gc"]


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


def rearm_expired_claims(conn: PgConnection) -> int:
    """Re-arm crashed-worker queue messages: ``claimed`` + expired vt -> ``ready``.

    UN-3445 crash-redelivery. Under the state-machine claim (``WHERE state='ready'``,
    client._dequeue_sql), an in-flight row is ``state='claimed'`` and invisible to
    claimants; its ``vt`` is the renewable lease (UN-3695). If the owning worker
    dies its renewal stops, ``vt`` lapses, and this sweep flips the row back to
    ``ready`` so the next consumer re-claims it — the explicit, indexed equivalent
    of the old design's implicit ``vt <= now()`` self-heal in the claim itself.

    A LIVE worker keeps ``vt`` in the future (renews every ~lease/3), so the
    ``vt <= now()`` predicate never matches it — only genuinely-dead-worker rows
    are re-armed. Bounded and cheap: the ``pg_queue_message_claimed_idx`` partial
    index (state='claimed' only, ~concurrency rows) scopes the scan; redelivered
    work is absorbed by the unchanged idempotency stack (claim_batch /
    FileHistory / _callback_already_ran), exactly as an old-design vt-expiry re-run
    was. Idempotent; rolls back on error. Runs every **leader** tick (redelivery
    cadence — a standby returns before this), not the retention sweep; see
    PgReaper.tick for the ordering/placement.
    """
    ready, claimed = QueueMessageState.READY.value, QueueMessageState.CLAIMED.value
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_queue_message')} "
                f"SET state = '{ready}' WHERE state = '{claimed}' AND vt <= now()"
            )
            rearmed = cur.rowcount
        conn.commit()
        return rearmed
    except Exception:
        _rollback_after_sweep_failure(conn, "pg_queue_message")
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
    metrics: ReaperMetrics | None = None,
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

    if metrics is not None:
        metrics.barrier_recovered.inc(len(recovered))
        metrics.barrier_recovery_failures.inc(failed)
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


def _orphan_claim_where(claim_alias: str) -> str:
    """WHERE clause selecting orphan ``pg_orchestration_claim`` rows.

    A claim is an orphan when it has NO matching ``pg_barrier_state`` row (never
    armed — the crash-window strand — OR armed-then-finalised — a completed/failed
    tombstone) AND is older than the stuck-timeout (so a just-claimed live
    orchestration that hasn't armed its barrier yet is left alone). Binds one
    ``%s`` — the stuck-timeout seconds. Defined once so the sweep SELECT, the
    pre-mark re-check, and the cleanup DELETE can't drift (like
    :data:`_STRANDED_PREDICATE` for barriers).
    """
    return (
        f"{claim_alias}.claimed_at < now() - make_interval(secs => %s) "
        f"AND NOT EXISTS (SELECT 1 FROM {qualified('pg_barrier_state')} b "
        f"WHERE b.execution_id = {claim_alias}.execution_id)"
    )


def _claim_still_orphan(
    conn: PgConnection, execution_id: str, stuck_timeout_seconds: int
) -> bool:
    """True iff the claim is STILL an orphan (no barrier, still old) right now.

    Re-checked immediately before the ERROR mark: between the sweep's SELECT and
    the mark, a slow-but-live orchestration could finally arm its barrier (making
    it the reaper's barrier-recovery concern, not a crash-window strand), or the
    claim could have been released and re-claimed with a fresh ``claimed_at``. In
    either case its live run must NOT be marked ERROR.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM {qualified('pg_orchestration_claim')} AS c "
            f"WHERE c.execution_id = %s AND {_orphan_claim_where('c')}",
            (execution_id, stuck_timeout_seconds),
        )
        found = cur.fetchone() is not None
    conn.commit()
    return found


def _delete_orphan_claim(
    conn: PgConnection, execution_id: str, stuck_timeout_seconds: int
) -> int:
    """Delete a claim, re-guarded on still-orphan-and-old so a concurrent re-claim
    (release + redelivery inserting a fresh ``claimed_at``) or a freshly-armed
    barrier is never torn out from under a live run. Returns the number of rows
    deleted (0 when the WHERE no longer matched — a concurrent re-claim / barrier
    arm won the race, so the caller must not count or log a removal).
    """
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {qualified('pg_orchestration_claim')} AS c "
            f"WHERE c.execution_id = %s AND {_orphan_claim_where('c')}",
            (execution_id, stuck_timeout_seconds),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted


def _recover_one_claim(
    conn: PgConnection,
    api_client: InternalAPIClient,
    execution_id: str,
    organization_id: str,
    stuck_timeout_seconds: int,
) -> _ClaimOutcome | None:
    """Recover or GC one orphan claim; return :data:`_CLAIM_RECOVERED` (execution
    marked ERROR — a crash-window recovery), :data:`_CLAIM_GC` (a terminal
    execution's tombstone deleted), or ``None`` (a benign skip). The claim row is
    deleted on GC and on a confirmed recovery; it is LEFT for the next sweep on any
    unconfirmed step (no org, unreadable status, re-armed during recovery, an
    unconfirmed mark, or a 0-row delete lost to a concurrent re-claim) so nothing
    is lost and nothing is mis-counted.

    A terminal execution (per :meth:`ExecutionStatus.is_completed` — COMPLETED /
    STOPPED / ERROR, the single source of truth) → GC the tombstone. A non-terminal
    one is the claim→arm crash window (the orchestrator committed the claim then
    died before arming the barrier; the reaper's barrier sweep can't see it because
    there is no barrier row) → mark it ERROR so it reaches a terminal state instead
    of stranding EXECUTING forever, then delete the claim.
    """
    if not organization_id:
        logger.error(
            "Reaper: orphan orchestration claim for execution %s has NO "
            "organization_id — cannot call the org-scoped status/mark API; leaving "
            "the row. A claim was written without an org — investigate.",
            execution_id,
        )
        return None

    status = _execution_status(api_client, execution_id, organization_id)
    if status is None:
        logger.warning(
            "Reaper: status read for orphan-claim execution %s returned no status "
            "— leaving the claim for the next sweep.",
            execution_id,
        )
        return None

    if ExecutionStatus.is_completed(status):
        # Terminal: the claim is a tombstone with no live run behind it — GC it.
        # (A terminal execution's orchestration message was acked on completion or
        # on the first skip-redelivery, so there is nothing left to re-orchestrate
        # once the row is gone.) A 0-row delete means a concurrent release+re-claim
        # replaced the row in the window since the SELECT — leave the fresh one.
        if not _delete_orphan_claim(conn, execution_id, stuck_timeout_seconds):
            logger.warning(
                "Reaper: orphan-claim execution %s was re-claimed during GC — "
                "leaving the fresh claim (its new run owns it).",
                execution_id,
            )
            return None
        logger.info(
            "Reaper: GC'd orphan orchestration claim for terminal execution %s (%s).",
            execution_id,
            status,
        )
        return _CLAIM_GC

    # Non-terminal → crash-window strand. Re-check it's STILL an orphan right before
    # marking, so a slow orchestration that just armed its barrier (or a fresh
    # re-claim) isn't flagged ERROR while live.
    if not _claim_still_orphan(conn, execution_id, stuck_timeout_seconds):
        logger.warning(
            "Reaper: orphan-claim execution %s armed a barrier or was re-claimed "
            "during recovery — leaving it (its live run owns the claim).",
            execution_id,
        )
        return None

    if not mark_execution_error(
        api_client,
        execution_id,
        organization_id,
        error_message=(
            "[reaper-recovery] Execution stranded: the orchestration claimed its "
            "slot but the barrier was never armed (crash before dispatch)."
        ),
    ):
        # Unconfirmed mark — do NOT delete the claim (it is the only recovery
        # handle); leave it for the next sweep to retry.
        return None

    # Safe to delete the tombstone now that the execution is terminal: the same
    # ack argument as the GC branch holds (the message was acked on the first
    # skip-redelivery). The re-guarded DELETE additionally protects the rare race
    # where the claim was re-armed between the mark and here — a 0-row delete then
    # leaves the fresh claim. (Residual: if the ENTIRE worker fleet were down
    # longer than the stuck-timeout so no consumer ever hit the skip-and-ack path,
    # the message could still be un-acked and a later redelivery would re-win the
    # claim — an accepted tradeoff for a catastrophic multi-hour outage.)
    if not _delete_orphan_claim(conn, execution_id, stuck_timeout_seconds):
        logger.warning(
            "Reaper: orphan-claim execution %s was re-claimed between the ERROR "
            "mark and the delete — leaving the fresh claim.",
            execution_id,
        )
        return None
    return _CLAIM_RECOVERED


def sweep_orphan_claims(
    conn: PgConnection,
    api_client: InternalAPIClient,
    stuck_timeout_seconds: int | None = None,
    metrics: ReaperMetrics | None = None,
) -> int:
    """GC / recover orphaned ``pg_orchestration_claim`` rows (UN-3679). Returns the
    number of claim rows removed (terminal-tombstone GCs + crash-window recoveries).

    The orchestration claim is taken BEFORE the barrier is armed, so — unlike
    ``pg_batch_dedup``, whose barrier always exists — a crash in the claim→arm
    window leaves a claim with no barrier row that the barrier sweep can't see, and
    a successful claim's tombstone has no natural GC. This sweep closes both: for
    each orphan claim (no barrier row, older than the stuck-timeout; see
    :func:`_orphan_claim_where`) it GC's a terminal execution's tombstone and marks
    a non-terminal (crash-window) execution ERROR. One claim failing (API down,
    unreadable status) is logged and skipped — its row is left for the next sweep —
    so it never blocks the others.

    ``conn`` runs in manual-commit mode; on any error we roll back before
    continuing / re-raising so the connection isn't left in an aborted-txn state.
    """
    if stuck_timeout_seconds is None:
        stuck_timeout_seconds = barrier_stuck_timeout_seconds()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT c.execution_id, c.organization_id "
                f"FROM {qualified('pg_orchestration_claim')} AS c "
                f"WHERE {_orphan_claim_where('c')}",
                (stuck_timeout_seconds,),
            )
            rows = cur.fetchall()
        conn.commit()
    except Exception:
        _rollback_after_sweep_failure(conn, "pg_orchestration_claim")
        raise

    gc_count = 0
    recovered = 0
    failed = 0  # genuine per-row failures (exceptions) — NOT benign skips
    for execution_id, organization_id in rows:
        try:
            outcome = _recover_one_claim(
                conn, api_client, execution_id, organization_id, stuck_timeout_seconds
            )
            if outcome == _CLAIM_RECOVERED:
                recovered += 1
            elif outcome == _CLAIM_GC:
                gc_count += 1
            # None = a benign skip (no org / no status / re-armed / unconfirmed
            # mark) — logged per-row inside; the row is left for the next sweep.
        except Exception:
            failed += 1
            with contextlib.suppress(Exception):
                conn.rollback()
            logger.exception(
                "Reaper: failed to recover/GC orphan orchestration claim for "
                "execution %s — leaving the row for the next sweep.",
                execution_id,
            )

    removed = gc_count + recovered
    if metrics is not None:
        metrics.claim_recovered.inc(recovered)
        metrics.claim_gc.inc(gc_count)
        metrics.claim_recovery_failures.inc(failed)
    if removed:
        logger.info(
            "Reaper: orphan-claim sweep removed %d of %d claim(s) — %d GC'd "
            "(terminal), %d recovered (marked ERROR).",
            removed,
            len(rows),
            gc_count,
            recovered,
        )
    # A non-empty sweep that accomplished NOTHING because every row raised is
    # systemic (internal API down / bad migration). Raise so _run_sweep records it
    # on the consecutive-failure streak — a clean return would reset that streak
    # and hide "the crash-window recovery net is completely down". Mirrors
    # recover_expired_barriers' failed-and-nothing-recovered escalation. A PARTIAL
    # failure (some rows swept) is only a warning — the net is working.
    if failed and not removed:
        raise RuntimeError(
            f"orphan-claim sweep: all {failed} row(s) failed and nothing was "
            f"swept — likely systemic (internal API down / bad migration)"
        )
    if failed:
        logger.warning(
            "Reaper: orphan-claim sweep — %d of %d row(s) failed (left for the next "
            "sweep); %d swept.",
            failed,
            len(rows),
            removed,
        )
    return removed


# Queue-gauge snapshot cadence. Deliberately a module constant, not an env knob:
# it only bounds metrics staleness (the tick already runs every
# _DEFAULT_REAPER_INTERVAL_SECONDS by default), and the
# snapshot is two cheap aggregate reads.
_GAUGE_REFRESH_INTERVAL_SECONDS: Final = 60.0


def refresh_queue_gauges(
    conn: PgConnection, metrics: ReaperMetrics, stuck_timeout_seconds: int
) -> None:
    """Take one queue-wide snapshot into ``metrics`` (leader-only caller).

    Two aggregate reads: per-queue depth + oldest-message age over
    ``pg_queue_message`` (all rows — ready and in-flight — since a backlog is a
    backlog either way), and live/stranded counts over ``pg_barrier_state``
    (live = ``remaining > 0`` in-flight fan-outs; stranded = what the next
    recovery pass would pick up — same predicate, unfiltered by ``remaining``,
    so it includes ``remaining==0`` delete-failure lingerers).

    ``conn`` runs in manual-commit mode; on any error we roll back before
    re-raising so the connection isn't left in an aborted-txn state (the caller
    counts the failure and discards an owned connection).
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT queue_name, count(*), "
                "COALESCE(EXTRACT(EPOCH FROM now() - min(enqueued_at)), 0) "
                f"FROM {qualified('pg_queue_message')} GROUP BY queue_name"
            )
            depth_rows = cur.fetchall()
            cur.execute(
                "SELECT count(*) FILTER (WHERE remaining > 0), "
                f"count(*) FILTER (WHERE {_STRANDED_PREDICATE}) "
                f"FROM {qualified('pg_barrier_state')}",
                (stuck_timeout_seconds,),
            )
            barriers_live, barriers_stranded = cur.fetchone()
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise
    metrics.set_queue_snapshot(
        depths={
            queue: (int(depth), float(oldest_age))
            for queue, depth, oldest_age in depth_rows
        },
        barriers_live=int(barriers_live),
        barriers_stranded=int(barriers_stranded),
    )


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
        # Queue-wide metrics snapshot cadence (same None-sentinel pattern as the
        # sweep gate: first leader tick refreshes immediately).
        self._last_gauge_refresh_monotonic: float | None = None
        self._metrics = ReaperMetrics(
            heartbeat_fn=self.seconds_since_last_tick,
            is_leader_fn=lambda: self._is_leader,
        )

    @property
    def metrics(self) -> ReaperMetrics:
        """This process's metrics exporter (served at ``/metrics``)."""
        return self._metrics

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
                self._step_down_metrics()
                raise
            if not still_leader:
                logger.warning(
                    "Reaper: lost leadership (lease taken over) — stepping down "
                    "to standby"
                )
                self._is_leader = False
                self._step_down_metrics()
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
                    metrics=self._metrics,
                )
            )
        except Exception:
            self._discard_owned_sweep_conn()
            raise
        # Crash-redelivery (UN-3445): re-arm queue messages whose owning worker
        # died (state='claimed', vt expired) back to 'ready'. Runs EVERY leader tick
        # (the redelivery cadence), like barrier recovery above and NOT the
        # retention sweep — a crashed batch must not wait the 5-min sweep interval.
        # Cheap (partial claimed-index scoped). On failure it increments a DEDICATED
        # counter (so a persistent redelivery outage is distinguishable from a
        # barrier/scheduler fault) then re-raises + discards the conn — SAME
        # semantics as barrier recovery above (recovery work is critical, not
        # swallow-and-continue like the retention sweeps). A re-arm fault therefore
        # also defers this tick's schedule dispatch; both recover next tick.
        try:
            rearmed = rearm_expired_claims(self._get_sweep_conn())
            if rearmed:
                self._metrics.queue_rearmed.inc(rearmed)
                logger.info(
                    "Reaper: re-armed %s expired in-flight queue message(s) "
                    "to 'ready' (crashed-worker redelivery)",
                    rearmed,
                )
        except Exception:
            self._metrics.queue_rearm_failures.inc()
            logger.exception(
                "Reaper: re-arm sweep failed — crashed-worker queue redelivery "
                "is stalled this tick (see pg_reaper_queue_rearm_failures_total)"
            )
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
        # Queue-wide metrics snapshot (cadence-gated, best-effort — a metrics
        # failure must never fail the tick). After all real work.
        self._maybe_refresh_gauges()
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
        # Orphan orchestration-claim GC + crash-window recovery (UN-3679). Runs
        # here (cadence-gated) rather than every tick: orphan claims are rare and
        # already older than the stuck-timeout, and this does a per-row status API
        # read, so the 5-min cadence keeps it off the hot path. Independent of the
        # other sweeps (its own _run_sweep) so a fault in one can't skip it.
        claims = self._run_sweep(
            "pg_orchestration_claim",
            lambda conn: sweep_orphan_claims(
                conn,
                self._get_api_client(),
                self._stuck_timeout_seconds,
                metrics=self._metrics,
            ),
        )
        if results or dedup or claims:
            logger.info(
                "Reaper: retention sweep deleted %s pg_task_result + "
                "%s pg_batch_dedup + %s pg_orchestration_claim row(s)",
                results,
                dedup,
                claims,
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
            self._metrics.sweep_failures.labels(table=table).inc()
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

    def _step_down_metrics(self) -> None:
        """On losing leadership: drop the queue snapshot AND reset the refresh
        cadence. Resetting the cadence is load-bearing — without it, a lease
        flap that re-acquires within the refresh interval would gate the next
        refresh out, leaving a re-elected leader exporting the just-cleared
        (false "empty queue") snapshot for up to a full interval.
        """
        self._metrics.clear_queue_snapshot()
        self._last_gauge_refresh_monotonic = None

    def _maybe_refresh_gauges(self) -> None:
        """Refresh the queue-wide metrics snapshot at most once per
        :data:`_GAUGE_REFRESH_INTERVAL_SECONDS` (leader-only, called from
        :meth:`tick`). Best-effort: metrics must never fail the tick, so a
        failure is counted + logged and the snapshot simply goes stale
        (``pg_queue_gauges_age_seconds`` exposes exactly that). The cadence is
        advanced BEFORE the read so a persistent failure retries once per
        interval rather than every tick — same pattern as :meth:`_maybe_sweep`.
        """
        now = time.monotonic()
        if (
            self._last_gauge_refresh_monotonic is not None
            and now - self._last_gauge_refresh_monotonic < _GAUGE_REFRESH_INTERVAL_SECONDS
        ):
            return
        self._last_gauge_refresh_monotonic = now
        try:
            refresh_queue_gauges(
                self._get_sweep_conn(), self._metrics, self._stuck_timeout_seconds
            )
        except Exception:
            self._metrics.gauge_refresh_failures.inc()
            logger.warning(
                "Reaper: queue-gauge snapshot refresh failed — metrics go stale "
                "until the next interval; the queue itself is unaffected",
                exc_info=True,
            )
            self._discard_owned_sweep_conn()

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
                    # Counted: the heartbeat is stamped at tick START, so /health
                    # stays 200 through every-tick failures (schema/grant faults) —
                    # this counter is the only machine-readable signal for that.
                    self._metrics.tick_failures.inc()
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
            metrics_fn=reaper.metrics.render,
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
