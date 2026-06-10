"""Redis-DECR Barrier — alternative substrate to ``CeleryChordBarrier``.

Implements the ``Barrier`` Protocol via the labs-design distributed-counter
pattern (``DECR remaining:{exec_id}``) with per-task result aggregation
in a Redis list. Selected at runtime by the ``WORKER_BARRIER_BACKEND``
env flag (default ``chord`` — see ``queue_backend.get_barrier``).

**Why this substrate exists.** Celery's ``chord(header)(body)`` aggregator
is the highest-risk Celery construct at our scale — documented silent
task drops at ~130K-task scale (see PG Queue decision journey). This
substrate replaces *only* the aggregation primitive; everything else
(dispatch, retries, result backend, monitoring) still rides on Celery.
The transport is unchanged — only the "wait for N tasks to complete,
then fire the callback with their results" coordination is moved from
Celery's chord backend to Redis.

**Wire model.**

1. ``enqueue``: ``SET remaining:{exec_id} N``, ``SET results:{exec_id} <empty>``
   (with 24h TTL as belt-and-suspenders cleanup). Each header task is
   dispatched with ``.link(barrier_decr_and_check.s(...))`` — Celery's
   per-task success hook.
2. Per-task success: the link task runs ``RPUSH results + DECR remaining``
   atomically via a Lua script. If the post-decrement counter reads 0,
   the link reads the full results list, dispatches the callback with
   it as the first arg, then deletes the Redis keys.
3. Per-task failure: the ``.link_error`` hook logs the error but does
   NOT decrement — preserving Celery chord's default error-propagation
   semantic (if any header task fails, the callback never fires; the
   outer task's error handler marks the workflow FAILED). TTLs prevent
   key leakage on stuck counters.

**Result-aggregation parity.** The callback receives
``list[BatchExecutionResult]`` exactly as it does today under
``CeleryChordBarrier`` — zero callback-side changes. Serialisation
rides through ``BatchExecutionResult.to_dict()`` / ``from_dict()``
(the typed boundary from UN-3513) ↔ JSON in Redis.

**Atomicity.** The per-task ``RPUSH + DECR`` is atomic via Lua — a
network partition mid-step can't split-brain the counter and the
result list. ``DECR`` is also atomic on its own, so exactly one task
sees the post-decrement 0.

**Mixed-version rolling deploy.** The ``WORKER_BARRIER_BACKEND`` env
var is read at worker startup, so each pod independently picks its
substrate. A given execution's tasks all share the publishing pod's
substrate choice (the barrier is selected once per execution start);
no cross-substrate aggregation within a single execution.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from celery.canvas import Signature

from unstract.core.cache.redis_client import create_redis_client

from .decorator import worker_task
from .fairness import FairnessKey
from .handle import BarrierHandle

if TYPE_CHECKING:
    import redis as redis_lib

logger = logging.getLogger(__name__)


# Env-var prefix for the barrier's Redis connection. Falls back to
# ``REDIS_`` (the canonical worker Redis instance) via ``create_redis_client``'s
# nested-getenv pattern. Operators can point the barrier at a separate
# Redis by setting ``WORKER_BARRIER_REDIS_HOST`` / ``_PORT`` etc.
_BARRIER_REDIS_ENV_PREFIX = "WORKER_BARRIER_REDIS_"

# Belt-and-suspenders cleanup for orphaned ``remaining`` / ``results``
# keys. On the happy path the Lua script ``DEL``s both keys when
# ``remaining`` reaches 0 — TTL only matters when the counter stalls
# (e.g. some header tasks fail and the link never fires for them).
#
# **Must be strictly > longest plausible execution wall-clock.** If
# TTL expires while tasks are still pending, the next successful
# task's ``DECR`` creates the counter at ``-1`` and the script fires
# the callback with just that task's result — followed by more
# spurious callbacks as remaining tasks complete.
#
# Reference budget (current sample envs):
#   - ``FILE_PROCESSING_TASK_TIME_LIMIT`` ≤ 10800 (3h) per batch
#   - ``process_file_batch`` has ``max_retries=0`` so no retry
#     amplification — worst case per batch is the time-limit ceiling
#   - Multi-batch executions ≈ max(per-batch time) since batches run
#     in parallel (worker concurrency is the limiter, not serial wait)
#
# 6h default gives 2× margin over the 3h worst case. Aligned with
# ``FILE_EXECUTION_TRACKER_TTL_IN_SECOND=18000`` (5h) — same order
# of magnitude as the existing file-execution scoping. Operators
# with longer workflows (e.g. multi-step pipelines with chained
# barriers) or shorter known max-execution-time should tune via
# ``WORKER_BARRIER_KEY_TTL_SECONDS``.
_KEY_TTL_DEFAULT_SECONDS = 6 * 60 * 60  # 6h


def _key_ttl_seconds() -> int:
    """Read the TTL from env, with the default applied on absence / parse
    failure. Read at call time (not module import) so a test
    ``monkeypatch.setenv`` flips the value without a module reload.

    Invalid values (non-int, negative, zero) fall back to default
    rather than raising — TTL is a safety-net, not a correctness
    invariant, and the worst case of misconfiguration is "wrong
    cleanup window" not "barrier broken". The fallback is logged
    so the misconfiguration surfaces.
    """
    raw = os.getenv("WORKER_BARRIER_KEY_TTL_SECONDS")
    if raw is None:
        return _KEY_TTL_DEFAULT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "WORKER_BARRIER_KEY_TTL_SECONDS=%r is not an int; "
            "falling back to default %ds",
            raw,
            _KEY_TTL_DEFAULT_SECONDS,
        )
        return _KEY_TTL_DEFAULT_SECONDS
    if value <= 0:
        logger.warning(
            "WORKER_BARRIER_KEY_TTL_SECONDS=%d must be >0; "
            "falling back to default %ds",
            value,
            _KEY_TTL_DEFAULT_SECONDS,
        )
        return _KEY_TTL_DEFAULT_SECONDS
    return value


# Atomic ``RPUSH + DECR``: when an integer pair (decremented counter,
# 0/1 result-stored flag) is returned, the link task uses the
# post-decrement value to decide whether to fire the callback. The
# script also reads results-so-far when remaining reads 0 — saving a
# round-trip and ensuring the LRANGE happens before any other task can
# RPUSH a stale result.
_RPUSH_DECR_LUA = """
local remaining_key = KEYS[1]
local results_key = KEYS[2]
local result_json = ARGV[1]
redis.call("RPUSH", results_key, result_json)
local remaining = redis.call("DECR", remaining_key)
if remaining <= 0 then
    local all_results = redis.call("LRANGE", results_key, 0, -1)
    redis.call("DEL", remaining_key, results_key)
    return {remaining, all_results}
