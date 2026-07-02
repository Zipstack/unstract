"""PG fan-in barrier — Postgres substrate for the ``Barrier`` Protocol.

Third ``WORKER_BARRIER_BACKEND`` option (``pg``) alongside ``chord`` and
``redis``. Mirrors :class:`~queue_backend.redis_barrier.RedisDecrBarrier`
exactly — same ``enqueue`` signature, same ``BarrierHandle | None`` contract,
same fairness plumbing, same Celery-dispatched header tasks with
``.link``/``.link_error`` — but moves the **aggregation** ("wait for N tasks,
then fire the callback with their results") from a Redis ``DECR`` counter to a
Postgres row. Selected at runtime by ``queue_backend.get_barrier``; default
stays ``chord``.

**Why a Postgres substrate.** It lets an execution coordinate in the *same*
Postgres that holds the PG queue — no Redis (or RabbitMQ chord backend) needed
for the fan-in. The transport for the header tasks themselves is unchanged
(still Celery); only the coordination moves.

**Wire model.**

1. ``enqueue``: UPSERT one ``pg_barrier_state`` row (``remaining = N``,
   ``results = []``, ``expires_at = now() + ttl``, ``last_progress_at = now()``)
   — the UPSERT clears any stale
   state from a prior run reusing the same ``execution_id``. Each header task is
   dispatched with
   ``.link(barrier_pg_decr_and_check)`` (success) and
   ``.link_error(barrier_pg_abort)`` (failure).
2. Per-task success: ``barrier_pg_decr_and_check`` runs ONE atomic statement —
   ``UPDATE … SET remaining = remaining - 1, results = results ||
   jsonb_build_array(result) … RETURNING remaining, results``. The row lock
   serialises concurrent decrements, so exactly one task observes ``remaining =
   0``; that task dispatches the callback with the aggregated results, then
   deletes the row. (No Lua — a single ``UPDATE … RETURNING`` is atomic in
   Postgres. The guarantee relies on each decrement committing in its own
   transaction — do NOT batch decrements into a shared transaction, or the row
   lock would hold and the serialisation that makes exactly one see 0 breaks.)
3. Per-task failure: ``barrier_pg_abort`` runs as a ``link_error``. It tears the
   barrier down with ONE atomic statement (``DELETE … RETURNING`` in a single
   transaction): the row's existence is the dedup token, so N concurrent
   failures collapse to a single cleanup, and a crash mid-abort rolls back
   (leaving the row for a sibling to retry) — there is no claimed-but-not-deleted
   window. Mirrors chord's default error semantic (callback not invoked on
   header failure).
4. Stuck bound: ``last_progress_at`` is re-stamped to ``now()`` on enqueue AND on
   every decrement, tracking when a batch last completed. The
   :mod:`~queue_backend.pg_queue.reaper` marks the stranded execution ERROR once
   ``last_progress_at`` is older than ``WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS``
   (default 2.5h — in the same band as Celery's per-task
   ``FILE_PROCESSING_TASK_TIME_LIMIT``, which ships 2h–3h) — a
   per-PROGRESS window, invariant to how many batches run in parallel
   (``MAX_PARALLEL_FILE_BATCHES`` is dynamic per-org), so it never false-fails a
   legitimately long multi-batch run. ``expires_at`` (fixed at enqueue,
   ``WORKER_BARRIER_KEY_TTL_SECONDS``, default 6h) is the absolute last-resort cap
   the reaper also sweeps.

**Failure-masking guards.** The callback can only fire when ``remaining`` hits
exactly 0, which requires ALL N header tasks to have decremented — i.e. all
succeeded. A failed task runs the abort (which deletes the row) instead of a
decrement, so the count never reaches 0 and a late in-flight decrement finds no
row → abandons. A decrement that drives ``remaining`` negative (expiry/replay)
also cleans up without firing. The callback is dispatched BEFORE the row is
deleted, so a callback ``apply_async`` failure leaves the row (and its expiry)
in place rather than stranding the execution; the post-dispatch delete is
best-effort (logged, not raised) since the callback has already fired.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NamedTuple

import psycopg2
import psycopg2.extensions

from unstract.core.data_models import (
    DEFAULT_WORKFLOW_TRANSPORT,
    WorkflowTransport,
    is_pg_transport,
)

from .barrier import (
    BarrierContext,
    CallbackDescriptor,
    barrier_ttl_seconds,
    callback_recovery_identity,
)
from .decorator import worker_task
from .fairness import (
    DEFAULT_PRIORITY,
    FAIRNESS_HEADER_NAME,
    FairnessKey,
    WorkloadType,
)
from .handle import BarrierHandle
from .pg_queue.connection import CONN_DEAD_ERRORS as _CONN_DEAD_ERRORS
from .pg_queue.connection import create_pg_connection
from .pg_queue.schema import qualified

if TYPE_CHECKING:
    from celery.canvas import Signature
    from psycopg2.extensions import connection as PgConnection
    from psycopg2.extensions import cursor as PgCursor

logger = logging.getLogger(__name__)


# ``_CONN_DEAD_ERRORS`` (the "is this a connection death?" test, used by
# ``_recover_after_error``/``_cursor`` to discard a stale handle and by the
# enqueue/decrement retries to decide eligibility) is imported from
# ``pg_queue.connection`` so the dispatch/result/barrier sites can't drift.


# Thread-local owned connection (prefork → one per child; thread-local keeps it
# correct under -P threads too, since a libpq connection is not concurrency-safe
# across threads). Self-recovers a dropped socket / PgBouncer recycle — same
# posture as queue_backend.dispatch / PgQueueClient.
_local = threading.local()


def _get_conn() -> PgConnection:
    conn = getattr(_local, "conn", None)
    if conn is None or conn.closed:
        conn = create_pg_connection(env_prefix="DB_")
        _local.conn = conn
    return conn


def _recover_after_error(conn: PgConnection, exc: BaseException) -> bool:
    """Roll back ``conn``; if it is dead, discard the thread-local handle so the
    next :func:`_get_conn` reconnects. Returns whether the connection was judged
    dead (a failed rollback proves it dead regardless of the original error).

    Factored out so ``_cursor`` and the decrement phase-split (which can't use
    ``_cursor`` because it must distinguish execute-phase from commit-phase
    failures) share one definition of "recover a connection after an error".
    """
    conn_dead = isinstance(exc, _CONN_DEAD_ERRORS)
    try:
        conn.rollback()
    except Exception:
        # A failed rollback proves the connection is unusable regardless of the
        # original error's subclass — treat it as dead. Surface why (instead of
        # swallowing it): this also reclassifies a non-conn error (e.g. DataError)
        # whose rollback fails into the dead/retry path, so the trail must show it
        # was the rollback, not the original error, that condemned the connection.
        logger.warning(
            "PgBarrier: rollback during error recovery failed (original error %s) "
            "— treating the connection as dead and discarding it.",
            type(exc).__name__,
            exc_info=True,
        )
        conn_dead = True
    if conn_dead or conn.closed:
        with contextlib.suppress(Exception):
            conn.close()
        _local.conn = None
    return conn_dead


@contextlib.contextmanager
def _cursor() -> Iterator[Any]:
    """Yield a cursor; commit on success, roll back + recover on error."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception as exc:
        _recover_after_error(conn, exc)
        raise


