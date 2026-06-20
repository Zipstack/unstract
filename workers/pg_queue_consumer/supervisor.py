"""Prefork supervisor for the PG-queue consumer (UN-3606).

Forks ``WORKER_PG_QUEUE_CONSUMER_CONCURRENCY`` copies of the single-threaded
:class:`~queue_backend.pg_queue.consumer.PgQueueConsumer` so multiple file
batches run in parallel — the PG analogue of Celery's ``--pool=prefork
--concurrency=N``. ``SELECT … FOR UPDATE SKIP LOCKED`` distributes work across the
children (and across replicas): each child claims distinct rows, and the cap on a
single execution is still ``MAX_PARALLEL_FILE_BATCHES`` (producer side). Total live
parallelism = ``concurrency × replicas``; k8s HPA scales the replica count.

**Process model** (matches Celery prefork — the cloud-trusted choice): each child
is a fully isolated process with its own DB connections and thread-local
``StateStore`` — no shared mutable state, no thread-safety surface. A child crash
is isolated and re-forked by the supervisor; its in-flight message redelivers via
``vt`` (at-least-once). The **consumer code is unchanged** — concurrency is purely
a launch concern.

**Health**: the supervisor owns the single liveness port and reports the *fleet's*
freshness — the staleness of the oldest-polling child (each child publishes its
last-poll wall-time into a shared array). A child that dies is re-forked
internally (transient); only a persistent failure (children that won't stay fresh)
sustains 503 → pod restart. Children do not bind the port themselves.

Used only when ``CONCURRENCY > 1``; ``CONCURRENCY = 1`` keeps the plain
single-process ``main()`` path (byte-identical to before this module existed).
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import os
import signal
import threading
import time

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 1
# Fork-bomb backstop for a fat-fingered env (a single machine can't usefully run
# hundreds of heavy file-processing children anyway — scale replicas instead).
_MAX_CONCURRENCY = 64
# How often each child republishes its heartbeat, and the parent reaps + checks.
_REPORT_INTERVAL_SECONDS = 1.0
_MONITOR_INTERVAL_SECONDS = 1.0
# Floor between a child's death and its re-fork — avoids a fork storm when a child
# dies on startup every time (e.g. a bad migration); the gap lets logs/alerts fire.
_RESTART_MIN_INTERVAL_SECONDS = 2.0
# How long to wait for children to drain on shutdown before giving up the join.
_SHUTDOWN_GRACE_SECONDS = 30.0


def concurrency_from_env() -> int:
    """Parse ``WORKER_PG_QUEUE_CONSUMER_CONCURRENCY`` (default 1, clamped to a sane
    max). 1 → the single-process path; >1 → the prefork supervisor.
    """
    raw = os.environ.get("WORKER_PG_QUEUE_CONSUMER_CONCURRENCY")
    if raw is None or raw == "":
        return _DEFAULT_CONCURRENCY
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid WORKER_PG_QUEUE_CONSUMER_CONCURRENCY={raw!r}: {exc}"
        ) from exc
    if n < 1:
        raise ValueError(f"WORKER_PG_QUEUE_CONSUMER_CONCURRENCY must be >= 1, got {n}")
    if n > _MAX_CONCURRENCY:
        logger.warning(
            "WORKER_PG_QUEUE_CONSUMER_CONCURRENCY=%s exceeds the %s cap; clamping "
            "(scale replicas for more parallelism, not one fat process)",
            n,
            _MAX_CONCURRENCY,
        )
        n = _MAX_CONCURRENCY
    return n


def _oldest_child_age(heartbeats) -> float:  # noqa: ANN001 (ctypes array)
    """Fleet staleness = seconds since the *oldest*-polling child last polled.

    The supervisor's liveness verdict: if the worst child has stalled past the
    threshold, the fleet probe goes 503. Empty fleet → 0 (fresh; nothing to judge).
    """
    now = time.time()
    return max((now - hb for hb in heartbeats), default=0.0)


def _run_child(slot: int, heartbeats) -> None:  # noqa: ANN001 (ctypes array)
    """Child entry: bootstrap the worker app, then run one consumer forever.

    The worker import (and any connections it opens) happens HERE, in the child —
    never inherited across the fork — so each process owns its own connections.
    A daemon thread publishes the consumer's last-poll wall-time into
    ``heartbeats[slot]`` for the supervisor's fleet liveness.
    """
    # Same source-worker selection the single-process launcher does (see
    # pg_queue_consumer/__main__.py): overwrite WORKER_TYPE before importing
    # ``worker``, which reads it at import time to register the right tasks.
    os.environ["WORKER_TYPE"] = os.environ.get(
        "WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE", "notification"
    )
    import worker  # noqa: F401 — side-effect: registers the source worker's tasks
    from queue_backend.pg_queue.consumer import build_consumer_from_env

    consumer = build_consumer_from_env()
    heartbeats[slot] = time.time()  # seed fresh before the first poll

    def _publish_heartbeat() -> None:
        # last-poll wall-time = now − (seconds since last poll). Frozen while a
        # task runs (the consumer stamps its heartbeat at the top of poll_once),
        # so a child stuck on a too-long task goes stale exactly as the single
        # consumer does — the supervisor then sees it via the shared slot.
        while True:
            heartbeats[slot] = time.time() - consumer.seconds_since_last_poll()
            time.sleep(_REPORT_INTERVAL_SECONDS)

    threading.Thread(target=_publish_heartbeat, daemon=True, name=f"pg-hb-{slot}").start()
    # consumer.run() installs its own SIGTERM/SIGINT handlers → graceful stop.
    consumer.run()


def run_supervised(concurrency: int) -> None:
    """Fork ``concurrency`` consumer children and supervise them until SIGTERM.

    Forks the initial fleet while the parent is still single-threaded (safe), then
    starts the liveness server and the reap/restart loop.
    """
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    # Shared, fork-inherited heartbeat slots (one wall-time per child). No lock:
    # each slot has a single writer (its child) and one reader (the parent); a
    # torn double read just yields one stale sample, self-correcting next tick.
    heartbeats = multiprocessing.Array("d", concurrency, lock=False)
    now = time.time()
    for i in range(concurrency):
        heartbeats[i] = now

    children: dict[int, int] = {}  # slot -> pid
    last_fork: dict[int, float] = {}  # slot -> monotonic time of last fork
    stopping = threading.Event()

    def _fork_child(slot: int) -> None:
        heartbeats[slot] = time.time()  # reset freshness for the new child
        pid = os.fork()
        if pid == 0:  # child
            try:
                _run_child(slot, heartbeats)
            except BaseException:
                # Last-resort: a child that can't even start must not return into
                # the supervisor loop (it would fork grandchildren). Log + hard exit.
                logger.exception("PG-queue consumer: child slot=%s failed to run", slot)
                os._exit(1)
            os._exit(0)
        children[slot] = pid
        last_fork[slot] = time.monotonic()
        logger.info("PG-queue consumer: forked child slot=%s pid=%s", slot, pid)

    def _signal_children(sig: int) -> None:
        for pid in list(children.values()):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, sig)

    def _on_term(signum: int, _frame: object) -> None:
        logger.info(
            "PG-queue consumer supervisor: signal %s — stopping %d child(ren)",
            signum,
            len(children),
        )
        stopping.set()
        _signal_children(signal.SIGTERM)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    # Fork the initial fleet while single-threaded (before the liveness thread).
    for slot in range(concurrency):
        _fork_child(slot)

    def _fleet_freshness() -> float:
        # Fleet age = the oldest child's staleness; if any child stalls past the
        # threshold the probe goes 503. A just-(re)forked child is seeded fresh.
        return _oldest_child_age(heartbeats)

    def _extra_status() -> dict[str, object]:
        return {"alive_children": len(children), "concurrency": concurrency}

    health = _maybe_start_supervisor_health(_fleet_freshness, _extra_status)

    try:
        while not stopping.is_set():
            _reap_and_restart(children, last_fork, stopping, _fork_child)
            time.sleep(_MONITOR_INTERVAL_SECONDS)
    finally:
        stopping.set()
        _signal_children(signal.SIGTERM)
        _join_children(children, _SHUTDOWN_GRACE_SECONDS)
        if health is not None:
            health.stop()
        logger.info("PG-queue consumer supervisor: stopped")


def _reap_and_restart(
    children: dict[int, int],
    last_fork: dict[int, float],
    stopping: threading.Event,
    fork_child,  # noqa: ANN001 (Callable[[int], None])
) -> None:
    """Reap any exited children; re-fork them (rate-limited) unless shutting down."""
    for slot, pid in list(children.items()):
        try:
            reaped, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            reaped = pid  # already reaped elsewhere — treat as gone
        if reaped == 0:
            continue  # still alive
        del children[slot]
        if stopping.is_set():
            continue
        elapsed = time.monotonic() - last_fork.get(slot, 0.0)
        if elapsed < _RESTART_MIN_INTERVAL_SECONDS:
            time.sleep(_RESTART_MIN_INTERVAL_SECONDS - elapsed)
        logger.warning(
            "PG-queue consumer: child slot=%s pid=%s exited — restarting", slot, pid
        )
        fork_child(slot)


def _join_children(children: dict[int, int], grace_seconds: float) -> None:
    """Wait up to ``grace_seconds`` for children to exit; SIGKILL stragglers."""
    deadline = time.monotonic() + grace_seconds
    for slot, pid in list(children.items()):
        remaining = deadline - time.monotonic()
        waited = False
        while remaining > 0:
            try:
                reaped, _status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                waited = True
                break
            if reaped != 0:
                waited = True
                break
            time.sleep(0.1)
            remaining = deadline - time.monotonic()
        if not waited:
            logger.warning(
                "PG-queue consumer: child slot=%s pid=%s did not stop in %ss — "
                "SIGKILL",
                slot,
                pid,
                grace_seconds,
            )
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)


def _maybe_start_supervisor_health(freshness_fn, extra_status_fn):  # noqa: ANN001,ANN201
    """Start the fleet liveness server when a port is configured; else None.

    Reuses the same env knobs as the single-process consumer
    (``WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT`` / ``_HEALTH_STALE_SECONDS``) so the
    pod's probe is unchanged — only the freshness source differs (fleet vs one loop).
    """
    from queue_backend.pg_queue.consumer import (
        _DEFAULT_HEALTH_STALE_SECONDS,
        consumer_env,
    )
    from queue_backend.pg_queue.liveness import LivenessServer

    port = consumer_env("HEALTH_PORT", None, int)
    if port is None:
        logger.info("PG-queue consumer supervisor: HEALTH_PORT unset — liveness disabled")
        return None
    stale_after = consumer_env(
        "HEALTH_STALE_SECONDS", _DEFAULT_HEALTH_STALE_SECONDS, float
    )
    server = LivenessServer(
        freshness_fn=freshness_fn,
        stale_after=stale_after,
        port=port,
        check_name="pg_queue_fleet",
        age_key="oldest_child_seconds_since_poll",
        extra_status_fn=extra_status_fn,
        thread_name="pg-supervisor-liveness",
        log_label="pg-queue supervisor",
    )
    try:
        server.start()
    except OSError:
        logger.exception(
            "PG-queue consumer supervisor: liveness could not bind :%s — "
            "continuing WITHOUT a probe",
            port,
        )
        return None
    logger.info(
        "PG-queue consumer supervisor: fleet liveness on :%s/health (stale after "
        "%ss, concurrency live)",
        server.bound_port,
        stale_after,
    )
    return server
