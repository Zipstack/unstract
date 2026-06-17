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
   ``results = []``, ``expires_at = now() + ttl``) — the UPSERT clears any stale
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
4. Orphan bound: like the Redis backend's key TTL, ``expires_at`` bounds a
   barrier whose header tasks never complete. **No expiry reclaim ships in this
   phase** — a periodic sweep job (keyed on ``pg_barrier_expires_idx``) is the
   intended backstop and is future work.

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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import psycopg2
import psycopg2.extensions

from unstract.core.data_models import (
    DEFAULT_WORKFLOW_TRANSPORT,
    WorkflowTransport,
    is_pg_transport,
)

from .barrier import BarrierContext, CallbackDescriptor, barrier_ttl_seconds
from .decorator import worker_task
from .fairness import FairnessKey
from .handle import BarrierHandle
from .pg_queue.connection import create_pg_connection

if TYPE_CHECKING:
    from celery.canvas import Signature
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)


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


@contextlib.contextmanager
def _cursor() -> Iterator[Any]:
    """Yield a cursor; commit on success, roll back + recover on error."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception as exc:
        conn_dead = isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))
        try:
            conn.rollback()
        except Exception:
            conn_dead = True
        if conn_dead or conn.closed:
            with contextlib.suppress(Exception):
                conn.close()
            _local.conn = None
        raise


def _delete_barrier(execution_id: str) -> None:
    with _cursor() as cur:
        cur.execute(
            "DELETE FROM pg_barrier_state WHERE execution_id = %s", (execution_id,)
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
            "INSERT INTO pg_batch_dedup (execution_id, batch_index, created_at) "
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
        cur.execute("DELETE FROM pg_batch_dedup WHERE execution_id = %s", (execution_id,))
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
            ttl_seconds = barrier_ttl_seconds()

            with _cursor() as cur:
                # UPSERT clears any leftover state from a prior run with this id.
                # No inline expiry sweep here — an unbounded global DELETE on the
                # enqueue hot path risks lock contention / deadlocks between
                # concurrent enqueues; orphan reclaim is a separate (future)
                # periodic sweep keyed on pg_barrier_expires_idx.
                cur.execute(
                    "INSERT INTO pg_barrier_state "
                    "(execution_id, remaining, results, created_at, expires_at) "
                    "VALUES (%s, %s, '[]'::jsonb, now(), "
                    "        now() + make_interval(secs => %s)) "
                    "ON CONFLICT (execution_id) DO UPDATE SET "
                    "  remaining = EXCLUDED.remaining, results = '[]'::jsonb, "
                    "  created_at = now(), expires_at = EXCLUDED.expires_at",
                    (execution_id, len(header_tasks), ttl_seconds),
                )
                # Reset per-batch dedup markers from a prior run reusing this
                # execution_id, ATOMICALLY with the barrier reset. Without this a
                # re-enqueue would leave stale markers → every in-body claim_batch
                # returns False → all batches skip → barrier hangs to expiry.
                # (Markers are written by claim_batch() on the in-body PG path.)
                cur.execute(
                    "DELETE FROM pg_batch_dedup WHERE execution_id = %s",
                    (execution_id,),
                )

            link_signature = barrier_pg_decr_and_check.s(
                execution_id=execution_id,
                callback_descriptor=callback_descriptor,
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
                    # Mid-loop dispatch failure: i of N never reached the queue,
                    # so the counter can't reach 0. Delete the row so an in-flight
                    # decrement (link or in-body) finds no row and cleans up;
                    # re-raise so the caller marks the workflow ERROR.
                    with contextlib.suppress(Exception):
                        _delete_barrier(execution_id)
                    logger.exception(
                        f"[exec:{execution_id}] header dispatch failed at task "
                        f"{i}/{len(header_tasks)}; barrier row deleted to prevent "
                        f"spurious callback fires from the orphan tasks."
                    )
                    raise

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


def _fire_barrier_callback(
    callback_descriptor: CallbackDescriptor, all_results: list[Any]
) -> str:
    """Dispatch the aggregating callback when the barrier completes; return its id.

    Two transports, selected by the descriptor's ``transport`` marker:

    - ``"pg_queue"`` (9e fire-and-forget PG path): self-chain the callback onto
      the PG queue via :func:`_dispatch_pg` — no Celery, so the whole execution
      stays off the broker. (The callback rides default priority; the barrier's
      fan-out fairness has already been applied to the header tasks.)
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

    Callers MUST run each decrement in its own committed transaction (the
    decrement ``UPDATE`` runs in its own ``_cursor()`` txn) and MUST NOT retry
    it: a replay re-runs the decrement and corrupts the count. This is enforced
    loudly, not just in prose — entry raises if the shared connection is already
    mid-transaction (see the guard below). The Celery wrapper additionally pins
    ``max_retries=0``; an orphaned barrier is bounded by ``expires_at`` instead.
    """
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
        with _cursor() as cur:
            cur.execute(
                "UPDATE pg_barrier_state "
                "   SET remaining = remaining - 1, "
                "       results = results || jsonb_build_array(%s::jsonb) "
                " WHERE execution_id = %s "
                "RETURNING remaining, results",
                (result_json, execution_id),
            )
            row = cur.fetchone()
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

    remaining, all_results = int(row[0]), row[1]
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

    The ``request``/``exc``/``traceback`` defaults keep the old-style
    ``errback(task_id)`` invocation (mixed-version deploy / ``bind=True``) from
    raising a ``TypeError``. This task does NOT drive workflow terminal status —
    the outer orchestrators own that.
    """
    del request, exc, traceback  # logged by the outer task; unused here
    with _cursor() as cur:
        cur.execute(
            "WITH claimed AS ("
            "    DELETE FROM pg_barrier_state WHERE execution_id = %s "
            "    RETURNING execution_id"
            ") SELECT execution_id FROM claimed",
            (execution_id,),
        )
        claimed = cur.fetchone() is not None

    if not claimed:
        # Another failure already aborted this execution (or it's already gone).
        return {"status": "already_aborted", "execution_id": execution_id}

    # We won the abort: reclaim the per-batch dedup markers too (best-effort —
    # the barrier is already torn down). A leftover marker would otherwise linger
    # until the future dedup-orphan sweep; it can never re-run anything.
    with contextlib.suppress(Exception):
        clear_execution_batches(execution_id)

    logger.error(
        f"[exec:{execution_id}] PgBarrier aborted — a header task failed; "
        f"barrier state cleaned up (aggregating callback will not fire)."
    )
    return {"status": "aborted", "execution_id": execution_id}


def _abort_barrier_in_body(execution_id: str, *, reason: str) -> None:
    """Tear the barrier down from the in-body PG path (no ``.link_error`` here).

    Best-effort: a batch failure and a DB failure are correlated, so the abort
    itself can fail — that's logged (not swallowed silently) so a stuck barrier
    isn't masked by a misleading "torn down" message. A failed teardown bottoms
    out at the barrier's ``expires_at`` and is reclaimed by the reaper.
    """
    try:
        barrier_pg_abort(execution_id=execution_id)
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
        _barrier_pg_decrement(
            result,
            execution_id=execution_id,
            callback_descriptor=barrier_context["callback_descriptor"],
        )
    except Exception:
        _abort_barrier_in_body(execution_id, reason=f"batch {batch_index} failed")
        raise
    return result