# One retry for an IDEMPOTENT, pre-dispatch barrier write. The thread-local
# connection is cached across barrier ops, so it can be reaped server-side
# (PgBouncer server_idle_timeout / DB failover) while sitting idle BETWEEN ops —
# and ``_get_conn`` can't tell, since ``conn.closed`` is a client-side flag only.
# The first statement after the idle gap then fails; ``_cursor`` discards the
# dead conn, so a single retry runs against a freshly reconnected one. This turns
# a transient blip (which previously aborted the whole execution at barrier
# enqueue) into a self-heal. Kept a literal (not env-driven) so the idempotency
# bound can't be weakened operationally.
_BARRIER_WRITE_ATTEMPTS: Final = 2  # total attempts: 1 initial + 1 retry
# Small fixed pause before the retry. The idle-reap case reconnects instantly
# regardless; this only widens the self-heal window for a brief DB failover, and
# avoids immediately re-hammering a struggling server on the rarer server-side
# errors the broad psycopg2.OperationalError catch also covers.
_BARRIER_RETRY_BACKOFF_SECONDS: Final = 0.5

# One retry for the NON-idempotent barrier DECREMENT — but only on an
# execute-phase failure on a reused connection (see :func:`_apply_decrement`),
# never on commit (ambiguous). Same one-shot bound as the idempotent write.
_BARRIER_DECREMENT_ATTEMPTS: Final = 2  # total attempts: 1 initial + 1 retry


def _run_idempotent_pre_dispatch_write(
    operation: Callable[[PgCursor], None], *, what: str
) -> None:
    """Run ``operation(cur)`` in a committed cursor, retrying ONCE if the cached
    connection was dead.

    The name spells out the contract because it can't be type-enforced: only call
    with an **idempotent** statement run **before** any task dispatch — the
    barrier UPSERT (``ON CONFLICT … DO UPDATE`` → same row, ``remaining``/
    ``results`` reset identically; timestamps refresh, harmlessly) + the
    per-execution dedup reset (``DELETE WHERE execution_id``). Re-running them
    after an ambiguous commit is a no-op, so a retry can neither duplicate a row
    nor double-dispatch work (no header has been enqueued yet). The ``-> None``
    op signature also blocks passing a ``RETURNING``-reading op by construction.

    Deliberately NOT used for the barrier **decrement** (``remaining =
    remaining - 1``): it is not idempotent — a re-applied decrement can fire the
    callback **prematurely with incomplete results**, or skip past 0 and
    **strand the barrier** to expiry — so it stays on the plain :func:`_cursor`
    (recover-but-don't-retry). Same for ``claim_batch``, whose ``RETURNING``
    answer flips on a retry.
    """
    for attempt in range(1, _BARRIER_WRITE_ATTEMPTS + 1):
        try:
            with _cursor() as cur:
                operation(cur)
            return
        except _CONN_DEAD_ERRORS as exc:
            # _cursor already dropped the dead thread-local conn → the next
            # _get_conn() reconnects. Retry once; re-raise if it still fails
            # (a genuinely-down DB surfaces as ERROR, as before). Name the real
            # error + keep the traceback: the broad catch also covers server-side
            # conditions (statement timeout, deadlock, admin shutdown), so the
            # message must not assert a connection drop it can't be sure of.
            if attempt >= _BARRIER_WRITE_ATTEMPTS:
                raise
            logger.warning(
                "PgBarrier: %s — DB write failed (%s: %s); cached connection "
                "likely stale, reconnecting and retrying (attempt %d/%d)",
                what,
                type(exc).__name__,
                exc,
                attempt,
                _BARRIER_WRITE_ATTEMPTS,
                exc_info=True,
            )
            time.sleep(_BARRIER_RETRY_BACKOFF_SECONDS)


def _delete_barrier(execution_id: str) -> None:
    with _cursor() as cur:
        cur.execute(
            f"DELETE FROM {qualified('pg_barrier_state')} WHERE execution_id = %s",
            (execution_id,),
        )


def claim_batch(execution_id: str, batch_index: int) -> bool:
    """Claim ``(execution_id, batch_index)`` for processing — the per-batch
    idempotency gate for the at-least-once PG pipeline.

    Atomically inserts the dedup marker (``pg_batch_dedup``); returns ``True``
    if THIS call inserted the row (first delivery — the caller should proceed
    and perform the single barrier decrement) and ``False`` if the row already
    existed (a redelivery — the caller should skip). This function itself only
    inserts the marker; pairing it with the caller's decrement is what keeps the
    barrier decremented exactly once per batch. ``ON CONFLICT DO NOTHING`` makes
    the check-and-set a single statement, so concurrent redeliveries of the same
    batch resolve to exactly one ``True`` (the row's existence is the token) with
    no race.

    Called on the in-body PG path from :func:`run_batch_with_barrier` (claim at
    batch start), alongside the in-body decrement. The companion
    :func:`clear_execution_batches` reclaims the markers at barrier finalise.
    """
    with _cursor() as cur:
        cur.execute(
            f"INSERT INTO {qualified('pg_batch_dedup')} "
            "(execution_id, batch_index, created_at) "
            "VALUES (%s, %s, now()) "
            "ON CONFLICT (execution_id, batch_index) DO NOTHING "
            "RETURNING execution_id",
            (execution_id, batch_index),
        )
        return cur.fetchone() is not None


def clear_execution_batches(execution_id: str) -> int:
    """Delete all per-batch dedup markers for an execution; returns the count.

    Called at barrier teardown (``remaining`` → 0) so the markers live exactly
    as long as the execution needs them. Executions that never finalise
    currently leak their markers — the reaper sweeps the orphaned
    ``pg_barrier_state`` row but does NOT yet reclaim ``pg_batch_dedup`` (no
    cascade); a dedup-orphan sweep is intended future work (see the
    ``PgBatchDedup`` model docstring). Safe to call when no rows exist (returns
    0). Uses the ``(execution_id, batch_index)`` constraint index (``execution_id``
    leading) for the lookup.

    Called from the barrier-finalise + abort paths.
    """
    with _cursor() as cur:
        cur.execute(
            f"DELETE FROM {qualified('pg_batch_dedup')} WHERE execution_id = %s",
            (execution_id,),
        )
        return cur.rowcount


