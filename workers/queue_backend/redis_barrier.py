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

1. ``enqueue``: ``SET remaining:{exec_id} N`` with TTL (default 6h,
   tunable via ``WORKER_BARRIER_KEY_TTL_SECONDS``). The results list
   is created lazily by the first link task's ``RPUSH`` — its TTL is
   set inside the Lua script after the push, so both keys share the
   same expiry window. Each header task is dispatched with
   ``.link(barrier_decr_and_check.s(...))`` (success) and
   ``.link_error(barrier_abort.s(...))`` (failure).
2. Per-task success: the link task runs ``RPUSH results + EXPIRE +
   DECR remaining`` atomically via a Lua script. If the post-decrement
   counter reads exactly 0, the link reads the full results list,
   dispatches the callback with it as the first arg, then deletes
   the Redis keys.
3. Per-task failure: ``barrier_abort`` runs as a link_error, DELing
   both barrier keys + logging the failure. Mirrors Celery chord's
   default error-propagation semantic (callback isn't invoked when
   any header fails). The outer task's error handler marks the
   workflow FAILED; this task only cleans barrier state.
4. TTL safety net: if the link/link_error never fire for some task
   (worker crash mid-execution, broker outage), TTL expires the keys
   after the configured window. Subsequent successful tasks' DECR on
   the missing counter returns negative; the Lua script's ``< 0``
   branch DELs cleanly without firing a spurious callback.

**Result-aggregation parity.** The callback receives
``list[BatchExecutionResult]`` exactly as it does today under
``CeleryChordBarrier`` — zero callback-side changes. Serialisation
rides through ``BatchExecutionResult.to_dict()`` / ``from_dict()``
(the typed callback boundary) ↔ JSON in Redis.

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

import contextlib
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

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
# Reference budget: the operator-tuned ceiling is whatever
# ``FILE_PROCESSING_TASK_TIME_LIMIT`` is set to in the deployment env
# (workers/sample.env ships 7200/2h; docker/sample.env up to 10800/3h).
# ``process_file_batch`` has ``max_retries=0`` so no retry amplification —
# worst case per batch is the time-limit ceiling. Multi-batch
# executions ≈ max(per-batch time) since batches run in parallel
# (worker concurrency is the limiter, not serial wait).
#
# 6h default gives 2-3x margin over the documented per-batch ceiling
# while staying in the same order of magnitude as
# ``FILE_EXECUTION_TRACKER_TTL_IN_SECOND=18000`` (5h). Operators with
# longer workflows (e.g. multi-step pipelines with chained barriers)
# or shorter known max-execution-time should tune via
# ``WORKER_BARRIER_KEY_TTL_SECONDS``.
_KEY_TTL_DEFAULT_SECONDS = 6 * 60 * 60  # 6h


def _key_ttl_seconds() -> int:
    """Read the TTL from env, applying the default only on absence.

    Read at call time (not module import) so a test
    ``monkeypatch.setenv`` flips the value without a module reload.

    Invalid values (non-int, negative, zero) **raise**, matching the
    posture in ``get_barrier()`` where ``WORKER_BARRIER_BACKEND=rediz``
    raises rather than silently falling back to chord. A misconfigured
    TTL shorter than execution wall-clock is a correctness issue per
    this file's docstring (would cause spurious callback fires) —
    operators get the same loud-on-misconfig signal as for the
    backend flag.
    """
    raw = os.getenv("WORKER_BARRIER_KEY_TTL_SECONDS")
    if raw is None:
        return _KEY_TTL_DEFAULT_SECONDS
    try:
        value = int(raw)
    except ValueError as e:
        raise ValueError(
            f"WORKER_BARRIER_KEY_TTL_SECONDS={raw!r} is not an integer. "
            f"Unset the env var to default to {_KEY_TTL_DEFAULT_SECONDS}s "
            f"(6h)."
        ) from e
    if value <= 0:
        raise ValueError(
            f"WORKER_BARRIER_KEY_TTL_SECONDS={value} must be a positive "
            f"integer. Unset the env var to default to "
            f"{_KEY_TTL_DEFAULT_SECONDS}s (6h)."
        )
    return value


