"""PG queue consumer — claims tasks from ``pg_queue_message`` and runs them.

The producer side enqueues a :class:`~queue_backend.pg_queue.TaskPayload`
when a task is routed to PG. This is the other half: it polls the queue with
``SKIP LOCKED`` + a visibility timeout (via :class:`PgQueueClient`), runs each
claimed task **in-process** (no Celery broker), and acks by deleting the row.

A task that fails — or a crash before ack — is redelivered once its ``vt``
expires (at-least-once; tasks must be idempotent), bounded by ``max_attempts``
(``read_ct``): a task that keeps failing past the cap is dropped as a poison
message (logged with its payload) rather than redelivered forever. A message
with no ``task_name`` (malformed/foreign) or a name not in the registry can
never run, so it is likewise dropped with a loud log. The fairness header is
rebuilt from the payload so a PG-routed run mirrors the Celery dispatch path.

In production this runs under the ``pg_queue_consumer`` supervisor
(``python -m pg_queue_consumer`` / ``./run-worker.sh pg-queue-consumer``),
which preforks N of these for parallel file batches; this module's ``main()``
runs a single consumer directly (config via env). The worker bootstrap must
have imported/registered the Celery tasks so they resolve in
``current_app.tasks``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Iterator
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from celery import current_app

from unstract.core.data_models import ContinuationSpec, TaskPayload

from ..barrier import callback_recovery_identity
from ..fairness import FAIRNESS_HEADER_NAME
from .client import PgQueueClient
from .connection import CONN_DEAD_ERRORS
from .liveness import LivenessServer as _BaseLivenessServer
from .result_backend import PgResultBackend
from .task_payload import to_payload

if TYPE_CHECKING:
    from celery import Celery
    from shared.api import InternalAPIClient

    from .client import QueueMessage

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_DEFAULT_QUEUE = "default"
# Default 1: the whole batch shares one vt window (set atomically at claim),
# but messages run sequentially — so with batch_size > 1 the tail can exceed
# its vt and be re-claimed mid-run (double-run). Batching is opt-in; if you
# raise it, keep vt_seconds > batch_size x worst-case task duration.
_DEFAULT_BATCH = 1
_DEFAULT_VT_SECONDS = 30
# Renewable-lease claim window. A claimed message is hidden for only
# this long; a background thread renews it (~every LEASE/3) while the task runs, so a
# live-but-slow task stays claimed but a DEAD worker's claim expires in ~LEASE →
# redelivery in minutes instead of the full VT. VT_SECONDS is now the drain /
# max-runtime bound (grace, health-stale), NOT the claim window.
_DEFAULT_LEASE_SECONDS = 120
# Bounded join so a wedged renewal thread can't block the ack — it's a daemon and
# dies with the process regardless.
_LEASE_JOIN_TIMEOUT_SECONDS = 10.0
_DEFAULT_POLL_INTERVAL = 0.1
_DEFAULT_BACKOFF_MAX = 2.0
# A task claimed more than this many times keeps failing — drop it (poison)
# rather than redeliver forever.
_DEFAULT_MAX_ATTEMPTS = 5
# When a poison drop's terminal-ERROR mark can't be confirmed (backend down), the
# message is re-parked this long instead of deleted into a void — so the drop
# never races a dead backend. Comfortably above a brief backend restart.
_DEFAULT_POISON_REPARK_VT_SECONDS = 300
# ...and give up (delete despite an unconfirmed mark, leaving the reaper as the
# last net) after this many extra reads past max_attempts, so a permanently
# unmarkable pipeline message can't re-park forever.
_DEFAULT_POISON_REPARK_BUDGET = 5
# Retention for the pg_task_result rows the REST task_status poll reads.
# 24h (Celery's default result_expires) — the 1h default would expire a completed
# task's row while a late poll (a browser resumed from sleep, an API client checking
# back) is still querying it. Completed rows are status-only (no payload); FAILED rows
# carry the executor error text, which can embed document content (cf. the _forget_sql
# note in result_backend.py) — accepted at this horizon because that same
# text is already shown to the owner via the WebSocket event + the task_status
# response, and the row is TTL'd.
_TASK_STATUS_RETENTION_SECONDS = 86400
# Liveness: a poll loop that hasn't cycled in this many seconds is reported
# unhealthy. The heartbeat is stamped at the top of each poll_once and frozen
# during task execution, so this threshold doubles as an UPPER BOUND on a single
# task's wall-clock: a task running longer than it trips the probe → pod restart
# → the in-flight task is killed and (at-least-once) redelivered. 60s suits the
# current sub-second leaf (send_webhook_notification); for longer-running tasks,
# raise WORKER_PG_QUEUE_CONSUMER_HEALTH_STALE_SECONDS above
# max(batch_size x worst_case_task_seconds, backoff_max).
_DEFAULT_HEALTH_STALE_SECONDS = 60.0


def _json_safe(value: object) -> object:
    """Round-trip through JSON with ``default=str`` so non-JSON-native values
    (UUID / datetime) survive a self-chained enqueue.

    ``PgQueueClient.send`` serialises with a plain ``json.dumps`` (no
    ``default=``), so a self-chained continuation whose prepended argument is an
    executor result dict containing a UUID/datetime would raise ``TypeError`` —
    swallowed by ``_chain_continuation`` and the callback (plus its user-facing
    event) lost. Coercing here mirrors the backend producer's ``_json_safe``.
    """
    return json.loads(json.dumps(value, default=str))


class _PoisonMarkOutcome(Enum):
    """Result of trying to mark a poison-dropped execution ERROR (drives whether
    the consumer drops the message now or re-parks it).
    """

    CONFIRMED = "confirmed"  # marked terminal → safe to drop the message
    UNMARKABLE = "unmarkable"  # permanent (no org) → drop now; re-park can't help
    TRANSIENT = "transient"  # backend down / client build failed → re-park


# Fire-and-forget tasks that carry their identity POSITIONALLY (in ``args``, not
# ``kwargs`` / ``_barrier_context``), mapped to ``(execution_id_index,
# organization_id_index)``. ``async_execute_bin`` is dispatched
# ``args=[schema_name, workflow_id, execution_id, hash_values]`` by the backend
# (workflow_helper._dispatch_orchestrator_task) — keep this map in step with that
# arg layout. Its poison drop happens BEFORE the barrier is armed AND before the
# orchestration claim is taken (a circuit-breaker-open drop, or repeated pre-claim
# failures), so the strand has NO ``pg_barrier_state`` row and NO
# ``pg_orchestration_claim`` row: it is invisible to every reaper sweep. Without
# recovering the execution_id here the poison drop can only bare-delete → the
# execution hangs EXECUTING forever with no handle. ``args[0]`` (org schema)
# doubles as the org.
_POSITIONAL_IDENTITY_ARGS: dict[str, tuple[int, int]] = {
    "async_execute_bin": (2, 0),
}


def _positional_identity(payload: TaskPayload) -> tuple[str | None, str | None]:
    """``(execution_id, organization_id)`` from a positional-args orchestration
    payload, keyed off the payload's own ``task_name`` (no separate arg to drift
    from it). ``(None, None)`` when the task doesn't carry identity positionally, or
    ``args`` is not a sequence / is too short (defensive — a malformed payload must
    not ``IndexError`` on the poison-drop path). See :data:`_POSITIONAL_IDENTITY_ARGS`.
    """
    indices = _POSITIONAL_IDENTITY_ARGS.get(payload.get("task_name") or "")
    if indices is None:
        return (None, None)
    args = payload.get("args") or []
    exec_idx, org_idx = indices
    # Bounds- AND type-check before ANY indexing: a short or non-sequence ``args``
    # returns (None, None) rather than indexing (no IndexError/TypeError path).
    if not isinstance(args, (list, tuple)) or len(args) <= max(exec_idx, org_idx):
        return (None, None)
    return (args[exec_idx], args[org_idx])


def _pipeline_identity(payload: TaskPayload) -> tuple[str | None, str]:
    """Best-effort ``(execution_id, organization_id)`` from a fire-and-forget
    payload, for marking the execution ERROR on a poison drop.

    The identity lives in one of four places, tried in order: directly on a
    callback payload's ``kwargs`` (the aggregating-callback case — the sharpest
    strand); on the injected ``_barrier_context``'s callback descriptor (a
    pipeline header); the org on the ``fairness`` payload; or — for orchestration
    messages, which pass identity POSITIONALLY — the task's ``args`` (see
    :func:`_positional_identity`). The callback-
    descriptor dig goes through :func:`callback_recovery_identity` so it can't
    drift from the barrier abort site. Returns ``(None, "")`` when the payload
    isn't a pipeline message — nothing to mark. ``organization_id`` may be ``""``
    even with an ``execution_id`` (the caller drops, since the status API is
    org-scoped and re-parking can't conjure an org).
    """
    kwargs = payload.get("kwargs") or {}
    barrier_ctx = kwargs.get("_barrier_context") or {}
    cb_execution_id, cb_org = callback_recovery_identity(
        barrier_ctx.get("callback_descriptor") or {}
    )
    pos_execution_id, pos_org = _positional_identity(payload)
    execution_id = (
        kwargs.get("execution_id")
        or barrier_ctx.get("execution_id")
        or cb_execution_id
        or pos_execution_id
    )
    organization_id = (
        kwargs.get("organization_id")
        or cb_org
        or (payload.get("fairness") or {}).get("org_id")
        or pos_org
    )
    return (
        str(execution_id) if execution_id else None,
        str(organization_id or ""),
    )


class PgQueueConsumer:
    """Polls one PG queue, runs each claimed task in-process, acks on success."""

    def __init__(
        self,
        queue_names: list[str],
        *,
        client: PgQueueClient | None = None,
        app: Celery | None = None,
        api_client: InternalAPIClient | None = None,
        batch_size: int = _DEFAULT_BATCH,
        vt_seconds: int = _DEFAULT_VT_SECONDS,
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        poison_repark_vt_seconds: int = _DEFAULT_POISON_REPARK_VT_SECONDS,
        poison_repark_budget: int = _DEFAULT_POISON_REPARK_BUDGET,
    ) -> None:
        # Validate at construction so a misconfigured consumer fails here
        # rather than batch-after-batch once the loop starts.
        for name, value in (
            ("batch_size", batch_size),
            ("vt_seconds", vt_seconds),
            ("lease_seconds", lease_seconds),
            ("poll_interval", poll_interval),
            ("backoff_max", backoff_max),
            ("max_attempts", max_attempts),
            ("poison_repark_vt_seconds", poison_repark_vt_seconds),
            ("poison_repark_budget", poison_repark_budget),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")
        if backoff_max < poll_interval:
            # Otherwise min(poll_interval*2, backoff_max) shrinks the backoff
            # below poll_interval — it would decrease instead of grow.
            raise ValueError(
                f"backoff_max ({backoff_max}) must be >= poll_interval ({poll_interval})"
            )
        if not queue_names:
            raise ValueError("queue_names must be a non-empty list")
        # One process can drain several queues (9f) — e.g. a file_processing
        # consumer drains both file_processing and api_file_processing. Each is
        # read once per cycle in list order (poll_once): this prevents starvation
        # (every queue gets a read each cycle) but does NOT equalize throughput —
        # an always-full queue_names[0] claims its full batch and runs it before
        # later queues. Copy + de-dup (order-preserving): a duplicate would
        # double-read a queue per cycle, and storing the caller's list by
        # reference would let a later mutation bypass the non-empty validation.
        self.queue_names = list(dict.fromkeys(queue_names))
        self._client = client if client is not None else PgQueueClient()
        self._app = app if app is not None else current_app
        # Lazily built the first time a poison drop needs to mark an execution
        # ERROR (fire-and-forget consumers with no poison never build it); an
        # injected client short-circuits the build (tests / DI).
        self._api_client = api_client
        self.batch_size = batch_size
        self.vt_seconds = vt_seconds
        # Renewable lease: the claim is taken for a short LEASE and renewed
        # every ~lease/3 while a task runs, so a dead worker's claim expires in ~LEASE
        # (fast redelivery) but a live one is never redelivered. VT_SECONDS is the
        # drain / max-runtime bound; a lease longer than it is meaningless, so clamp —
        # loudly, since a lease > VT is a misconfig, not a silent no-op.
        self.lease_seconds = min(lease_seconds, vt_seconds)
        if lease_seconds > vt_seconds:
            logger.warning(
                "WORKER_PG_QUEUE_CONSUMER_LEASE_SECONDS=%s > VT_SECONDS=%s; clamped the "
                "claim window to %ss (the lease can't outlast the max-runtime bound)",
                lease_seconds,
                vt_seconds,
                self.lease_seconds,
            )
        self._lease_renew_interval = max(1, self.lease_seconds // 3)
        # The renewal only extends the IN-FLIGHT message; a batch tail sits claimed but
        # unrenewed, so with batch>1 a slow head lets the tail's lease lapse and another
        # consumer double-runs it. Force serial claims whenever the lease is the short
        # (renewed) claim window; batch>1 stays available when lease == vt (no renewal).
        if self.batch_size > 1 and self.lease_seconds < vt_seconds:
            logger.warning(
                "WORKER_PG_QUEUE_CONSUMER_BATCH_SIZE=%s forced to 1: the renewable lease "
                "only covers the in-flight message, so a batch tail could lapse and "
                "double-run",
                self.batch_size,
            )
            self.batch_size = 1
        self.poll_interval = poll_interval
        self.backoff_max = backoff_max
        self.max_attempts = max_attempts
        self._poison_repark_vt_seconds = poison_repark_vt_seconds
        self._poison_repark_budget = poison_repark_budget
        self._running = False
        # Request-reply (executor RPC) result store — lazily created the first
        # time a message carries a ``reply_key``; fire-and-forget consumers
        # (orchestrator/fileproc/callback/scheduler) never instantiate it.
        self._result_backend: PgResultBackend | None = None
        # Heartbeat for the liveness probe: monotonic timestamp of the most
        # recent poll attempt. Seeded at construction so a just-started consumer
        # reads healthy. Updated at the TOP of poll_once, so a loop wedged on a
        # long-running task (poll_once not returning) goes stale and is caught —
        # something pgrep-based --status and the launch-time check cannot see.
        self._last_poll_monotonic = time.monotonic()

    def poll_once(self) -> int:
        """Claim + process one batch per queue (read once each, in list order);
        returns the total number of messages claimed across all queues this cycle.

        Each queue is isolated: a read/handle failure on one queue is logged and
        skipped so the others still get their turn, and the work already done this
        cycle still counts (so run() doesn't take the empty-queue backoff path
        after a partial failure).
        """
        self._last_poll_monotonic = time.monotonic()
        total = 0
        for queue_name in self.queue_names:
            try:
                messages = self._client.read(
                    queue_name, vt_seconds=self.lease_seconds, qty=self.batch_size
                )
                for message in messages:
                    self._handle(message)
                total += len(messages)
            except Exception:
                logger.exception(
                    "PG-queue consumer: poll failed for queue %r; "
                    "continuing with the other queues",
                    queue_name,
                )
        return total

    @contextlib.contextmanager
    def _lease_renewal(self, msg_id: int) -> Iterator[None]:
        """Keep ``msg_id``'s claim alive while a task runs.

        Starts a daemon thread that renews the short lease (``set_vt``) every
        ``lease/3`` — so a live-but-slow task stays claimed — then signals stop and
        joins on exit, before the caller acks. If the worker DIES, the thread dies
        with it → the lease expires in ~``lease_seconds`` → the message redelivers in
        minutes instead of the full VT. The join is bounded by
        ``_LEASE_JOIN_TIMEOUT_SECONDS``; a thread still alive after that (wedged in a
        stalled ``set_vt``) is logged and abandoned — it owns its own connection (see
        the loop), so it can't corrupt the ack path, and a late ``set_vt`` on the
        about-to-be-acked row is a benign no-op.
        """
        stop = threading.Event()
        thread = threading.Thread(
            target=self._renew_lease_loop,
            args=(msg_id, stop),
            name=f"pg-lease-{msg_id}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=_LEASE_JOIN_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.error(
                    "PG-queue consumer: lease-renewal thread for msg_id=%s did not "
                    "stop within %ss — proceeding to ack; its connection is abandoned "
                    "until the process exits",
                    msg_id,
                    _LEASE_JOIN_TIMEOUT_SECONDS,
                )

    def _make_renew_client(self) -> PgQueueClient:
        """Factory for the renewal thread's own connection (patched in tests)."""
        return PgQueueClient()

    def _renew_lease_loop(self, msg_id: int, stop: threading.Event) -> None:
        """Renew ``msg_id``'s claim every ``_lease_renew_interval`` until ``stop``.

        Waits *then* renews (the initial claim already set the lease), so a task
        shorter than the interval never renews and opens no second connection. Owns its
        connection start-to-finish (closed on exit) — never shared with the main
        thread's claim/ack client. Best-effort: a connection death is retried next tick
        (the interval leaves ~2x slack before expiry), but if it keeps failing past
        ``lease_seconds`` the lease is genuinely lost (the row can be reclaimed) and it
        escalates to ERROR. A ``False`` return means the row was already deleted — and
        since the ack runs only after this thread is joined, that means another consumer
        reclaimed + acked it, i.e. this task is double-running: logged, then stop. A
        non-connection error is left to propagate (fail loud, not swallowed forever).
        """
        client: PgQueueClient | None = None
        last_ok = time.monotonic()
        try:
            while not stop.wait(self._lease_renew_interval):
                try:
                    # Built on the FIRST renewal (not on thread start), so a task
                    # shorter than the interval opens no second connection.
                    if client is None:
                        client = self._make_renew_client()
                    if not client.set_vt(msg_id, self.lease_seconds):
                        logger.warning(
                            "PG-queue consumer: lease for msg_id=%s lost (row already "
                            "gone) — it was reclaimed and this task may double-run",
                            msg_id,
                        )
                        return
                    last_ok = time.monotonic()
                except CONN_DEAD_ERRORS:
                    down_for = time.monotonic() - last_ok
                    if down_for >= self.lease_seconds:
                        logger.exception(
                            "PG-queue consumer: lease renewal for msg_id=%s failing for "
                            "%.0fs (>= lease %ss) — the lease has likely expired and "
                            "this task may double-run",
                            msg_id,
                            down_for,
                            self.lease_seconds,
                        )
                    else:
                        logger.warning(
                            "PG-queue consumer: lease renewal for msg_id=%s failed "
                            "(retry in %ss; %.0fs of %ss slack used) — a dead "
                            "connection self-heals on the next tick",
                            msg_id,
                            self._lease_renew_interval,
                            down_for,
                            self.lease_seconds,
                            exc_info=True,
                        )
        finally:
            if client is not None:
                with contextlib.suppress(Exception):
                    client.close()

    def _resolve_runnable_task(
        self, message: QueueMessage, payload: TaskPayload, task_name: str | None
    ) -> Any | None:
        """Return the task to run, or drop+ack the message and return None.

        Collapses the three terminal-drop guards — malformed (no ``task_name``),
        poison (re-claimed past the cap), and unknown (named but unregistered) —
        each of which acks the message so it is never redelivered. Extracted from
        ``_handle`` to keep that method's cognitive complexity within budget.
        """
        # Malformed / foreign payload: no task name → can't run; drop with a
        # log that points at the payload, not at task registration.
        if not task_name:
            logger.error(
                "PG-queue consumer: payload missing task_name (msg_id=%s) — "
                "dropping malformed message: %r",
                message.msg_id,
                payload,
            )
            self._fail_dispatch(payload, error="malformed message: missing task_name")
            self._client.delete(message.msg_id)
            return None

        # Poison message: a task re-claimed past the cap keeps failing. Drop
        # it (with the payload, so it's recoverable from logs) instead of
        # redelivering on every vt expiry forever.
        if message.read_ct > self.max_attempts:
            self._drop_poison_message(message, payload, task_name)
            return None

        task = self._app.tasks.get(task_name)
        if task is None:
            # A named-but-unregistered task can never run → drop and shout.
            logger.error(
                "PG-queue consumer: unknown task %r (msg_id=%s) — dropping",
                task_name,
                message.msg_id,
            )
            self._fail_dispatch(payload, error=f"unknown task {task_name}")
            self._client.delete(message.msg_id)
            return None

        return task

    def _handle(self, message: QueueMessage) -> None:
        payload = message.message
        task_name = payload.get("task_name")
        # Request-reply (executor RPC): a unique key the dispatching caller is
        # blocking on. Read up front so the drop branches below can store a
        # definitive failure reply (the caller fails fast instead of blocking to
        # its full timeout). Present → store the outcome + ack after one attempt;
        # absent → fire-and-forget (the existing leaf/pipeline path).
        reply_key = payload.get("reply_key")
        # Async/callback (dispatch_with_callback) self-chaining (③c): a callback
        # to enqueue after the task runs (on_success after success, on_error after
        # failure) — the PG analogue of Celery firing a link/link_error. Mutually
        # exclusive with reply_key. ``task_id`` is the dispatch id prepended to the
        # on_error callback as the failed id (Celery link_error parity).
        on_success = payload.get("on_success")
        on_error = payload.get("on_error")

        # Validate the claimed message is runnable; a malformed / poison /
        # unknown-task message is dropped+acked inside the helper (returns None).
        task = self._resolve_runnable_task(message, payload, task_name)
        if task is None:
            return

        try:
            # Run the task body in-process (eager), carrying the fairness
            # header so a PG-routed run mirrors the Celery dispatch path.
            fairness = payload.get("fairness")
            headers = {FAIRNESS_HEADER_NAME: fairness} if fairness else None
            # Renew the short lease while the (possibly long) task runs, so a dead
            # worker's claim expires fast but a live one is never redelivered.
            with self._lease_renewal(message.msg_id):
                eager = task.apply(
                    args=payload.get("args") or [],
                    kwargs=payload.get("kwargs") or {},
                    headers=headers,
                    throw=True,
                )
        except Exception as exc:
            if reply_key or on_success or on_error:
                # Request-reply / async-callback dispatch: surface the failure on
                # its return channel (store the error reply, or self-chain on_error
                # carrying the real error text), then ACK regardless. We do NOT
                # vt-redeliver: a redelivery would race a result the caller may
                # already have consumed, and re-running the executor is costly
                # (LLM spend). The executor task's own autoretry covers transient
                # errors within this attempt; the caller re-dispatches with a fresh
                # handle to retry the whole RPC. ``on_success`` is in the guard too:
                # an on_success-only callback dispatch (on_error omitted) that raises
                # must still ACK — falling through to vt-redelivery would re-run the
                # executor (the LLM double-spend this path exists to avoid).
                # _fail_dispatch is best-effort, so the ack never wedges.
                self._fail_dispatch(payload, error=f"{type(exc).__name__}: {exc}")
                self._client.delete(message.msg_id)  # ack
                logger.exception(
                    "PG-queue consumer: dispatch %r (msg_id=%s) failed — surfaced "
                    "via reply/on_error + acked",
                    task_name,
                    message.msg_id,
                )
                return
            # Fire-and-forget: leave the row — its vt expires and it is
            # redelivered (bounded by max_attempts above).
            logger.exception(
                "PG-queue consumer: task %r (msg_id=%s, read_ct=%s) failed — "
                "leaving for vt-expiry redelivery",
                task_name,
                message.msg_id,
                message.read_ct,
            )
            return

        if reply_key:
            # Persist the result for the waiting caller before ack. Guarded: a
            # store failure must NOT leave the message for vt-redelivery — that
            # re-runs the executor (real LLM spend) and blocks the caller to its
            # full timeout. Log loudly and ack anyway; the caller degrades to a
            # timeout (rare), but we never double-spend.
            try:
                self._store_reply(reply_key, result=eager.result)
            except Exception:
                logger.exception(
                    "PG-queue consumer: FAILED to store request-reply result "
                    "(task=%r msg_id=%s reply_key=%s) — acking anyway to avoid an "
                    "expensive re-run; caller will time out",
                    task_name,
                    message.msg_id,
                    reply_key,
                )
        elif on_success:
            # Async/callback: self-chain the success continuation onto the callback
            # queue before the ack — the callback hand-off (PG analogue of Celery's link).
            #
            # "success" == the task did not RAISE (parity with Celery `link`, which
            # also fires on any non-exception return). A task that *returns* a failed
            # ExecutionResult (success=False, no raise) deliberately follows this
            # path — the on_success callback receives the failed result and renders
            # it — exactly as on Celery. This is NOT the missing-on_error drop bug
            # the early-drop branches handle.
            #
            # If the success hand-off can't be enqueued (transport/DB error, bad
            # queue), fall back to on_error so the HTTP-202 caller still gets a
            # terminal event instead of hanging after the LLM spend already
            # happened. Both are best-effort + still ack (no executor re-run).
            if not self._chain_continuation(
                on_success, prepend=eager.result, payload=payload
            ):
                self._fail_dispatch(
                    payload, error="result delivery failed; see worker logs"
                )

        if not self._client.delete(message.msg_id):  # ack
            logger.warning(
                "PG-queue consumer: ack found no row for task %r (msg_id=%s) — "
                "it likely exceeded vt and was re-claimed (possible double-run)",
                task_name,
                message.msg_id,
            )

    def _store_reply(
        self, reply_key: str, *, result: dict | None = None, error: str | None = None
    ) -> None:
        """Persist a request-reply task's outcome to ``pg_task_result``.

        Lazily opens the result-backend connection on first use (so only the
        executor consumer pays for it). ``store_result`` is idempotent
        (first-write-wins), so a redelivery before the original ack is harmless.
        """
        if self._result_backend is None:
            self._result_backend = PgResultBackend()
        self._result_backend.store_result(reply_key, result=result, error=error)

    def _record_task_status(
        self, payload: TaskPayload, *, error: str | None, executor_result: object
    ) -> None:
        """Record a ``dispatch_with_callback`` task's terminal status in
        ``pg_task_result`` so the REST ``PromptStudio.task_status`` poll resolves
        under the PG transport — the eager PG executor never writes a Celery
        result backend under the dispatch id, so ``AsyncResult`` alone would poll
        "processing" forever.

        Keyed by the dispatch ``task_id``; ``completed`` unless the run raised
        (``error`` set) or the executor reported an application failure
        (``executor_result["success"]`` false). Status-only + PII-free (no payload
        stored) + TTL'd. Best-effort — never raises, so it can't wedge the ack.
        """
        task_id = payload.get("task_id")
        if not task_id:
            return
        executor_failed = isinstance(executor_result, dict) and not executor_result.get(
            "success", True
        )
        try:
            with PgResultBackend() as rb:
                if error is not None or executor_failed:
                    msg = (
                        error
                        or (
                            executor_result.get("error")
                            if isinstance(executor_result, dict)
                            else None
                        )
                        or "Task failed"
                    )
                    rb.store_result(
                        task_id,
                        error=msg,
                        retention_seconds=_TASK_STATUS_RETENTION_SECONDS,
                    )
                else:
                    rb.store_result(
                        task_id,
                        result={},  # status-only → completed (PII-free)
                        retention_seconds=_TASK_STATUS_RETENTION_SECONDS,
                    )
        except Exception:
            logger.exception(
                "PG-queue consumer: could not record pg_task_result status for task "
                "%s — the REST task_status poll may report 'processing'",
                task_id,
            )

    def _chain_continuation(
        self,
        spec: ContinuationSpec,
        *,
        prepend: object,
        payload: TaskPayload,
        error: str | None = None,
    ) -> bool:
        """Enqueue a self-chained callback continuation (best-effort, never raises).

        The PG analogue of Celery firing a ``link`` / ``link_error``: after the
        executor task runs, enqueue ``spec`` (``task_name`` + ``kwargs`` +
        ``queue``) onto its queue with ``prepend`` as the first positional arg —
        the executor result dict on success, the dispatch ``task_id`` on error —
        exactly the first parameter the callback signature expects (mirroring
        Celery prepending the parent task's return value). The prepended value is
        JSON-coerced so a UUID/datetime in an executor result can't make the
        enqueue's ``json.dumps`` raise and silently drop the callback.

        ``error`` (failure path only): the real error text. On PG there is no
        Celery ``AsyncResult`` for the on_error callback (e.g. ``ide_prompt_error``)
        to recover the message from — the executor ran eagerly — so we hand it
        through ``callback_kwargs['error']``, which those callbacks prefer over the
        empty ``AsyncResult`` lookup. Absent on the success path.

        Returns ``True`` if the continuation was enqueued, ``False`` if it failed.
        Never raises: a failure here must not wedge the executor message's ack
        (which is taken regardless, to avoid an expensive re-run). The success path
        uses the return value to fall back to on_error so the caller still gets a
        terminal event; the failure path can't recover further (the callback — and
        its user-facing WebSocket event — is lost, logged loud with the run/task/org
        so the stranded session is correlatable).
        """
        # Record the terminal status for the REST PromptStudio.task_status poll
        # before the enqueue, so it resolves under PG even if the callback
        # enqueue below fails. This self-chain is the single terminal choke point for
        # both success (``error`` None) and failure (``error`` set) of a callback
        # dispatch. The recorded status reflects the EXECUTOR outcome, not callback
        # delivery: on a rare on_success-enqueue-failure ``_fail_dispatch`` re-enters
        # here with on_error, but ``store_result`` is first-write-wins (ON CONFLICT DO
        # NOTHING) so the "completed" already written stands — a REST poll then reads
        # "completed" (the executor did succeed) even though the callback's socket
        # event / bookkeeping was lost. Accepted (the browser also relies on that
        # socket event, so this window is REST-poll-only and rare).
        self._record_task_status(payload, error=error, executor_result=prepend)
        try:
            queue = spec["queue"]
            kwargs = dict(spec.get("kwargs") or {})
            if error is not None:
                cb = dict(kwargs.get("callback_kwargs") or {})
                cb.setdefault("error", error)
                kwargs["callback_kwargs"] = cb
            self._client.send(
                queue,
                to_payload(
                    spec["task_name"],
                    args=[_json_safe(prepend)],
                    kwargs=kwargs,
                    queue=queue,
                ),
                org_id=self._continuation_org(payload),
            )
            return True
        except Exception:
            ctx = payload.get("args") or [{}]
            ctx0 = ctx[0] if ctx and isinstance(ctx[0], dict) else {}
            logger.exception(
                "PG-queue consumer: FAILED to self-chain continuation %r — the "
                "callback (and its user-facing event) is lost "
                "(run_id=%s task_id=%s org=%s)",
                spec.get("task_name") if isinstance(spec, dict) else spec,
                ctx0.get("run_id"),
                payload.get("task_id"),
                self._continuation_org(payload),
            )
            return False

    @staticmethod
    def _continuation_org(payload: TaskPayload) -> str:
        """Best-effort org id for a chained callback (fairness/debug on its queue).

        The executor request carries it in the context dict (``args[0]``);
        callbacks are not fairness-critical, so a missing/odd shape degrades to
        ``""`` (no org). The guards below cover every non-dict shape, so no
        try/except is needed.
        """
        args = payload.get("args") or []
        if args and isinstance(args[0], dict):
            return str(args[0].get("organization_id") or "")
        return ""

    def _fail_dispatch(self, payload: TaskPayload, *, error: str) -> None:
        """Surface a terminal dispatch failure on whichever return channel applies.

        Request-reply (``reply_key``) → store the error for the blocking caller.
        Async/callback (``on_error``) → self-chain the on_error continuation,
        carrying the real ``error`` text. Best-effort + never raises — the caller
        acks regardless. Used by BOTH the run-raised path and the early-drop
        branches (malformed / poison / unknown task), so a ``dispatch_with_callback``
        failure ALWAYS reaches its on_error callback, not only when the task body
        raised (the realistic poison-executor case is exactly when the user most
        needs the error surfaced).
        """
        reply_key = payload.get("reply_key")
        if reply_key:
            self._fail_reply(reply_key, error)
            return
        on_error = payload.get("on_error")
        if on_error:
            self._chain_continuation(
                on_error,
                prepend=payload.get("task_id") or "",
                payload=payload,
                error=error,
            )

    def _drop_poison_message(
        self, message: QueueMessage, payload: TaskPayload, task_name: str | None
    ) -> None:
        """Handle a message that exceeded ``max_attempts`` (poison).

        A message with a failure channel (``reply_key`` / ``on_error``) surfaces
        the failure there and is dropped — existing behavior. A pipeline header /
        barrier callback has neither but carries an ``execution_id``: a bare delete
        would silently strand the execution EXECUTING-forever (the barrier row is
        already gone → the reaper has no handle), so mark it ERROR first. The mark
        has three outcomes (see :class:`_PoisonMarkOutcome`): confirmed → drop;
        permanently unmarkable (no org) → drop now, since re-parking can never
        help; transient (backend down / client build failed) → re-park with a long
        vt rather than delete into a void, bounded by ``poison_repark_budget``.
        """
        execution_id, organization_id = _pipeline_identity(payload)
        logger.error(
            "PG-queue consumer: task %r (msg_id=%s) exceeded max_attempts=%s "
            "(read_ct=%s, execution_id=%s) — poison; full payload: %r",
            task_name,
            message.msg_id,
            self.max_attempts,
            message.read_ct,
            execution_id,
            payload,
        )
        # Failure channel (request-reply / on_error) → surface there, then drop.
        if payload.get("reply_key") or payload.get("on_error"):
            self._fail_dispatch(
                payload,
                error=f"task {task_name} exceeded max_attempts={self.max_attempts}",
            )
            self._client.delete(message.msg_id)
            return
        # No failure channel and not a pipeline message → nothing to mark; drop.
        if execution_id is None:
            self._client.delete(message.msg_id)
            return
        # Pipeline strand: mark ERROR so the failure is visible and re-runnable.
        outcome = self._mark_poison_execution_error(
            execution_id, organization_id, task_name
        )
        if outcome is _PoisonMarkOutcome.CONFIRMED:
            self._client.delete(message.msg_id)  # terminal → safe to drop
            return
        if outcome is _PoisonMarkOutcome.UNMARKABLE:
            # Permanent (no org): re-parking can never change the outcome, so drop
            # now rather than burn the whole budget. The full payload was logged
            # above for manual recovery.
            self._client.delete(message.msg_id)
            return
        # TRANSIENT (backend down / client build failed): re-park rather than
        # delete into a void, bounded so a permanently-stuck message can't re-park
        # forever. NOTE: the reaper only recovers executions that still have a
        # pg_barrier_state row; an aggregating-callback message is enqueued AFTER
        # that row is deleted, so on budget exhaustion here it has no reaper handle
        # and needs manual replay from the logged payload — the bound is a
        # backstop, not a guaranteed reaper recovery for the callback case.
        if message.read_ct > self.max_attempts + self._poison_repark_budget:
            logger.error(
                "PG-queue consumer: exhausted poison re-park budget for execution "
                "%s (msg_id=%s, read_ct=%s) — dropping with an unconfirmed ERROR "
                "mark. If this was an aggregating callback its barrier row is "
                "already gone, so the reaper cannot recover it: manual replay from "
                "the full payload logged above may be required.",
                execution_id,
                message.msg_id,
                message.read_ct,
            )
            self._client.delete(message.msg_id)
            return
        if not self._client.set_vt(message.msg_id, self._poison_repark_vt_seconds):
            # Row already gone (vt expired and another reader deleted it) — nothing
            # to re-park; don't log a re-park that didn't happen.
            logger.info(
                "PG-queue consumer: poison message %s already gone before re-park.",
                message.msg_id,
            )
            return
        logger.warning(
            "PG-queue consumer: could not confirm ERROR mark for poison execution "
            "%s (msg_id=%s, read_ct=%s) — re-parked for %ss instead of dropping.",
            execution_id,
            message.msg_id,
            message.read_ct,
            self._poison_repark_vt_seconds,
        )

    def _get_api_client(self) -> InternalAPIClient:
        # Lazy import + build (mirrors the reaper): keeps a fire-and-forget
        # consumer that never poisons free of the HTTP/env client, and avoids a
        # module-load import cycle via shared.api.
        if self._api_client is None:
            from shared.api import InternalAPIClient

            self._api_client = InternalAPIClient()
        return self._api_client

    def _mark_poison_execution_error(
        self, execution_id: str, organization_id: str, task_name: str | None
    ) -> _PoisonMarkOutcome:
        """Best-effort: mark a poison-dropped pipeline execution ERROR (+cascade).

        Returns a :class:`_PoisonMarkOutcome`: ``CONFIRMED`` when the backend
        confirmed the mark (safe to drop); ``UNMARKABLE`` when it can never be
        marked (no org to scope the status API — re-parking is pointless, drop
        now); ``TRANSIENT`` when the mark failed for a possibly-recoverable reason
        (backend down, or the API client couldn't be built) so the caller re-parks
        rather than dropping into a void.
        """
        if not organization_id:
            logger.error(
                "PG-queue consumer: poison message for execution %s carries no "
                "organization_id — cannot mark it ERROR via the org-scoped API; "
                "dropping now (re-parking cannot help). Manual recovery from the "
                "logged payload may be required.",
                execution_id,
            )
            return _PoisonMarkOutcome.UNMARKABLE
        try:
            api_client = self._get_api_client()
        except Exception:
            logger.exception(
                "PG-queue consumer: could not build the internal API client to "
                "mark poison execution %s ERROR — will re-park",
                execution_id,
            )
            return _PoisonMarkOutcome.TRANSIENT
        from .recovery import mark_execution_error

        confirmed = mark_execution_error(
            api_client,
            execution_id,
            organization_id,
            error_message=(
                f"[pg-poison-drop] task {task_name} exceeded "
                f"max_attempts={self.max_attempts}."
            ),
        )
        return _PoisonMarkOutcome.CONFIRMED if confirmed else _PoisonMarkOutcome.TRANSIENT

    def _fail_reply(self, reply_key: str | None, error: str) -> None:
        """Best-effort failure reply for a request-reply message that can't run
        or whose run raised (drop / poison / unknown-task / exception).

        No-op without a ``reply_key``; never raises — a store failure here must
        not wedge the drop/ack path (the message is acked regardless), it just
        means the caller degrades to a timeout instead of a fast definitive error.
        """
        if not reply_key:
            return
        try:
            self._store_reply(reply_key, error=error)
        except Exception:
            logger.exception(
                "PG-queue consumer: failed to store failure reply (reply_key=%s): %s",
                reply_key,
                error,
            )

    def _registered_task_count(self) -> int:
        """Count application tasks (excluding Celery's built-ins)."""
        return sum(1 for name in self._app.tasks if not name.startswith("celery."))

    def seconds_since_last_poll(self) -> float:
        """Seconds since the last poll attempt (for the liveness heartbeat)."""
        return time.monotonic() - self._last_poll_monotonic

    def run(self, *, install_signals: bool = True, require_tasks: bool = True) -> None:
        """Poll loop with empty-queue backoff and graceful shutdown.

        Refuses to start if no application tasks are registered — a strong
        signal the worker app wasn't bootstrapped, in which case *every*
        message would be dropped as "unknown task". This makes a
        misconfigured launch fail loudly instead of silently destroying data.
        """
        if require_tasks and self._registered_task_count() == 0:
            raise RuntimeError(
                "PG-queue consumer: no application tasks are registered — the "
                "worker app was not bootstrapped. Launch via "
                "`python -m pg_queue_consumer` (or ./run-worker.sh "
                "pg-queue-consumer), not bare "
                "`python -m queue_backend.pg_queue.consumer`. Refusing to start "
                "to avoid dropping every message as an unknown task."
            )
        self._running = True
        if install_signals:
            self._install_signal_handlers()
        # Log the registered application tasks at startup. The guard above only
        # catches an *empty* registry; a *wrong* one (e.g. the launcher selected
        # the wrong source worker type) is non-empty but missing the target
        # task, so each message would be dropped as "unknown task". Surfacing
        # the registry here makes a wrong-type boot diagnosable from one line.
        app_tasks = sorted(
            name for name in self._app.tasks if not name.startswith("celery.")
        )
        logger.info(
            "PG-queue consumer started (queues=%r, batch=%s, lease=%ss, vt=%ss) — "
            "%d application task(s) registered: %s",
            self.queue_names,
            self.batch_size,
            self.lease_seconds,
            self.vt_seconds,
            len(app_tasks),
            ", ".join(app_tasks) or "(none)",
        )
        backoff = self.poll_interval
        while self._running:
            try:
                claimed = self.poll_once()
            except Exception:
                # A transient read/DB blip must not tear down the loop — the
                # client self-recovers its connection, so log and back off.
                logger.exception(
                    "PG-queue consumer: poll cycle failed; backing off and continuing"
                )
                claimed = 0
            if claimed:
                backoff = self.poll_interval
            else:
                time.sleep(backoff)
                backoff = min(backoff * 2, self.backoff_max)
        logger.info("PG-queue consumer stopped (queues=%r)", self.queue_names)

    def stop(self, *_: object) -> None:
        """Request a graceful stop after the current batch."""
        self._running = False

    def _install_signal_handlers(self) -> None:
        # signal.signal only works in the main thread.
        try:
            signal.signal(signal.SIGTERM, self.stop)
            signal.signal(signal.SIGINT, self.stop)
        except ValueError:
            logger.warning(
                "PG-queue consumer: signal handlers not installed (non-main "
                "thread) — SIGTERM/SIGINT will not trigger graceful shutdown"
            )


def _parse_queue_list(raw: str) -> list[str]:
    """Comma-separated queue list (9f). A single value stays a one-element list,
    so the pre-9f single-queue config remains valid. Empty entries (a doubled or
    trailing comma — almost always a config typo) are dropped with a warning so a
    malformed list is diagnosable from the logs, not just by eyeballing.
    """
    parts = [q.strip() for q in raw.split(",")]
    queues = [q for q in parts if q]
    dropped = len(parts) - len(queues)
    if dropped:
        logger.warning(
            "PG-queue consumer: dropped %d empty queue name(s) from "
            "WORKER_PG_QUEUE_CONSUMER_QUEUE=%r → %r",
            dropped,
            raw,
            queues,
        )
    return queues


def consumer_env(suffix: str, default: _T, cast: Callable[[str], _T]) -> _T:
    """Read ``WORKER_PG_QUEUE_CONSUMER_<suffix>`` with a typed default.

    Preserves the default's type through to PgQueueConsumer's typed ``__init__``
    (a bare ``type`` would erase it). On a bad value, fail with the offending var
    name instead of a context-free ``int('abc')`` ValueError. Treats empty-string
    as unset (an empty HEALTH_PORT must hit the clean opt-out, not ``int("")``).
    Module-level (not nested in ``main``) so the prefork supervisor reads the same
    knobs the single-process path does.
    """
    var = f"WORKER_PG_QUEUE_CONSUMER_{suffix}"
    raw = os.getenv(var)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {var}={raw!r}: {exc}") from exc


def build_consumer_from_env() -> PgQueueConsumer:
    """Construct a :class:`PgQueueConsumer` from the ``WORKER_PG_QUEUE_CONSUMER_*``
    env. Shared by ``main`` (single process) and the prefork supervisor's children,
    so every consumer instance is configured identically.
    """
    return PgQueueConsumer(
        queue_names=consumer_env("QUEUE", [_DEFAULT_QUEUE], _parse_queue_list),
        batch_size=consumer_env("BATCH", _DEFAULT_BATCH, int),
        vt_seconds=consumer_env("VT_SECONDS", _DEFAULT_VT_SECONDS, int),
        lease_seconds=consumer_env("LEASE_SECONDS", _DEFAULT_LEASE_SECONDS, int),
        poll_interval=consumer_env("POLL_INTERVAL", _DEFAULT_POLL_INTERVAL, float),
        backoff_max=consumer_env("BACKOFF_MAX", _DEFAULT_BACKOFF_MAX, float),
        max_attempts=consumer_env("MAX_ATTEMPTS", _DEFAULT_MAX_ATTEMPTS, int),
    )


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    consumer = build_consumer_from_env()
    # Annotate the int|None result so the intent ("a port, or None when unset") is
    # declared rather than recovered from the generic widening over default=None.
    port: int | None = consumer_env("HEALTH_PORT", None, int)
    health_server = _maybe_start_health_server(
        consumer,
        port=port,
        stale_after=consumer_env(
            "HEALTH_STALE_SECONDS", _DEFAULT_HEALTH_STALE_SECONDS, float
        ),
    )
    try:
        consumer.run()
    finally:
        if health_server is not None:
            health_server.stop()


def _maybe_start_health_server(
    consumer: PgQueueConsumer, *, port: int | None, stale_after: float
) -> LivenessServer | None:
    """Start the liveness server when ``port`` is not None; else ``None``.

    ``main()`` wires ``port`` from ``WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT`` (unset
    → ``None`` → no server, no stray port). A bind failure degrades gracefully:
    the probe is auxiliary, so it must never stop the consumer from draining the
    queue — we log and continue probe-less rather than abort startup.
    """
    if port is None:
        logger.info(
            "PG-queue consumer: WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT unset — "
            "liveness server disabled"
        )
        return None
    server = LivenessServer(consumer, port=port, stale_after=stale_after)
    try:
        server.start()
    except OSError:
        logger.exception(
            "PG-queue consumer: liveness server could not bind :%s — "
            "continuing WITHOUT a probe",
            port,
        )
        return None
    logger.info(
        "PG-queue consumer: liveness server on :%s/health (stale after %ss)",
        server.bound_port,
        stale_after,
    )
    return server


class LivenessServer(_BaseLivenessServer):
    """Consumer poll-loop liveness — a thin wrapper over the shared
    :class:`queue_backend.pg_queue.liveness.LivenessServer`, bound to the
    consumer's heartbeat (``seconds_since_last_poll``). Same wire shape as before
    (``/health`` → 200 fresh / 503 stale, ``check="pg_queue_poll"``), plus
    ``/metrics`` exporting that heartbeat as a scrapeable gauge.
    """

    def __init__(
        self, consumer: PgQueueConsumer, *, port: int, stale_after: float
    ) -> None:
        from .metrics import ConsumerMetrics

        metrics = ConsumerMetrics(freshness_fn=consumer.seconds_since_last_poll)
        super().__init__(
            freshness_fn=consumer.seconds_since_last_poll,
            stale_after=stale_after,
            port=port,
            check_name="pg_queue_poll",
            age_key="seconds_since_last_poll",
            metrics_fn=metrics.render,
            thread_name="pg-consumer-liveness",
            log_label="pg-queue consumer",
        )


if __name__ == "__main__":
    main()