def _dispatch_pg(
    task_name: str,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    queue: str | None,
    fairness: FairnessKey | None = None,
) -> Any:
    """Enqueue a task onto the PG queue (the one place that owns the cycle-avoiding
    local imports + the ``backend=QueueBackend.PG`` argument).

    Both the header fan-out (:meth:`PgBarrier._dispatch_header_pg`) and the
    self-chained callback (:func:`_fire_barrier_callback`) route through here.
    Returns the ``dispatch`` handle. ``queue`` is required (may be ``None`` only
    if the caller has already logged the fallback) — a ``None`` queue makes
    ``dispatch`` fall back to its default PG queue.
    """
    # Local import: dispatch/routing pull in queue plumbing that imports the
    # barrier package — importing at module load would be a cycle.
    from .dispatch import dispatch
    from .routing import QueueBackend

    return dispatch(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        fairness=fairness,
        backend=QueueBackend.PG,
    )


@dataclass(frozen=True, slots=True)
class _PgBarrierHandle:
    """Minimal ``BarrierHandle`` — ``id`` is the execution id (what call sites
    log for chord-id tracing), same as ``_RedisBarrierHandle``.
    """

    id: str


class PgBarrier:
    """``Barrier`` implementation via a Postgres ``pg_barrier_state`` row.

    Drop-in for ``CeleryChordBarrier`` / ``RedisDecrBarrier`` from the call
    sites' perspective. See the module docstring for the wire model and the
    failure-masking guards.
    """

    def enqueue(
        self,
        header_tasks: list[Signature],
        *,
        callback_task_name: str,
        callback_kwargs: dict[str, Any],
        callback_queue: str,
        app_instance: Any,
        fairness: FairnessKey | None = None,
        transport: str = DEFAULT_WORKFLOW_TRANSPORT,
    ) -> BarrierHandle | None:
        """See :class:`queue_backend.barrier.Barrier.enqueue`.

        Empty ``header_tasks`` → ``None`` (caller owns the zero-files contract);
        any substrate failure raises. ``app_instance`` is accepted for Protocol
        parity but unused.

        ``transport`` selects the fan-out mode (9e):

        - ``celery`` (default, the ``WORKER_BARRIER_BACKEND=pg`` legacy path):
          header tasks are Celery-dispatched with ``.link(barrier_pg_decr_and_check)``
          / ``.link_error(barrier_pg_abort)``; the link drives the decrement.
        - ``pg_queue`` (the fire-and-forget path): header tasks are dispatched onto
          the PG queue (``dispatch(backend=PG)``) with a ``_barrier_context`` kwarg
          carrying ``execution_id`` / ``batch_index`` / ``callback_descriptor`` —
          a PG-consumed task fires no ``.link``, so it claims its batch and runs
          the decrement in-body, self-chaining the callback at ``remaining`` → 0.
        """
        del app_instance  # Protocol parity; callback dispatched by the decrement.
        if not header_tasks:
            logger.info(
                f"[exec:{callback_kwargs.get('execution_id')}] "
                f"[pipeline:{callback_kwargs.get('pipeline_id')}] "
                "Zero header tasks detected — skipping barrier enqueue "
                "(parent should handle pipeline status updates directly)"
            )
            return None

        execution_id = callback_kwargs.get("execution_id")
        if not execution_id:
            raise ValueError(
                "PgBarrier requires execution_id in callback_kwargs — it's the "
                "primary key of the per-execution pg_barrier_state row"
            )
        execution_id = str(execution_id)

        is_pg = is_pg_transport(transport)
        try:
            fairness_headers = fairness.as_header() if fairness else None
            callback_descriptor: CallbackDescriptor = {
                "task_name": callback_task_name,
                "kwargs": callback_kwargs,
                "queue": callback_queue,
                "fairness_headers": fairness_headers,
            }
            if is_pg:
                # The decrement (run in-body on the PG path) reads this to
                # self-chain the callback onto PG rather than Celery.
                callback_descriptor["transport"] = WorkflowTransport.PG_QUEUE.value
            # expires_at = absolute orphan cap (6h). last_progress_at = now() (the
            # reaper's fast stuck signal, re-stamped on every decrement).
            ttl_seconds = barrier_ttl_seconds()
            # Stamp the owning org so the reaper can call the org-scoped status
            # API when recovering this barrier if it strands (it has only the
            # execution_id off the row otherwise).
            organization_id = str(callback_kwargs.get("organization_id") or "")
            if not organization_id:
                # Should never happen — every fan-out passes organization_id in
                # callback_kwargs. Surface loudly: a barrier with no org can't be
                # recovered via the org-scoped API if it strands.
                logger.error(
                    f"[exec:{execution_id}] PgBarrier enqueued with NO "
                    f"organization_id in callback_kwargs — a stranded barrier "
                    f"could not be reaper-recovered. This is a bug in the caller."
                )

            def _reset_barrier(cur: PgCursor) -> None:
                # UPSERT clears any leftover state from a prior run with this id.
                # No inline expiry sweep here — an unbounded global DELETE on the
                # enqueue hot path risks lock contention / deadlocks between
                # concurrent enqueues; orphan reclaim is a separate (future)
                # periodic sweep keyed on pg_barrier_expires_idx.
                cur.execute(
                    f"INSERT INTO {qualified('pg_barrier_state')} "
                    "(execution_id, organization_id, remaining, results, "
                    " created_at, expires_at, last_progress_at) "
                    "VALUES (%s, %s, %s, '[]'::jsonb, now(), "
                    "        now() + make_interval(secs => %s), now()) "
                    "ON CONFLICT (execution_id) DO UPDATE SET "
                    "  organization_id = EXCLUDED.organization_id, "
                    "  remaining = EXCLUDED.remaining, results = '[]'::jsonb, "
                    "  created_at = now(), expires_at = EXCLUDED.expires_at, "
                    "  last_progress_at = now()",
                    (
                        execution_id,
                        organization_id,
                        len(header_tasks),
                        ttl_seconds,
                    ),
                )
                # Reset per-batch dedup markers from a prior run reusing this
                # execution_id, ATOMICALLY with the barrier reset. Without this a
                # re-enqueue would leave stale markers → every in-body claim_batch
                # returns False → all batches skip → barrier hangs to expiry.
                # (Markers are written by claim_batch() on the in-body PG path.)
                cur.execute(
                    f"DELETE FROM {qualified('pg_batch_dedup')} WHERE execution_id = %s",
                    (execution_id,),
                )

            # Idempotent + pre-dispatch → safe to retry; see
            # _run_idempotent_pre_dispatch_write.
            _run_idempotent_pre_dispatch_write(
                _reset_barrier, what=f"enqueue exec={execution_id}"
            )

            self._dispatch_headers(
                header_tasks,
                is_pg=is_pg,
                execution_id=execution_id,
                callback_descriptor=callback_descriptor,
                fairness=fairness,
                fairness_headers=fairness_headers,
            )

            logger.info(
                f"Barrier enqueued via PgBarrier ({transport}) — "
                f"exec_id={execution_id}, header_tasks={len(header_tasks)}, "
                f"callback={callback_task_name}, queue={callback_queue}"
            )
            return _PgBarrierHandle(id=execution_id)

        except Exception:
            logger.exception(
                f"[exec:{execution_id}] "
                f"[pipeline:{callback_kwargs.get('pipeline_id')}] "
                f"Failed to enqueue barrier via Postgres "
                f"(callback={callback_task_name}, queue={callback_queue}, "
                f"header_tasks={len(header_tasks)})"
            )
            raise

    def _dispatch_headers(
        self,
        header_tasks: list[Signature],
        *,
        is_pg: bool,
        execution_id: str,
        callback_descriptor: CallbackDescriptor,
        fairness: FairnessKey | None,
        fairness_headers: dict[str, Any] | None,
    ) -> None:
        """Dispatch the N header tasks, one transport or the other.

        PG path (``is_pg``) → fire-and-forget onto the PG queue via
        :meth:`_dispatch_header_pg` (no ``.link``). Celery path → ``.link`` /
        ``.link_error`` chord-style. On any mid-loop dispatch failure, ``i`` of N
        never reached the queue so the counter can't reach 0 — delete the barrier
        row (and, on the PG path, reclaim dedup markers an earlier header may have
        committed, since the in-flight ``barrier_pg_abort`` is a no-op once the row
        is gone) so an in-flight decrement finds nothing, then re-raise.
        """
        link_signature = barrier_pg_decr_and_check.s(
            execution_id=execution_id, callback_descriptor=callback_descriptor
        )
        link_error_signature = barrier_pg_abort.s(execution_id=execution_id)
        for i, task in enumerate(header_tasks):
            try:
                if is_pg:
                    self._dispatch_header_pg(
                        task, i, execution_id, callback_descriptor, fairness
                    )
                else:
                    cloned = task.clone()
                    if fairness_headers:
                        cloned.set(headers=fairness_headers)
                    cloned.link(link_signature)
                    cloned.link_error(link_error_signature)
                    cloned.apply_async()
            except Exception:
                with contextlib.suppress(Exception):
                    _delete_barrier(execution_id)
                if is_pg:
                    with contextlib.suppress(Exception):
                        clear_execution_batches(execution_id)
                logger.exception(
                    f"[exec:{execution_id}] header dispatch failed at task "
                    f"{i}/{len(header_tasks)}; barrier row deleted to prevent "
                    f"spurious callback fires from the orphan tasks."
                )
                raise

    @staticmethod
    def _dispatch_header_pg(
        task: Signature,
        batch_index: int,
        execution_id: str,
        callback_descriptor: CallbackDescriptor,
        fairness: FairnessKey | None,
    ) -> None:
        """Dispatch one header task onto the PG queue (fire-and-forget mode).

        Unpacks the Celery ``Signature`` (the fan-out built it as
        ``app.signature(name, kwargs={batch_files, batch_index, total_batches},
        queue=...)`` — the batch payload is in ``kwargs``) and re-dispatches it via
        :func:`_dispatch_pg` with an added ``_barrier_context`` kwarg. The PG
        consumer runs the task; it claims ``(execution_id, batch_index)`` and runs
        the decrement in-body (no ``.link``). ``fairness`` carries org/priority
        onto the row exactly as the bare-dispatch sites do.
        """
        barrier_context: BarrierContext = {
            "execution_id": execution_id,
            "batch_index": batch_index,
            "callback_descriptor": callback_descriptor,
        }
        header_kwargs = dict(task.kwargs or {})
        header_kwargs["_barrier_context"] = barrier_context
        queue = task.options.get("queue")
        if queue is None:
            # The fan-out always sets a queue; a missing one would silently route
            # to dispatch's default PG queue (off the intended file-processing
            # queue), so surface it rather than let it slip by.
            logger.warning(
                f"[exec:{execution_id}] header task {task.task!r} (batch "
                f"{batch_index}) has no queue option — falling back to the default "
                f"PG queue; the consumer for the intended queue won't see it."
            )
        _dispatch_pg(
            task.task,
            args=list(task.args or ()),
            kwargs=header_kwargs,
            queue=queue,
            fairness=fairness,
        )