# Atomic ``RPUSH + EXPIRE + DECR``: returns ``(remaining, results)``.
#
# Three branches the Python side reads off the returned counter:
#
#   remaining > 0  — pending, no results returned (still aggregating)
#   remaining == 0 — complete, all results returned (we are the last).
#                    Keys are NOT DEL'd here — Python defers the DEL
#                    until after ``apply_async()`` succeeds, so that
#                    a callback-dispatch failure leaves the keys (and
#                    their TTL) in place rather than stranding the
#                    execution with no state + no recovery path.
#   remaining < 0  — TTL-expired counter (or replay after cleanup);
#                    keys DEL'd inside the script to prevent further
#                    spurious fires, no callback dispatched.
#
# Setting the ``results`` key TTL inside the script — ``EXPIRE`` on
# the call AFTER ``RPUSH`` ensures the key exists when EXPIRE runs
# (issuing EXPIRE before any push is a no-op on a non-existent key,
# which is the bug the previous version had). Repeated EXPIRE per
# RPUSH is cheap and keeps both keys' TTLs aligned.
_RPUSH_DECR_LUA = """
local remaining_key = KEYS[1]
local results_key = KEYS[2]
local result_json = ARGV[1]
local ttl_seconds = tonumber(ARGV[2])
redis.call("RPUSH", results_key, result_json)
redis.call("EXPIRE", results_key, ttl_seconds)
local remaining = redis.call("DECR", remaining_key)
if remaining == 0 then
    -- We're the last task. LRANGE the results for the Python side to
    -- dispatch the callback. DO NOT DEL the keys here — Python defers
    -- the DEL until after apply_async() succeeds so a dispatch failure
    -- (broker outage, serialisation error) leaves the keys + TTL in
    -- place. Without this deferral, an apply_async failure would
    -- strand the execution with both keys gone, no TTL, no Celery
    -- retry (max_retries=0), and no link_error fallback — strictly
    -- worse than the chord baseline (where Celery's chord backend
    -- owns + retries body invocation).
    local all_results = redis.call("LRANGE", results_key, 0, -1)
    return {remaining, all_results}
end
if remaining < 0 then
    -- Counter was TTL-expired (or already cleaned up) when this task
    -- ran. ``DECR`` on a missing key created it at ``-1``; subsequent
    -- tasks would land here too. DEL both keys so neither this task
    -- nor any subsequent one fires a spurious callback; the abandoned
    -- branch on the Python side surfaces an error-severity log.
    redis.call("DEL", remaining_key, results_key)
    return {remaining, {}}
end
return {remaining, {}}
"""


# Process-local cached Redis client. Lazy-initialised on first call
# within a worker process; reused across every ``barrier_decr_and_check``
# / ``barrier_abort`` / ``RedisDecrBarrier`` invocation in that process.
#
# Why a singleton: ``create_redis_client`` builds a fresh
# ``ConnectionPool`` each call. Without caching, a 1000-task fan-out
# would spin up 1000 separate pools (1000 TCP handshakes torn down in
# sequence) — exactly the scale this substrate exists to handle.
#
# Fork safety: Celery's prefork model re-imports this module in each
# child process, so each worker process gets its own fresh
# ``_redis_client_singleton`` — no socket sharing across fork
# boundaries (which would corrupt state).
#
# Thread safety: redis-py's ``ConnectionPool`` is internally thread-safe,
# so concurrent users of the cached client are fine. The lazy-init
# itself is not locked — two threads racing on the first call could
# briefly create two pools, with one being orphaned. The cost is one
# short-lived pool (immediately GC'd), not a correctness issue.
_redis_client_singleton: redis_lib.Redis | None = None