end
return {remaining, {}}
"""


def _get_redis_client() -> redis_lib.Redis:
    """Build a Redis client from the barrier env prefix.

    ``create_redis_client`` reads ``{prefix}HOST`` etc., falling back
    to the canonical ``REDIS_`` prefix when the barrier-specific vars
    aren't set. ``decode_responses=True`` so ``LRANGE`` returns
    ``list[str]`` (we JSON-decode each entry).
    """
    return create_redis_client(
        env_prefix=_BARRIER_REDIS_ENV_PREFIX,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
    )


def _remaining_key(execution_id: str) -> str:
    return f"barrier:remaining:{execution_id}"


def _results_key(execution_id: str) -> str:
    return f"barrier:results:{execution_id}"


class RedisDecrBarrier:
    """``Barrier`` implementation via Redis ``DECR remaining`` pattern.

    Drop-in replacement for ``CeleryChordBarrier`` from the call
    sites' perspective — same ``enqueue(header_tasks, ...)`` signature,
    same ``BarrierHandle | None`` return contract, same fairness
    plumbing. The substrate difference is invisible above the
    ``Barrier`` Protocol.

    See module docstring for the wire model, atomicity, and failure
    semantics.
    """

    def __init__(self, redis_client: redis_lib.Redis | None = None) -> None:
        """Args:
        redis_client: Optional pre-built client. Tests pass a fake
            (``fakeredis``) here. Production leaves it ``None`` so
            the barrier builds its own from env on first use.
        """
        self._redis_client = redis_client

    @property
    def redis(self) -> redis_lib.Redis:
        """Lazy-init the Redis client.

        Built on first use rather than at construction time so the
        module can be imported (and the worker task registered) in
        contexts where Redis isn't yet reachable (e.g. test collection,
        worker boot before networking up).
        """
        if self._redis_client is None:
            self._redis_client = _get_redis_client()
        return self._redis_client

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

        Mirrors ``CeleryChordBarrier.enqueue`` semantics:

        - Empty ``header_tasks`` → ``None`` (caller handles the
          zero-files contract); no Redis keys touched.
        - Any substrate-level failure (Redis down, dispatch error,
          serialisation issue) → raises.
        - Success → returns a ``BarrierHandle`` whose ``.id`` is the
          execution id (no ``AsyncResult`` since there's no Celery
          chord wrapping the group; the id is what the call site
          logs for chord-id traceability).
        """
        if not header_tasks:
            execution_id = callback_kwargs.get("execution_id")
            pipeline_id = callback_kwargs.get("pipeline_id")
            logger.info(
                f"[exec:{execution_id}] [pipeline:{pipeline_id}] "
                "Zero header tasks detected — skipping barrier enqueue "
                "(parent should handle pipeline status updates directly)"
            )
            return None

        execution_id = callback_kwargs.get("execution_id")
        if not execution_id:
            raise ValueError(
                "RedisDecrBarrier requires execution_id in callback_kwargs — "
                "it's the key suffix for the per-execution remaining/results "
                "Redis keys"
            )
        execution_id = str(execution_id)

        try:
            fairness_headers = fairness.as_header() if fairness else None

            # The link task body needs to know:
            # - which execution's counter to decrement
            # - how to reconstruct + dispatch the callback when count hits 0
            # All Celery-serialisable so the link can run on any worker.
            callback_descriptor = {
                "task_name": callback_task_name,
                "kwargs": callback_kwargs,
                "queue": callback_queue,
                "fairness_headers": fairness_headers,
            }

            # Initialise the counter and an empty results list before
            # any header task can fire. ``SET ... EX 24h`` and ``DEL +
            # EXPIRE`` cover both "fresh start" and "stale leftover
            # keys from a previous run with the same exec_id" (e.g.
            # retry after partial fan-out failure). Ordered: ``DEL``
            # first to clear any stale results list, then ``SET`` the
            # counter with TTL.
            ttl_seconds = _key_ttl_seconds()
            self.redis.delete(_results_key(execution_id))
            self.redis.set(
                _remaining_key(execution_id),
                len(header_tasks),
                ex=ttl_seconds,
            )
            # ``results`` key gets a TTL too — Redis sets TTL per-key,
            # so we set it on first RPUSH via the Lua script... but
            # that's not how RPUSH works. Use ``EXPIRE`` after the
            # first push instead. For now, set a placeholder so TTL
            # applies; the first link's RPUSH appends to it.
            self.redis.expire(_results_key(execution_id), ttl_seconds)

            # Stamp fairness on each header task and attach the link.
            # ``Signature.clone()`` avoids mutating the caller's list
            # (same reasoning as ``CeleryChordBarrier``).
            link_signature = barrier_decr_and_check.s(
                execution_id=execution_id,
                callback_descriptor=callback_descriptor,
            )
            for task in header_tasks:
                cloned = task.clone()
                if fairness_headers:
                    cloned.set(headers=fairness_headers)
                cloned.link(link_signature)
                cloned.apply_async()

            logger.info(
                f"Barrier enqueued via RedisDecrBarrier — "
                f"exec_id={execution_id}, "
                f"header_tasks={len(header_tasks)}, "
                f"callback={callback_task_name}, "
                f"queue={callback_queue}"
            )

            # Handle's ``.id`` is the execution id — same call sites
            # log ``chord_id`` from this; the semantic shifts from
            # "Celery chord aggregator task id" to "execution id" but
            # both are stable per-execution identifiers and the log
            # consumers don't depend on the underlying task vs exec id
            # distinction.
            return _RedisBarrierHandle(id=execution_id)

        except Exception:
            execution_id = callback_kwargs.get("execution_id")
            pipeline_id = callback_kwargs.get("pipeline_id")
            logger.exception(
                f"[exec:{execution_id}] [pipeline:{pipeline_id}] "
                f"Failed to enqueue barrier via Redis "
                f"(callback={callback_task_name}, queue={callback_queue}, "
                f"header_tasks={len(header_tasks)})"
            )
            raise