def _fairness_from_headers(
    fairness_headers: dict[str, Any] | None,
) -> FairnessKey | None:
    """Reconstruct a :class:`FairnessKey` from the stored ``x-fairness-key`` header.

    The descriptor carries the wire-shape headers (``FairnessKey.as_header()``),
    but the PG dispatch path wants the ``FairnessKey`` itself (``dispatch`` writes
    ``org_id`` + ``pipeline_priority`` onto the row). Reconstructing keeps the PG
    callback at the producer's org/priority — parity with the Celery path, which
    applies the headers directly. ``None`` when the producer attached no key.
    """
    payload = (fairness_headers or {}).get(FAIRNESS_HEADER_NAME)
    if not payload:
        return None
    return FairnessKey(
        org_id=payload.get("org_id"),
        workload_type=WorkloadType(payload["workload_type"]),
        pipeline_priority=payload.get("pipeline_priority", DEFAULT_PRIORITY),
    )


def _fire_barrier_callback(
    callback_descriptor: CallbackDescriptor, all_results: list[Any]
) -> str:
    """Dispatch the aggregating callback when the barrier completes; return its id.

    Two transports, selected by the descriptor's ``transport`` marker:

    - ``"pg_queue"`` (9e fire-and-forget PG path): self-chain the callback onto
      the PG queue via :func:`_dispatch_pg`, carrying the producer's fairness
      (reconstructed from the stored headers) so the callback rides the same
      org/priority as the Celery path — no Celery, so the whole execution stays
      off the broker.
    - absent / anything else (legacy ``.link`` path): dispatch via
      ``current_app.signature(...).apply_async()`` — byte-identical to pre-9e,
      preserving the ``fairness_headers`` the producer attached.
    """
    if is_pg_transport(callback_descriptor.get("transport")):
        handle = _dispatch_pg(
            callback_descriptor["task_name"],
            args=[all_results],
            kwargs=callback_descriptor["kwargs"],
            queue=callback_descriptor["queue"],
            fairness=_fairness_from_headers(callback_descriptor.get("fairness_headers")),
        )
        return str(handle.id)

    from celery import current_app

    # Build the callback-signature kwargs explicitly (headers only when truthy) —
    # matching CeleryChordBarrier's idiom, no spurious headers=None.
    signature_kwargs: dict[str, Any] = {
        "args": [all_results],
        "kwargs": callback_descriptor["kwargs"],
        "queue": callback_descriptor["queue"],
    }
    if callback_descriptor.get("fairness_headers"):
        signature_kwargs["headers"] = callback_descriptor["fairness_headers"]
    callback_signature = current_app.signature(
        callback_descriptor["task_name"], **signature_kwargs
    )
    return str(callback_signature.apply_async().id)


