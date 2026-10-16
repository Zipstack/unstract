"""Redis-list consumer for the log stream (UN-3755).

Drains the list ``LogPublisher.publish()`` writes to when ``LOG_TRANSPORT=redis`` and
runs the **existing** ``logs_consumer`` task body against each envelope. Nothing about
what a log *does* changes here: the task still RPUSHes to ``log_history_queue`` and
emits over Socket.IO, and the log-history scheduler still drains that to
``execution_log``. This module replaces only the transport hop that RabbitMQ used to
provide, so the log consumer no longer needs a Celery deployment.

**Why a reliable-queue pattern rather than a bare BLPOP.** The Celery consumer runs with
``task_acks_late=True`` (``shared/infrastructure/config/worker_config.py:545``, and
``backend/celery_config.py:63``), so a worker that dies mid-task gets the message
redelivered. ``BLPOP`` deletes on read, which would silently make crashes lossy — a real
regression, not a no-op. ``BLMOVE`` instead parks the envelope on a per-pod *processing*
list and removes it only after the handler returns, and startup re-queues whatever the
previous incarnation left behind.

Bound worth knowing: recovery is keyed on ``HOSTNAME``, so a **container restart** (crash
loop, OOM kill — the dominant failure mode) recovers fully, while a **pod replacement**
strands that pod's in-flight envelopes, at most one per concurrent loop. That is strictly
better than BLPOP and, for a stream already discarded wholesale at its 10k cap, close
enough to the Celery behaviour it replaces. Sweeping other pods' lists is deliberately not
attempted: with multiple replicas it cannot distinguish a dead owner from a live one, and
would duplicate log lines on every start.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from types import FrameType
from typing import Any

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.logging import WorkerLogger

from unstract.core.cache.redis_client import create_redis_client
from unstract.core.constants import LogProcessingTask

logger = WorkerLogger.setup(WorkerType.LOG_CONSUMER)

# Build the Celery app before importing tasks: ``@worker_task`` is ``shared_task``, which
# binds to the current app at call time. Same ordering as ``log_consumer/worker.py``.
app, config = WorkerBuilder.build_celery_app(WorkerType.LOG_CONSUMER)

from log_consumer.tasks import logs_consumer  # noqa: E402

_QUEUE_NAME = os.getenv("LOG_STREAM_QUEUE_NAME", "log_stream_queue")
# BLMOVE blocks up to this long before returning None. Keep it well under the pod's
# terminationGracePeriodSeconds.
_BLOCK_TIMEOUT_SECONDS = int(os.getenv("LOG_STREAM_BLOCK_TIMEOUT", "5"))
# redis-py enforces ``socket_timeout`` on the BLMOVE read itself, so it MUST exceed the
# server-side block or every call aborts mid-block with ``redis.TimeoutError``.
# ``create_redis_client`` defaults it to 5s — exactly ``_BLOCK_TIMEOUT_SECONDS`` — and the
# socket won that race in integration: a traceback every ~5.01s while idle, plus a
# disconnect/reconnect each time. Worse, an envelope BLMOVE had already moved to the
# processing list was stranded there until this pod restarted, because the reply never
# reached the client. Identical trap to the one documented at
# ``workers/queue_backend/pg_queue/result_backend.py:152``.
_SOCKET_TIMEOUT_SECONDS = _BLOCK_TIMEOUT_SECONDS + 5
# Wait after a failed BLMOVE, doubling per consecutive failure up to the cap and reset by
# the next successful BLMOVE (an envelope or an idle None). Without it, a failure that
# returns at once — a refused connect, or an OOM/READONLY/MISCONF reply — spun the loop,
# logging a traceback each time: 0.7-1.7 GiB of Cloud Logging per minute, per pod
# (staging, Oct 2026). The loop never gives up, so a failure only a restart can fix —
# the client reads its credentials once, so a rotated password is one — keeps logging
# an ERROR every 30s until the pod is restarted.
_RECONNECT_BACKOFF_INITIAL_SECONDS = 1.0
_RECONNECT_BACKOFF_MAX_SECONDS = 30.0
# How often a backoff wait re-checks for a shutdown signal. Polling the flag rather than
# waiting on a threading.Event is deliberate: calling Event.set() from _handle_signal
# can, in a narrow race, deadlock against Event.wait() on this same thread.
_SHUTDOWN_POLL_SECONDS = 0.5

_shutdown = False


def _processing_list_name() -> str:
    """Per-pod parking list, so one pod never reclaims another's in-flight envelope."""
    return f"{_QUEUE_NAME}:processing:{os.getenv('HOSTNAME') or socket.gethostname()}"


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    """Finish the envelope in hand, then stop. Never abandon work mid-flight."""
    global _shutdown
    _shutdown = True
    logger.info("Signal %s received; finishing current log then shutting down", signum)


