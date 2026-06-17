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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import psycopg2
import psycopg2.extensions

from .barrier import CallbackDescriptor, barrier_ttl_seconds
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
    ) -> BarrierHandle | None:
        """See :class:`queue_backend.barrier.Barrier.enqueue`.

        Empty ``header_tasks`` → ``None`` (caller owns the zero-files contract);
        any substrate failure raises. ``app_instance`` is accepted for Protocol
        parity but unused — the callback is built inside the link task via
        ``current_app`` so it runs against the worker's app.
        """
        del app_instance  # Protocol parity; callback built in the link task.
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

        try:
            fairness_headers = fairness.as_header() if fairness else None
            callback_descriptor: CallbackDescriptor = {
                "task_name": callback_task_name,
                "kwargs": callback_kwargs,
                "queue": callback_queue,
                "fairness_headers": fairness_headers,
            }
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

            link_signature = barrier_pg_decr_and_check.s(
                execution_id=execution_id,
                callback_descriptor=callback_descriptor,
            )
            link_error_signature = barrier_pg_abort.s(execution_id=execution_id)
            for i, task in enumerate(header_tasks):
                try:
                    cloned = task.clone()
                    if fairness_headers:
                        cloned.set(headers=fairness_headers)
                    cloned.link(link_signature)
                    cloned.link_error(link_error_signature)
                    cloned.apply_async()
                except Exception:
                    # Mid-loop dispatch failure: i of N never reached the broker,
                    # so the counter can't reach 0. Delete the row so in-flight
                    # links' decrement finds no row and cleans up; re-raise so the
                    # caller marks the workflow ERROR.
                    with contextlib.suppress(Exception):
                        _delete_barrier(execution_id)
                    logger.exception(
                        f"[exec:{execution_id}] apply_async failed at task "
                        f"{i}/{len(header_tasks)}; barrier row deleted to prevent "
                        f"spurious callback fires from the orphan tasks' links."
                    )
                    raise

            logger.info(
                f"Barrier enqueued via PgBarrier — exec_id={execution_id}, "
                f"header_tasks={len(header_tasks)}, callback={callback_task_name}, "
                f"queue={callback_queue}"
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
    from celery import current_app

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
    # a Python list already — no per-element json.loads needed. Build the kwargs
    # explicitly (headers only when truthy) — clearer than an inline ** spread,
    # matching CeleryChordBarrier's idiom.
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
    # Dispatch FIRST; delete the row only after dispatch succeeds, so a callback
    # apply_async failure leaves the row (and its expiry) in place rather than
    # stranding the execution with no state and no recovery path.
    callback_result = callback_signature.apply_async()
    # The post-dispatch delete must not mask the successful dispatch: the callback
    # already fired, so a delete error here is logged (not raised) — the row
    # lingers until expiry rather than re-running the callback. No double-fire is
    # possible: this is the last decrement (remaining hit 0) and max_retries=0, so
    # the link task is never replayed.
    try:
        _delete_barrier(execution_id)
    except Exception:
        logger.exception(
            f"[exec:{execution_id}] Barrier callback dispatched "
            f"(callback_task_id={callback_result.id}) but the post-dispatch row "
            f"delete failed — row will be reclaimed at expiry. Callback NOT "
            f"re-run (max_retries=0)."
        )

    logger.info(
        f"[exec:{execution_id}] Barrier complete — fired callback "
        f"{callback_descriptor['task_name']} on {callback_descriptor['queue']} "
        f"with {len(all_results)} aggregated results "
        f"(callback_task_id={callback_result.id})"
    )
    return {
        "status": "complete",
        "callback_task_id": callback_result.id,
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

    logger.error(
        f"[exec:{execution_id}] PgBarrier aborted — a header task failed; "
        f"barrier state cleaned up (aggregating callback will not fire)."
    )
    return {"status": "aborted", "execution_id": execution_id}