class _DecrementRow(NamedTuple):
    """The decrement ``UPDATE … RETURNING`` row, named so the caller reads
    ``row.remaining`` / ``row.results`` instead of positional ``row[0]`` / ``row[1]``
    and the ``results`` list-shape is documented in the type.
    """

    remaining: int
    results: list[Any]


def _apply_decrement(
    execution_id: str, result_json: str, *, reused: bool
) -> _DecrementRow | None:
    """Apply the barrier decrement ``UPDATE`` and return its ``(remaining,
    results)`` row (``None`` if the barrier row is already gone).

    The decrement is NON-idempotent — re-applying it double-counts (premature
    callback fire with incomplete results, or a strand past 0) — so it is split
    into its two phases and retried in ONLY the one phase where a re-apply is
    provably safe:

    - **EXECUTE phase** (``UPDATE … RETURNING`` + ``fetchone``) — the statement
      runs but is NOT yet committed. A connection-level failure here when the
      connection was *cached* (``reused`` — sampled by the caller BEFORE the entry
      guard materialises a connection) is the PgBouncer idle-reap: the statement
      never reached the server, no commit was issued, and the open transaction is
      rolled back on disconnect. So the decrement provably never landed →
      reconnect and re-apply it exactly once. A *freshly-created* connection
      failing (``reused`` False) is a genuine DB error, not a reap, so it is NOT
      retried — a reconnect would buy nothing. **This safety relies on the
      connection being non-autocommit** (psycopg2's default; ``create_pg_connection``
      does not override it): even if the server actually ran the ``UPDATE`` before
      the socket dropped, it sits in an uncommitted transaction that is rolled back
      on disconnect — durability happens ONLY at the commit below — so re-applying
      can never double-count. (``test_create_pg_connection_is_non_autocommit`` pins
      that default at its source.)
    - **COMMIT phase** — ``conn.commit()``. A failure here is AMBIGUOUS: the
      server may have applied the commit before the socket dropped. Re-applying
      could double-count, so it is NEVER retried — it propagates. On the in-body
      PG path (:func:`run_batch_with_barrier`) the caller then tears the barrier
      down so the execution fails fast; on the Celery ``.link`` path
      (:func:`barrier_pg_decr_and_check`, ``max_retries=0``) it is not retried and
      the barrier is reclaimed at ``expires_at`` by the reaper. Either way the
      counter is never corrupted.

    Any non-connection error (e.g. the NUL-byte ``psycopg2.DataError`` from the
    jsonb cast) also propagates unchanged — only the idle-reap self-heals. This is
    the decrement's counterpart to ``pg_queue.client.send``'s reused-guard
    (UN-3654) and the idempotent pre-dispatch write's retry, but phase-split
    because the decrement, unlike those, must never replay a committed write.
    """
    # ``last_progress_at = now()`` records that a batch just completed — the
    # reaper's stuck signal (it marks the execution ERROR only once no decrement
    # has landed for stuck_timeout; see barrier.py / reaper.py). last_progress_at
    # is UNINDEXED, so — like remaining/results — this stays a heap-only-tuple (HOT)
    # update: no index churn on the decrement hot path. (expires_at, the indexed
    # absolute cap, is deliberately NOT touched here, to preserve HOT.)
    sql = (
        f"UPDATE {qualified('pg_barrier_state')} "
        "   SET remaining = remaining - 1, "
        "       results = results || jsonb_build_array(%s::jsonb), "
        "       last_progress_at = now() "
        " WHERE execution_id = %s "
        "RETURNING remaining, results"
    )
    for attempt in range(1, _BARRIER_DECREMENT_ATTEMPTS + 1):
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (result_json, execution_id))
                fetched = cur.fetchone()
        except Exception as exc:
            conn_dead = _recover_after_error(conn, exc)
            # Retry ONLY a reused-conn death on the execute phase: it never
            # committed (re-applying lands exactly once) and reconnecting can
            # actually help. ``reused`` reflects the connection state at entry, so
            # it is True only on the first attempt's cached handle; a reconnect
            # makes the next attempt fresh, and the attempt bound stops the loop.
            if conn_dead and reused and attempt < _BARRIER_DECREMENT_ATTEMPTS:
                logger.warning(
                    "[exec:%s] PgBarrier decrement: execute failed on a cached "
                    "connection (%s) — reconnecting and re-applying once "
                    "(attempt %d/%d); the decrement never committed, so it lands "
                    "exactly once.",
                    execution_id,
                    type(exc).__name__,
                    attempt,
                    _BARRIER_DECREMENT_ATTEMPTS,
                    exc_info=True,
                )
                time.sleep(_BARRIER_RETRY_BACKOFF_SECONDS)
                continue
            # Not retried. A non-connection error (e.g. DataError) is logged by the
            # caller's own teardown; but a conn-dead give-up (fresh-conn death, or
            # the retry budget spent) would otherwise be silent — log it so the
            # terminal "didn't self-heal" decision leaves the same breadcrumb the
            # retryable path does, then propagate.
            if conn_dead:
                logger.warning(
                    "[exec:%s] PgBarrier decrement: execute failed with a "
                    "connection error (%s) that is NOT being retried (reused=%s, "
                    "attempt %d/%d) — propagating; the barrier is not self-healed "
                    "here.",
                    execution_id,
                    type(exc).__name__,
                    reused,
                    attempt,
                    _BARRIER_DECREMENT_ATTEMPTS,
                    exc_info=True,
                )
            raise
        try:
            conn.commit()
        except Exception as exc:
            _recover_after_error(conn, exc)
            # AMBIGUOUS — the server may have committed. Re-applying could
            # double-count, so do NOT retry: propagate (the caller fails the
            # barrier fast, or it is reclaimed at expiry) rather than corrupt it.
            logger.warning(
                "[exec:%s] PgBarrier decrement: commit failed (%s) — NOT retrying "
                "(the server may already have applied it; a re-apply would "
                "double-count). Propagating.",
                execution_id,
                type(exc).__name__,
                exc_info=True,
            )
            raise
        return None if fetched is None else _DecrementRow(int(fetched[0]), fetched[1])
    # Defensive: the loop always returns or raises before here. The annotation
    # permits None, so a type checker would NOT catch a stray fall-through — this
    # guards a future edit that breaks the always-return/raise invariant.
    raise AssertionError("unreachable: _apply_decrement loop exited without return")