def _wait_before_reconnect(seconds: float) -> None:
    """Sleep up to ``seconds``, returning early once a shutdown signal has arrived.

    A plain ``time.sleep(seconds)`` would not do: since PEP 475 a sleep interrupted by a
    signal resumes once the handler returns, so SIGTERM mid-backoff would hold the pod
    for up to the full cap.
    """
    deadline = time.monotonic() + seconds
    while not _shutdown:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, _SHUTDOWN_POLL_SECONDS))


def _recover_in_flight(redis_client: Any, processing: str) -> None:
    """Re-queue anything this pod was mid-way through when it last died.

    LMOVE back to the *head* of the source list so recovered envelopes are re-processed
    before newer ones, preserving rough log ordering.
    """
    recovered = 0
    while redis_client.lmove(processing, _QUEUE_NAME, "RIGHT", "LEFT"):
        recovered += 1
    if recovered:
        logger.warning(
            "Recovered %d in-flight log envelope(s) from a previous run of this pod",
            recovered,
        )


def _dispatch(raw: bytes | str) -> None:
    """Run one envelope through the existing task body.

    Dispatches **by name** so a producer/consumer mismatch fails loudly here rather than
    silently discarding the message.
    """
    envelope = json.loads(raw)
    task_name = envelope.get("task")
    if task_name != LogProcessingTask.TASK_NAME:
        raise ValueError(
            f"Unexpected task {task_name!r} on '{_QUEUE_NAME}'; "
            f"expected {LogProcessingTask.TASK_NAME!r}"
        )
    logs_consumer(**envelope.get("kwargs", {}))


def run() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Not ``RedisQueueClient.from_env()``: that hard-codes the 5s socket timeout, which
    # cannot outlive this loop's block. Built directly so the two stay related by
    # construction — see _SOCKET_TIMEOUT_SECONDS.
    redis_client = create_redis_client(
        decode_responses=True,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
    )
    processing = _processing_list_name()
    logger.info(
        "Log stream consumer starting: queue='%s' processing='%s'",
        _QUEUE_NAME,
        processing,
    )

    backoff = _RECONNECT_BACKOFF_INITIAL_SECONDS
    recovered = False
    while not _shutdown:
        try:
            # Inside the try, so a failing startup LMOVE backs off like a failing BLMOVE.
            if not recovered:
                _recover_in_flight(redis_client, processing)
                recovered = True
            raw = redis_client.blmove(
                _QUEUE_NAME, processing, _BLOCK_TIMEOUT_SECONDS, "LEFT", "RIGHT"
            )
        except Exception:
            # Must not kill the pod, and must not be retried immediately: most such
            # failures recur at once. create_redis_client gives the client no retry
            # (redis-py's default Retry(NoBackoff(), 0)), a refused connect returns
            # without BLMOVE ever blocking, and an error reply (OOM, READONLY, MISCONF,
            # NOPERM) is just as instant.
            logger.error(
                "Log stream %s failed; backing off %.0fs before retrying",
                "read" if recovered else "recovery",
                backoff,
                exc_info=True,
            )
            # redis-py keeps the socket after an error reply, so a standalone client left
            # on a demoted primary would get READONLY forever. Disconnecting the pool's
            # connections makes the next attempt open a fresh one and re-resolve the
            # host.
            redis_client.connection_pool.disconnect()
            _wait_before_reconnect(backoff)
            backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX_SECONDS)
            continue

        # A successful BLMOVE, including an idle block's None, ends the failure streak.
        backoff = _RECONNECT_BACKOFF_INITIAL_SECONDS

        if raw is None:  # timeout, no work — loop so shutdown can be observed
            continue

        try:
            _dispatch(raw)
        except Exception:
            # Match the Celery consumer's posture: a poison envelope is logged and
            # dropped, never retried forever. logs_consumer already swallows its own
            # sink failures, so reaching here means a malformed envelope.
            logger.error("Discarding unprocessable log envelope", exc_info=True)
        finally:
            # Remove exactly one copy, whether it succeeded or was discarded — leaving it
            # parked would have it re-queued on the next restart and replayed forever.
            redis_client.lrem(processing, 1, raw)

    logger.info("Log stream consumer stopped")
    return 0


if __name__ == "__main__":
    sys.exit(run())