def _get_redis_client() -> redis_lib.Redis:
    """Return a process-cached Redis client for the barrier.

    ``create_redis_client``'s nested-getenv fallback only covers
    HOST/PORT/PASSWORD/USER/DB — it does NOT cross-fall-back
    SENTINEL_MODE or SSL. In a deployment where the canonical Redis
    is Sentinel-backed or TLS-secured, leaving ``WORKER_BARRIER_REDIS_*``
    unset and relying on the documented HOST fallback would result in
    the barrier inheriting the right host/port but connecting
    standalone/plaintext — which fails (or worse, connects without
    TLS) every execution the moment the flag flips.

    To avoid that footgun: when no barrier-specific HOST is set, use
    the canonical ``REDIS_`` prefix *directly* so we inherit the FULL
    canonical config (including Sentinel + SSL). When an operator
    has set ``WORKER_BARRIER_REDIS_HOST`` they've opted into a
    dedicated barrier Redis and are responsible for the full config
    (HOST + PORT + ... + SENTINEL_MODE + SSL).

    ``decode_responses=True`` so ``LRANGE`` returns ``list[str]``
    (we JSON-decode each entry).
    """
    global _redis_client_singleton
    if _redis_client_singleton is None:
        # If no dedicated barrier-Redis host is configured, use the
        # canonical REDIS_ prefix so Sentinel/SSL config inherits too.
        if os.getenv(f"{_BARRIER_REDIS_ENV_PREFIX}HOST"):
            env_prefix = _BARRIER_REDIS_ENV_PREFIX
        else:
            env_prefix = "REDIS_"
        _redis_client_singleton = create_redis_client(
            env_prefix=env_prefix,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _redis_client_singleton


def _remaining_key(execution_id: str) -> str:
    return f"barrier:remaining:{execution_id}"


def _results_key(execution_id: str) -> str:
    return f"barrier:results:{execution_id}"


def _abort_lock_key(execution_id: str) -> str:
    """Per-execution dedup lock for ``barrier_abort``.

    Set via ``SET NX EX`` in ``barrier_abort`` to collapse N concurrent
    header-task failures into a single Sentry/error event. MUST be
    cleared at the start of a new barrier (in ``enqueue``) — otherwise
    a retry that reuses an ``execution_id`` would hit a stale lock,
    early-exit the abort path, and silently mask the failed retry as
    successful.
    """
    return f"barrier:abort_lock:{execution_id}"


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

        Production path: ``self._redis_client is None`` → falls back to
        (and caches) the module-level ``_redis_client_singleton``, so
        the instance and the standalone ``barrier_decr_and_check`` /
        ``barrier_abort`` worker tasks all share the same
        ``ConnectionPool``.

        Test path: ``__init__(redis_client=...)`` bypasses this branch
        entirely — fixtures inject a ``MagicMock`` / ``fakeredis``
        without touching the module-level singleton (which would leak
        across tests).
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

        Note: ``app_instance`` is accepted for ``Barrier`` Protocol
        parity with ``CeleryChordBarrier`` but unused by this
        substrate. The callback signature is built inside the link
        task via ``celery.current_app.signature(...)`` (so the link
        runs against the *worker's* app, not the producer's). Keeping
        the parameter in the signature lets call sites swap between
        substrates without per-substrate adapter code.
        """
        # Explicit ``del`` documents the Protocol-parity intent and
        # satisfies static linters' unused-parameter check.
        del app_instance
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
            callback_descriptor: CallbackDescriptor = {
                "task_name": callback_task_name,
                "kwargs": callback_kwargs,
                "queue": callback_queue,
                "fairness_headers": fairness_headers,
            }

            # Initialise the counter before any header task can fire.
            # ``SET remaining N EX <ttl>`` overwrites any stale counter
            # left from a prior run with the same exec_id; the upfront
            # ``DEL results, abort_lock`` (below) clears the rest of
            # the prior-run state (the results list grows via RPUSH so
            # we must clear it explicitly; the abort_lock would otherwise
            # silently mask a retry's failure as success — see the
            # comment block at the DELETE call). ``ttl`` is
            # ``_key_ttl_seconds()`` (6h default).
            ttl_seconds = _key_ttl_seconds()
            # Clear any leftover state from a prior execution with this
            # execution_id (including the dedup lock written by a
            # previous run's ``barrier_abort``). Without DELing the
            # abort_lock here, a retry that reuses execution_id would
            # find the stale lock and route every ``barrier_abort``
            # straight to the deduplicated branch — leaving B's
            # ``remaining``/``results`` keys uncleaned. In-flight
            # successful tasks from B would then hit ``remaining == 0``
            # via DECR and fire the callback with partial results,
            # silently masking the failed retry as successful.
            self.redis.delete(
                _results_key(execution_id),
                _abort_lock_key(execution_id),
            )
            self.redis.set(
                _remaining_key(execution_id),
                len(header_tasks),
                ex=ttl_seconds,
            )
            # ``results`` key TTL is set inside the Lua script on
            # first RPUSH — ``EXPIRE`` on a non-existent key is a
            # no-op, so we can't pre-set it here.

            # Stamp fairness on each header task and attach the link
            # (success) + link_error (failure) callbacks.
            # ``Signature.clone()`` avoids mutating the caller's list
            # (same reasoning as ``CeleryChordBarrier``).
            link_signature = barrier_decr_and_check.s(
                execution_id=execution_id,
                callback_descriptor=callback_descriptor,
            )
            # link_error explicitly propagates header-task failures —
            # mirrors Celery chord's default error semantic (chord
            # callback isn't invoked on header failure). Without this,
            # a failed header task would leave the counter stuck and
            # the execution would hang until TTL cleanup. The abort
            # task DELs the barrier keys + logs the error; the outer
            # task's error path is responsible for the workflow
            # status update.
            link_error_signature = barrier_abort.s(execution_id=execution_id)
            for i, task in enumerate(header_tasks):
                try:
                    cloned = task.clone()
                    if fairness_headers:
                        cloned.set(headers=fairness_headers)
                    cloned.link(link_signature)
                    cloned.link_error(link_error_signature)
                    cloned.apply_async()
                except Exception:
                    # Mid-loop dispatch failure: tasks 0..i-1 are
                    # already in flight with the link attached, but
                    # ``i`` of N never made it to the broker. The
                    # counter would never reach 0 → execution hangs.
                    # DEL the barrier keys so the in-flight links'
                    # DECR-on-missing returns negative and the Lua
                    # script's ``< 0`` branch DELs cleanly. Re-raise
                    # so the caller's status-update path marks the
                    # workflow ERROR.
                    self.redis.delete(
                        _remaining_key(execution_id),
                        _results_key(execution_id),
                    )
                    # ``logger.exception`` captures the underlying
                    # apply_async failure cause (broker timeout vs
                    # serialisation error vs routing error) alongside
                    # the orphan-count context — without it, a reader
                    # of this log can't tell why dispatch failed and
                    # has to cross-reference the outer handler's log.
                    logger.exception(
                        f"[exec:{execution_id}] apply_async failed at "
                        f"task {i}/{len(header_tasks)}; {i} orphan tasks "
                        f"already dispatched. Barrier keys DEL'd to "
                        f"prevent spurious callback fires from the "
                        f"orphan tasks' link decrements."
                    )
                    raise

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


class CallbackDescriptor(TypedDict):
    """Shape of the dict baked into the link signature and re-read on
    the worker that runs ``barrier_decr_and_check``.

    This descriptor crosses a serialisation boundary (Celery
    ``signature(...)`` → broker → consumer worker), so the four-key
    contract is otherwise enforced only by string literals duplicated
    across producer and consumer. Typing it as a ``TypedDict`` gives
    the type checker a chance to catch typos / renames before they
    surface as remote ``KeyError`` mid-aggregation.

    ``fairness_headers`` is always present in the dict; ``None`` when
    the producer passed no ``FairnessKey``.
    """

    task_name: str
    kwargs: dict[str, Any]
    queue: str
    fairness_headers: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class _RedisBarrierHandle:
    """Minimal ``BarrierHandle`` implementation.

    Just an ``id`` attribute (the execution id) so call sites that
    log ``handle.id`` for chord-id tracing keep working. A class
    (rather than a ``namedtuple``) gives a clear home for the
    docstring + ``slots=True`` memory control; the ``BarrierHandle``
    Protocol is structural so any object exposing ``id: str`` would
    type-check.
    """

    id: str


@worker_task(
    name="barrier_decr_and_check",
    # ``max_retries=0`` — the link task is intentionally non-idempotent
    # at the Redis-script level (RPUSH + DECR are committed atomically,
    # but a Celery retry would replay the script and double-count). Any
    # Celery-level retry would cause a second RPUSH + DECR, corrupting
    # the aggregation. If the link fails after the Lua commit (e.g. the
    # subsequent callback ``apply_async`` raises), the counter has
    # already advanced — TTL-driven cleanup is the safety net, and the
    # outer execution's error path marks the workflow status.
    #
    # Trade-off: a transient Redis blip on the link's Lua call means
    # this task's contribution is lost (counter doesn't advance) and
    # the execution hangs until TTL. Acceptable because (a) the
    # alternative — letting Celery retry — corrupts the aggregation,
    # and (b) Redis blips are operator-visible via monitoring, unlike
    # silent double-counts.
    max_retries=0,
)
def barrier_decr_and_check(
    result: Any,
    *,
    execution_id: str,
    callback_descriptor: CallbackDescriptor,
) -> dict[str, Any]:
    """Per-task link callback for ``RedisDecrBarrier``.

    Runs after each header task completes successfully. Pushes the
    task's result into the per-execution Redis list, decrements the
    counter, and (if the post-decrement counter reads 0) dispatches
    the aggregating callback with the full result list.

    ``result`` is whatever the header task returned — for ``process_file_batch``
    that's a ``BatchExecutionResult`` already serialised to a dict via
    the typed callback boundary. We pass it through ``json.dumps`` to
    survive the Redis round-trip.
    """
    from celery import current_app

    try:
        # No ``default=str`` — that would silently stringify any non-
        # JSON-safe leaf (datetime, UUID, Decimal, sets...) and mask
        # the typed-boundary regression the surrounding ``try/except``
        # is here to surface. The header task's return value is
        # expected to be a fully JSON-safe dict per the
        # ``BatchExecutionResult.to_dict()`` contract; anything else
        # should fail loudly here so the regression surfaces.
        result_json = json.dumps(result)
    except (TypeError, ValueError):
        logger.exception(
            f"[exec:{execution_id}] Header task result is not "
            f"JSON-serialisable — barrier aggregation cannot proceed. "
            f"This indicates a typed-boundary regression; the "
            f"BatchExecutionResult.to_dict() contract must produce a "
            f"JSON-safe shape."
        )
        raise

    redis_client = _get_redis_client()
    script = redis_client.register_script(_RPUSH_DECR_LUA)
    remaining, raw_results = script(
        keys=[
            _remaining_key(execution_id),
            _results_key(execution_id),
        ],
        args=[result_json, _key_ttl_seconds()],
    )

    logger.info(f"[exec:{execution_id}] Barrier link DECR → remaining={remaining}")

    if remaining > 0:
        # More tasks pending — nothing to do.
        return {"status": "pending", "remaining": remaining}

    if remaining < 0:
        # TTL-expired counter (or replay after cleanup). The Lua
        # script already DEL'd both keys to prevent further spurious
        # fires on subsequent task completions. No callback dispatch.
        #
        # Logged at ERROR (not WARNING) because reaching this branch
        # means the barrier was torn down out from under in-flight
        # tasks — by definition an abnormal terminal state where the
        # execution almost certainly did not complete normally.
        # Returning normally from a .link is indistinguishable from
        # success to Celery; the ERROR log is the only execution-id-
        # tagged signal an operator can correlate to the hung/
        # incorrectly-statused execution.
        logger.error(
            f"[exec:{execution_id}] Barrier abandoned — counter went "
            f"negative (remaining={remaining}); keys were TTL-expired "
            f"or torn down. No callback dispatched; execution likely "
            f"in an inconsistent terminal state and needs investigation."
        )
        return {"status": "abandoned", "remaining": remaining}

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
    # Dispatch FIRST; DEL the barrier keys only after dispatch succeeds.
    #
    # If apply_async raises (broker outage, serialisation error,
    # routing failure), the exception propagates. The barrier keys
    # are NOT yet DEL'd, so:
    #   - Subsequent late-arriving link tasks (if any) hit the Lua
    #     ``< 0`` branch (counter is still 0 — DECR-on-zero would
    #     yield -1) and exit cleanly via the abandoned branch.
    #   - The keys TTL-expire eventually — Redis cleans them up.
    #   - The link task's failure surfaces via Celery's standard
    #     task-failure channels.
    #
    # If we DEL'd before apply_async (the previous design), an
    # apply_async failure would strand the execution with no keys,
    # no TTL, no Celery retry (max_retries=0), and no link_error
    # fallback — silent infinite hang. The deferred DEL is what
    # restores parity-or-better with the chord baseline.
    callback_result = callback_signature.apply_async()
    redis_client.delete(
        _remaining_key(execution_id),
        _results_key(execution_id),
    )

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


@worker_task(
    name="barrier_abort",
    # Same posture as ``barrier_decr_and_check`` — non-idempotent at
    # the Redis level (DEL is fine to repeat, but we don't want
    # double-logged abort events polluting Sentry).
    max_retries=0,
)
def barrier_abort(
    request: Any = None,
    exc: Any = None,
    traceback: Any = None,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """``link_error`` callback: header task failed → clean up barrier state.

    Celery 5.5 invokes new-style errbacks as
    ``errback(request, exc, traceback)`` only for ``bind=False`` tasks
    with arity > 1. If a worker hits the ``NotRegistered`` fallback
    during a mixed-version rolling deploy (or if this task is ever
    switched to ``bind=True``), Celery calls the errback old-style
    with just ``(task_id,)``. The defaults on ``request`` / ``exc`` /
    ``traceback`` mean the old-style path degrades to a clean
    ``exc=None`` log line rather than a confusing
    ``TypeError: missing required positional arguments``.

    Mirrors Celery chord's default error semantic: when any header
    task fails, the chord callback isn't invoked. Without explicit
    cleanup the ``remaining`` counter would stay above 0 until TTL
    expiry, the ``results`` key would leak, and any subsequent
    successful header tasks' link would still DECR — eventually
    spurious-firing the callback with partial results (or via the
    Lua ``< 0`` branch, abandoning the execution but only after the
    extra task work).

    We DEL the barrier keys here so the in-flight successful tasks'
    link DECR returns negative → Lua ``< 0`` branch fires →
    aggregation cleanly abandoned. **Terminal status drivers**: this
    task does NOT mark the workflow FAILED — the outer orchestrators
    (``_run_workflow_api`` / ``_orchestrate_file_processing_general``)
    wrap only the *synchronous* fan-out in try/except and have
    already returned by the time ``barrier_abort`` runs. Workflow
    terminal status on async header failure is driven by per-file
    updates inside ``process_file_batch`` plus the eventual
    aggregating callback (which won't fire because we DEL'd the
    keys). A future Phase 6b' refinement may have ``barrier_abort``
    itself drive the execution-level status update.

    **Concurrent-failure dedup.** Every header task attaches the same
    ``link_error``, so N simultaneous failures would otherwise fire N
    ``barrier_abort`` executions — each calling ``logger.error`` and
    each producing its own Sentry event for what is a *single* logical
    execution failure. A ``SET NX`` lock on
    ``barrier:abort_lock:{execution_id}`` makes the first abort win;
    subsequent aborts for the same execution see the lock present and
    early-exit silently. The DELs are idempotent anyway (DEL on a
    missing key is a no-op), but the dedup collapses the alert noise.

    **Lock release on DELETE failure.** If SET NX succeeds (this
    abort wins) but the subsequent DELETE then raises (mid-abort
    Redis blip), the lock stays held while the barrier keys are NOT
    deleted. Every sibling ``barrier_abort`` would then hit the
    dedup early-exit and do nothing, leaving the counter alive for
    in-flight successful tasks to DECR to 0 → callback fires with
    partial results → silent success masking. To close this hole,
    we explicitly release the abort_lock if the DELETE raises, so
    a sibling abort can re-acquire it and complete the cleanup.
    """
    redis_client = _get_redis_client()
    # ``SET NX EX`` — first-write-wins with auto-expiry. TTL matches
    # the barrier keys' TTL so the lock cleans up alongside them.
    # The lock is also explicitly DEL'd by ``enqueue`` at the start
    # of any new execution with the same execution_id, to prevent a
    # stale lock from masking a retry's failure as success.
    if not redis_client.set(
        _abort_lock_key(execution_id), "1", ex=_key_ttl_seconds(), nx=True
    ):
        # Another barrier_abort for this execution already won the
        # SET NX race. Silently exit — no log, no Sentry, no
        # duplicate DEL.
        return {
            "status": "deduplicated",
            "execution_id": execution_id,
        }
    try:
        redis_client.delete(
            _remaining_key(execution_id),
            _results_key(execution_id),
        )
    except Exception:
        # DELETE failed AFTER we won the SET NX. Release the lock so
        # subsequent aborts aren't dedup-suppressed into no-ops while
        # the barrier keys still exist. ``suppress`` because if the
        # lock-release also fails, the original DELETE exception is
        # the more useful one to propagate (Redis is clearly in
        # trouble and the original error captures that).
        with contextlib.suppress(Exception):
            redis_client.delete(_abort_lock_key(execution_id))
        raise
    logger.error(
        f"[exec:{execution_id}] Header task failed; barrier aborted. "
        f"Cleaned up remaining/results keys. exc={exc!r}"
    )
    return {
        "status": "aborted",
        "execution_id": execution_id,
        "reason": str(exc),
    }