def _barrier_pg_decrement(
    result: Any,
    *,
    execution_id: str,
    callback_descriptor: CallbackDescriptor,
) -> dict[str, Any]:
    """Atomic barrier decrement + last-task callback fire (substrate core).

    Appends this task's result and decrements ``remaining`` in one atomic
    statement; the single caller that drives ``remaining`` to 0 dispatches the
    aggregating callback (then deletes the row). This is the plain, in-body-
    callable core shared by two entry points:

    - the Celery ``link`` callback :func:`barrier_pg_decr_and_check` (today's
      only caller, behaviour unchanged); and
    - the 9e PR 2c PG-consumed pipeline path, which will call this directly in
      the header task's body — a PG-consumed task fires no ``.link``, so the
      decrement must run in-body.

    Callers MUST run each decrement in its own committed transaction and MUST NOT
    replay a *committed* decrement: re-applying one that already landed corrupts
    the count (fires the callback early with incomplete results, or skips past 0
    and strands the barrier). This is enforced loudly, not just in prose — entry
    raises if the shared connection is already mid-transaction (see the guard
    below), and the Celery wrapper pins ``max_retries=0`` so a task-level replay
    can't re-drive it; an orphaned barrier is bounded by ``expires_at`` instead.

    The decrement DOES self-heal one narrow, provably-safe case via
    :func:`_apply_decrement`: an execute-phase failure on a cached connection that
    PgBouncer idle-reaped (the statement never reached the server, so nothing
    committed) is reconnected and re-applied exactly once. A commit-phase failure
    is ambiguous and is NEVER retried — see :func:`_apply_decrement`.
    """
    # Sample whether the decrement will run on a *cached* connection BEFORE the
    # entry-guard's _get_conn() below materialises one. _apply_decrement's
    # reused-guard needs the pre-guard state: a freshly-created connection must NOT
    # be classified 'reused' (only a cached handle can be a stale idle-reap), but
    # the guard's _get_conn() would otherwise always leave _local.conn populated,
    # making 'reused' permanently True. Mirrors pg_queue.client.send, which samples
    # before any _get_conn().
    conn_was_cached = getattr(_local, "conn", None) is not None and not _local.conn.closed

    # Enforce the "own committed transaction" contract loudly. A caller that
    # invokes this inside an already-open transaction on the shared thread-local
    # connection would hold the row lock across the call and let the outer txn's
    # commit boundary replay the decrement — corrupting ``remaining`` and
    # breaking the exactly-one-sees-zero serialisation, surfacing only as a
    # barrier hung until ``expires_at`` (~6h). The Celery ``.link`` path always
    # enters idle (``_cursor`` commits after every use); the 2c in-body caller
    # must too. (Tests inject an autocommit connection → always idle → no trip.)
    if (
        _get_conn().get_transaction_status()
        != psycopg2.extensions.TRANSACTION_STATUS_IDLE
    ):
        raise RuntimeError(
            f"[exec:{execution_id}] _barrier_pg_decrement entered with an open "
            f"transaction on the shared connection — each decrement MUST run in "
            f"its own committed transaction (see this function's docstring). "
            f"Refusing to proceed to avoid corrupting the barrier counter."
        )

    try:
        # No default=str — a non-JSON-safe leaf must fail loudly here (it would
        # signal a BatchExecutionResult.to_dict() typed-boundary regression).
        result_json = json.dumps(result)
    except (TypeError, ValueError):
        logger.exception(
            f"[exec:{execution_id}] Header task result is not JSON-serialisable "
            f"— barrier aggregation cannot proceed (typed-boundary regression)."
        )
        raise

    # jsonb_build_array(...) appends exactly one element regardless of the
    # result's shape (``||`` would concatenate if the result were itself a list).
    try:
        row = _apply_decrement(execution_id, result_json, reused=conn_was_cached)
    except psycopg2.DataError:
        # json.dumps accepts a few bytes jsonb rejects — notably a NUL (0x00)
        # in a string. The cast above then raises, the decrement never lands, and
        # the barrier would hang to expires_at (~6h). Tear it down so the
        # execution fails fast and visibly instead.
        logger.exception(
            f"[exec:{execution_id}] Header result rejected by jsonb (e.g. a NUL "
            f"byte) — tearing down the barrier so the execution fails fast "
            f"rather than hanging until expiry."
        )
        with contextlib.suppress(Exception):
            _delete_barrier(execution_id)
        raise

    if row is None:
        # Barrier already torn down (a header failed → abort deleted the row, or
        # an expiry sweep removed it). No callback.
        logger.error(
            f"[exec:{execution_id}] PgBarrier decrement found no row — barrier "
            f"already torn down. No callback dispatched."
        )
        return {"status": "abandoned", "remaining": None}

    remaining, all_results = row.remaining, row.results
    logger.info(f"[exec:{execution_id}] PgBarrier decrement → remaining={remaining}")

    if remaining > 0:
        return {"status": "pending", "remaining": remaining}

    if remaining < 0:
        # Decremented past 0 — expiry/replay. Clean up, no fire.
        _delete_barrier(execution_id)
        logger.error(
            f"[exec:{execution_id}] PgBarrier abandoned — remaining={remaining} "
            f"(expired or torn down). No callback dispatched; execution likely "
            f"in an inconsistent terminal state and needs investigation."
        )
        return {"status": "abandoned", "remaining": remaining}

    # remaining == 0: we are the last task. psycopg2 decodes the jsonb array to
    # a Python list already — no per-element json.loads needed.
    #
    # Dispatch the callback FIRST; delete the row only after dispatch succeeds, so
    # a callback dispatch failure leaves the row (and its expiry) in place rather
    # than stranding the execution with no state and no recovery path. No
    # double-fire is possible: this is the last decrement (remaining hit 0) and
    # max_retries=0, so the task is never replayed.
    callback_id = _fire_barrier_callback(callback_descriptor, all_results)
    # Post-dispatch cleanup is best-effort: the callback already fired, so a
    # failure here is logged (not raised) — the rows linger until reclaim rather
    # than re-running the callback. The two cleanups are independent so one
    # failing doesn't skip the other and each names what failed: the barrier row
    # is reclaimed by expiry, the dedup markers by the (PR-3-blocking) dedup-orphan
    # sweep — neither re-runs anything (this is the last decrement, max_retries=0).
    try:
        _delete_barrier(execution_id)
    except Exception:
        logger.exception(
            f"[exec:{execution_id}] Barrier callback dispatched "
            f"(callback_task_id={callback_id}) but deleting the pg_barrier_state "
            f"row failed — reclaimed at expiry. Callback NOT re-run."
        )
    try:
        clear_execution_batches(execution_id)
    except Exception:
        logger.exception(
            f"[exec:{execution_id}] Barrier callback dispatched "
            f"(callback_task_id={callback_id}) but clearing pg_batch_dedup markers "
            f"failed — reclaimed by the dedup-orphan sweep. Callback NOT re-run."
        )

    logger.info(
        f"[exec:{execution_id}] Barrier complete — fired callback "
        f"{callback_descriptor['task_name']} on {callback_descriptor['queue']} "
        f"with {len(all_results)} aggregated results "
        f"(callback_task_id={callback_id})"
    )
    return {
        "status": "complete",
        "callback_task_id": callback_id,
        "aggregated_count": len(all_results),
    }