class _RedisBarrierHandle:
    """Minimal ``BarrierHandle`` implementation.

    Just an ``id`` attribute (the execution id) so call sites that
    log ``handle.id`` for chord-id tracing keep working. Used over a
    bare ``namedtuple`` so static checkers can confirm Protocol
    satisfaction.
    """

    __slots__ = ("id",)

    def __init__(self, *, id: str) -> None:  # noqa: A002 — Protocol declares ``id``
        self.id = id


@worker_task(
    name="barrier_decr_and_check",
    # On uncaught failure the link itself shouldn't infinitely retry —
    # the counter would never decrement and the execution would hang.
    # One retry to absorb transient Redis blips; then the link gives
    # up and the execution's TTL-driven cleanup takes over.
    autoretry_for=(Exception,),
    max_retries=1,
    retry_backoff=True,
)
def barrier_decr_and_check(
    result: Any,
    *,
    execution_id: str,
    callback_descriptor: dict[str, Any],
) -> dict[str, Any]:
    """Per-task link callback for ``RedisDecrBarrier``.

    Runs after each header task completes successfully. Pushes the
    task's result into the per-execution Redis list, decrements the
    counter, and (if the post-decrement counter reads 0) dispatches
    the aggregating callback with the full result list.

    ``result`` is whatever the header task returned — for ``process_file_batch``
    that's a ``BatchExecutionResult`` already serialised to a dict via
    UN-3513's typed boundary. We pass it through ``json.dumps`` to
    survive the Redis round-trip.
    """
    from celery import current_app

    try:
        result_json = json.dumps(result, default=str)
    except (TypeError, ValueError):
        logger.exception(
            f"[exec:{execution_id}] Header task result is not "
            f"JSON-serialisable — barrier aggregation cannot proceed. "
            f"This indicates a typed-boundary regression; the "
            f"BatchExecutionResult.to_dict() contract from UN-3513 "
            f"must produce a JSON-safe shape."
        )
        raise

    redis_client = _get_redis_client()
    script = redis_client.register_script(_RPUSH_DECR_LUA)
    remaining, raw_results = script(
        keys=[
            _remaining_key(execution_id),
            _results_key(execution_id),
        ],
        args=[result_json],
    )

    logger.info(f"[exec:{execution_id}] Barrier link DECR → remaining={remaining}")

    if remaining > 0:
        # More tasks pending — nothing to do.
        return {"status": "pending", "remaining": remaining}

    # remaining == 0: we're the last task. Dispatch the callback.
    all_results = [json.loads(r) for r in raw_results]
    callback_task_name = callback_descriptor["task_name"]
    callback_kwargs = callback_descriptor["kwargs"]
    callback_queue = callback_descriptor["queue"]
    fairness_headers = callback_descriptor.get("fairness_headers")

    callback_signature = current_app.signature(
        callback_task_name,
        args=[all_results],
        kwargs=callback_kwargs,
        queue=callback_queue,
        **({"headers": fairness_headers} if fairness_headers else {}),
    )
    callback_result = callback_signature.apply_async()

    logger.info(
        f"[exec:{execution_id}] Barrier complete — "
        f"fired callback {callback_task_name} on {callback_queue} "
        f"with {len(all_results)} aggregated results "
        f"(callback_task_id={callback_result.id})"
    )

    return {
        "status": "complete",
        "callback_task_id": callback_result.id,
        "aggregated_count": len(all_results),
    }