@worker_task(name="barrier_pg_decr_and_check", max_retries=0)
def barrier_pg_decr_and_check(
    result: Any,
    *,
    execution_id: str,
    callback_descriptor: CallbackDescriptor,
) -> dict[str, Any]:
    """Per-task ``link`` callback for :class:`PgBarrier` (Celery entry point).

    Thin ``@worker_task`` wrapper around :func:`_barrier_pg_decrement` so the
    decrement logic stays callable in-body (no ``.link``) on the PG-consumed
    pipeline path (9e PR 2c). ``max_retries=0`` — a Celery retry would replay
    the decrement and corrupt the count (see the core's contract).
    """
    return _barrier_pg_decrement(
        result, execution_id=execution_id, callback_descriptor=callback_descriptor
    )


@worker_task(name="barrier_pg_abort", max_retries=0)
def barrier_pg_abort(
    request: Any = None,
    exc: Any = None,
    traceback: Any = None,
    *,
    execution_id: str,
    preserve_dedup_markers: bool = False,
) -> dict[str, Any]:
    """``link_error`` callback: a header task failed → tear down barrier state.

    Mirrors chord's default error semantic (callback not invoked on header
    failure). The claim and the teardown are a SINGLE atomic statement — a
    ``DELETE … RETURNING`` in one transaction. The row's existence is the dedup
    token: the first abort deletes it (and so "wins"); every concurrent sibling
    finds nothing to delete and short-circuits. Because it's one transaction, a
    crash/failure mid-abort rolls the whole thing back (the row survives) so a
    sibling can retry — there is no "claimed-but-not-deleted" window. A late
    in-flight successful decrement then finds no row and abandons (no partial
    fire).

    ``preserve_dedup_markers`` keeps the per-batch ``pg_batch_dedup`` markers in
    place (default ``False`` — the Celery ``link_error`` path writes no markers,
    so clearing them is a harmless no-op there). The in-body PG path passes
    ``True``: the failed message can still redeliver, and a surviving marker makes
    ``claim_batch`` return ``False`` on redelivery → the batch is skipped, not
    re-run wholesale (real LLM spend). The markers are reclaimed later by the
    barrier re-arm (same execution_id) or the dedup-orphan sweep; they can never
    re-run anything on their own.

    The ``request``/``exc``/``traceback`` defaults keep the old-style
    ``errback(task_id)`` invocation (mixed-version deploy / ``bind=True``) from
    raising a ``TypeError``. This task does NOT drive workflow terminal status —
    the outer orchestrators own that (the in-body PG path marks the execution
    ERROR before calling here; see :func:`run_batch_with_barrier`).
    """
    del request, exc, traceback  # logged by the outer task; unused here
    with _cursor() as cur:
        cur.execute(
            "WITH claimed AS ("
            f"    DELETE FROM {qualified('pg_barrier_state')} WHERE execution_id = %s "
            "    RETURNING execution_id"
            ") SELECT execution_id FROM claimed",
            (execution_id,),
        )
        claimed = cur.fetchone() is not None

    if not claimed:
        # Another failure already aborted this execution (or it's already gone).
        return {"status": "already_aborted", "execution_id": execution_id}

    if not preserve_dedup_markers:
        # We won the abort: reclaim the per-batch dedup markers too (best-effort —
        # the barrier is already torn down). A leftover marker would otherwise
        # linger until the future dedup-orphan sweep; it can never re-run anything.
        with contextlib.suppress(Exception):
            clear_execution_batches(execution_id)

    logger.error(
        f"[exec:{execution_id}] PgBarrier aborted — a header task failed; "
        f"barrier state cleaned up (aggregating callback will not fire; "
        f"dedup markers {'preserved' if preserve_dedup_markers else 'cleared'})."
    )
    return {"status": "aborted", "execution_id": execution_id}


def _abort_barrier_in_body(
    execution_id: str, *, reason: str, preserve_dedup_markers: bool = False
) -> None:
    """Tear the barrier down from the in-body PG path (no ``.link_error`` here).

    Best-effort: a batch failure and a DB failure are correlated, so the abort
    itself can fail — that's logged (not swallowed silently) so a stuck barrier
    isn't masked by a misleading "torn down" message. A failed teardown bottoms
    out at the barrier's ``expires_at`` and is reclaimed by the reaper.

    ``preserve_dedup_markers`` forwards to :func:`barrier_pg_abort` — the in-body
    path keeps the per-batch markers so a redelivered batch is skipped by
    ``claim_batch`` rather than re-run wholesale.
    """
    try:
        barrier_pg_abort(
            execution_id=execution_id, preserve_dedup_markers=preserve_dedup_markers
        )
        logger.error(
            f"[exec:{execution_id}] {reason} — barrier teardown attempted in-body "
            f"(no .link_error on the PG path); aggregating callback won't fire."
        )
    except Exception:
        logger.exception(
            f"[exec:{execution_id}] {reason} AND the in-body barrier teardown "
            f"itself failed — barrier will hang until expiry and be reclaimed by "
            f"the reaper (max_retries=0, no replay)."
        )


def _mark_execution_error_on_abort(
    barrier_context: BarrierContext, *, reason: str
) -> bool:
    """Best-effort: mark the execution ERROR (+cascade files) on an in-body PG
    batch failure, so a failed batch reaches a terminal state instead of being
    stranded ``EXECUTING`` forever with no handle the reaper can find.

    Returns ``True`` iff the execution is now terminal (the mark was confirmed) —
    only then is it safe for the caller to tear the barrier row down. On failure
    (backend unreachable, or no ``organization_id`` to scope the org API) returns
    ``False``: the caller must leave the barrier row so the reaper recovers it at
    expiry, rather than erasing the only recovery handle.

    PG path only — ``run_batch_with_barrier`` is the fire-and-forget substrate;
    the Celery path never reaches here (its outer orchestrator owns terminal
    status). The org and execution id come off the barrier's callback kwargs, the
    same values the enqueue stamped onto ``pg_barrier_state``.
    """
    execution_id = str(barrier_context["execution_id"])
    _, org = callback_recovery_identity(barrier_context["callback_descriptor"])
    organization_id = str(org or "")
    if not organization_id:
        logger.error(
            f"[exec:{execution_id}] {reason} but the barrier carries no "
            f"organization_id — cannot mark it ERROR via the org-scoped API; "
            f"leaving the barrier row for the reaper (not erasing the handle)."
        )
        return False
    # Lazy import: keep this module free of the HTTP/env client at import time
    # (mirrors the reaper) and avoid an import cycle via shared.api.
    from shared.api import InternalAPIClient

    from .pg_queue.recovery import mark_execution_error

    try:
        api_client = InternalAPIClient()
    except Exception:
        logger.exception(
            f"[exec:{execution_id}] {reason} and building the internal API client "
            f"to mark it ERROR failed — leaving the barrier row for the reaper."
        )
        return False
    return mark_execution_error(
        api_client,
        execution_id,
        organization_id,
        error_message=f"[pg-barrier-abort] {reason}.",
    )


# A batch whose execution is already terminal returns its result with this
# marker set. run_batch_with_barrier bypasses the barrier decrement for it: the
# reaper has by definition already torn the barrier down, so decrementing would
# only log a spurious "decrement found no row" ERROR (false alert noise), and an
# already-terminal execution must not have its aggregating callback fired.
SKIPPED_TERMINAL_EXECUTION_KEY = "skipped_terminal_execution"


def run_batch_with_barrier(
    barrier_context: BarrierContext, work_fn: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    """Run a fire-and-forget PG-path batch under the barrier protocol (9e PR 2c).

    A PG-consumed header task fires no Celery ``.link``, so the barrier
    coordination runs in-body here, given the ``_barrier_context`` that
    :meth:`PgBarrier._dispatch_header_pg` injected (``execution_id`` /
    ``batch_index`` / ``callback_descriptor``):

    1. **Claim** ``(execution_id, batch_index)``. A redelivery (at-least-once
       queue) finds the marker already set → returns a no-op result WITHOUT
       re-running the work or re-decrementing — exactly-once decrement.
    2. **Run** ``work_fn()`` (the batch).
    3. **Decrement** the barrier with the batch result; the task that drives
       ``remaining`` → 0 self-chains the aggregating callback onto PG.

    Steps 2 *and* 3 are wrapped: any catchable failure (work error, the decrement
    guard / DB error, or the last-batch callback dispatch failing) tears the
    barrier down in-body via :func:`barrier_pg_abort` and re-raises, so it fails
    fast instead of hanging to expiry — mirroring the chord path's ``.link_error``.

    **Strand windows the reaper must cover (NOT catchable here — hard merge
    dependency for enabling the flag in PR 3, see the module / PgBatchDedup docs):**

    - A hard crash / SIGKILL / visibility-timeout expiry *during* ``work_fn()``
      leaves the dedup marker committed (claim is step 1), so redelivery returns
      ``skipped_redelivery`` and never re-runs the batch — the barrier hangs to
      ``expires_at``. (Claiming before the work avoids re-processing on the common
      redelivery case at the cost of this crash window.)
    - A hard crash *between* the decrement committing (``remaining`` → 0) and the
      callback enqueue completing: the decrement is committed (so redelivery is
      blocked by the marker) but the process is gone before the callback is
      enqueued and before any in-body abort can run, so the ``pg_barrier_state``
      row survives to ``expires_at`` with no callback ever fired. (A *software*
      callback-dispatch failure here is NOT this window — that's catchable and is
      torn down by step 3's wrap above.)

    For both, the **reaper** (sweep stranded ``pg_barrier_state``, mark the
    execution ERROR / re-drive, reclaim ``pg_batch_dedup``) is the recovery net;
    it must be live before PR 3 flips ``pg_queue_execution_enabled``.

    ``work_fn`` must return the JSON-serialisable batch result (the same dict the
    Celery chord path returns), since the decrement appends it to the barrier's
    aggregated results that the callback receives.
    """
    execution_id = str(barrier_context["execution_id"])
    batch_index = int(barrier_context["batch_index"])

    if not claim_batch(execution_id, batch_index):
        logger.info(
            f"[exec:{execution_id}] batch {batch_index} already claimed — "
            f"redelivery, skipping (barrier already decremented for this batch)."
        )
        return {
            "status": "skipped_redelivery",
            "execution_id": execution_id,
            "batch_index": batch_index,
        }

    # Wrap BOTH the work and the decrement: a decrement-side failure (the
    # open-transaction guard, a json/DB error, or the last-batch callback dispatch
    # raising) must also tear the barrier down, else the marker is committed,
    # redelivery is blocked, and the barrier strands to expiry.
    try:
        result = work_fn()
        if result.get(SKIPPED_TERMINAL_EXECUTION_KEY):
            # The batch's execution is already terminal, so the reaper has by
            # definition already torn the barrier down. Bypass the decrement —
            # decrementing a gone barrier only logs a spurious "decrement found
            # no row" ERROR (false alert noise) — and do NOT abort (nothing to
            # tear down; and an already-terminal execution must not have its
            # aggregating callback re-fired).
            logger.info(
                f"[exec:{execution_id}] batch {batch_index} skipped — execution "
                f"already terminal; barrier decrement bypassed."
            )
            return result
        _barrier_pg_decrement(
            result,
            execution_id=execution_id,
            callback_descriptor=barrier_context["callback_descriptor"],
        )
    except Exception:
        reason = f"batch {batch_index} failed"
        # Mark the execution ERROR FIRST (+cascade files) so it reaches a terminal
        # state. Only if that's confirmed do we tear the barrier row down — the
        # row is the reaper's only recovery handle, so we must not delete it while
        # the execution is still non-terminal. On a confirmed mark, keep the dedup
        # markers so this message's redelivery is skipped by claim_batch (belt-and-
        # braces with the terminal-execution guard) rather than re-run wholesale.
        if _mark_execution_error_on_abort(barrier_context, reason=reason):
            _abort_barrier_in_body(
                execution_id, reason=reason, preserve_dedup_markers=True
            )
        else:
            # Mark unconfirmed (backend down / no org): leave the barrier row so
            # the reaper marks it ERROR and reclaims it at expiry. Do NOT erase the
            # handle — that's the strand this ticket fixes.
            logger.error(
                f"[exec:{execution_id}] {reason} and could not confirm the ERROR "
                f"mark — leaving the barrier row intact for the reaper (barrier "
                f"hangs to expiry rather than stranding non-terminal)."
            )
        raise
    return result
