"""Prefork supervisor for the PG-queue consumer (UN-3606).

Forks ``WORKER_PG_QUEUE_CONSUMER_CONCURRENCY`` copies of the single-threaded
:class:`~queue_backend.pg_queue.consumer.PgQueueConsumer` so multiple file
batches run in parallel — the PG analogue of Celery's ``--pool=prefork
--concurrency=N``. ``SELECT … FOR UPDATE SKIP LOCKED`` distributes work across the
children (and across replicas): each child claims distinct rows, a single
execution is still capped by ``MAX_PARALLEL_FILE_BATCHES``, and total live
parallelism = ``concurrency × replicas`` (k8s HPA scales the replica count).

**Process model** (matches Celery prefork — the cloud-trusted choice): each child
is a fully isolated process with its own DB connections and thread-local
``StateStore`` — no shared mutable state, no thread-safety surface. A child crash
is isolated and re-forked (rate-limited); its in-flight message redelivers via
``vt`` (at-least-once). The **consumer code is unchanged** — concurrency is purely
a launch concern. ``CONCURRENCY = 1`` keeps the plain single-process ``main()``
path (byte-identical to before this module existed).

**Health**: the supervisor owns the single liveness port and reports the *fleet's*
freshness — the staleness of the oldest-polling child (each child publishes its
last-poll wall-time into a shared array). A child that dies is re-forked
internally (transient); a child that **crash-loops** (dies immediately N times in
a row, never reaching a real poll) forces the probe to 503 so k8s restarts the
pod rather than the supervisor masking a wedged fleet with fresh-looking re-forks.

**Fork safety**: the initial fleet is forked while the parent is single-threaded.
Re-forks happen after the liveness daemon thread exists; the only other thread is
that probe (idle in ``select`` between requests, and CPython 3.12 re-inits the
``logging`` locks across ``fork`` via ``os.register_at_fork``), and each child
resets inherited signal handlers + does its own ``import worker`` before touching
shared resources — so an inherited held lock or the parent's ``_on_term`` cannot
wedge or mis-signal a child.
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import os
import signal
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from queue_backend.pg_queue.liveness import LivenessServer

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 1
# Fork-bomb backstop for a fat-fingered env (a single machine can't usefully run
# hundreds of heavy file-processing children anyway — scale replicas instead).
_MAX_CONCURRENCY = 64
# How often each child republishes its heartbeat, and the parent reaps + checks.
_REPORT_INTERVAL_SECONDS = 1.0
_MONITOR_INTERVAL_SECONDS = 1.0
# Re-fork backoff floor and ceiling — a crash-looping child must not fork-storm.
_RESTART_MIN_INTERVAL_SECONDS = 2.0
_RESTART_MAX_BACKOFF_SECONDS = 30.0
# A child that stays up at least this long before exiting is a normal exit, not an
# immediate crash — it resets the slot's consecutive-crash counter.
_MIN_HEALTHY_UPTIME_SECONDS = 10.0
# Consecutive immediate crashes after which the fleet probe is forced unhealthy.
_CRASH_LOOP_THRESHOLD = 3
# How long to wait per child for a graceful drain on shutdown before SIGKILL.
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


class _Fleet:
    """Owns the per-slot child state — pid, last-fork, heartbeat, crash count and
    pending-restart schedule — keeping them mutually consistent. Slots are
    validated against ``[0, concurrency)`` so a stray key can't silently desync
    the structures or ``IndexError`` the shared array.
    """

    def __init__(self, concurrency: int) -> None:
        self._n = concurrency
        # Shared, fork-inherited heartbeat slots (one last-poll wall-time per
        # child). lock=False is safe: a slot is written either by the parent
        # (seed, at construction, while no child owns it) OR by that child's
        # heartbeat thread — never concurrently — and only read by the parent, so
        # a torn double read just yields one stale sample that self-corrects.
        self._heartbeats = multiprocessing.Array("d", concurrency, lock=False)
        now = time.time()
        for i in range(concurrency):
            self._heartbeats[i] = now
        self._pids: dict[int, int] = {}
        self._last_fork: dict[int, float] = {}
        self._consecutive_crashes: dict[int, int] = {}
        self._restart_due: dict[int, float] = {}  # slot -> monotonic not-before

    @property
    def concurrency(self) -> int:
        return self._n

    @property
    def heartbeats(self):  # noqa: ANN201
        """The shared heartbeat array (a ctypes array, passed to forked children,
        which write their own slot directly).
        """
        return self._heartbeats

    def _validate(self, slot: int) -> None:
        if not 0 <= slot < self._n:
            raise IndexError(f"slot {slot} out of range [0, {self._n})")

    def record_fork(self, slot: int, pid: int) -> None:
        """Mark ``slot`` alive under ``pid``; clears any pending restart. Note the
        heartbeat is deliberately NOT reseeded here — a re-forked child must earn
        freshness by actually polling, so a crash-looping slot ages instead of
        looking perpetually fresh.
        """
        self._validate(slot)
        self._pids[slot] = pid
        self._last_fork[slot] = time.monotonic()
        self._restart_due.pop(slot, None)

    def reap(self, slot: int) -> float:
        """Drop the slot's pid + last-fork together; return the child's uptime (s)."""
        forked_at = self._last_fork.pop(slot, time.monotonic())
        self._pids.pop(slot, None)
        return time.monotonic() - forked_at

    def schedule_restart(self, slot: int, uptime: float) -> int:
        """Record the exit and set the re-fork not-before; return the consecutive
        immediate-crash count. A child that ran healthily before exiting resets the
        counter; an immediate death increments it and backs the restart off
        (capped) so a crash loop can't fork-storm.
        """
        if uptime < _MIN_HEALTHY_UPTIME_SECONDS:
            n = self._consecutive_crashes.get(slot, 0) + 1
        else:
            n = 0  # ran fine, then exited — not a crash loop
        self._consecutive_crashes[slot] = n
        backoff = min(
            _RESTART_MIN_INTERVAL_SECONDS * max(1, n), _RESTART_MAX_BACKOFF_SECONDS
        )
        self._restart_due[slot] = time.monotonic() + backoff
        return n

    def due_restarts(self) -> list[int]:
        """Slots whose re-fork backoff has elapsed (oldest schedule first)."""
        now = time.monotonic()
        return sorted(s for s, due in self._restart_due.items() if due <= now)

    def consecutive_crashes(self, slot: int) -> int:
        return self._consecutive_crashes.get(slot, 0)

    def alive_items(self) -> list[tuple[int, int]]:
        return list(self._pids.items())

    def alive_count(self) -> int:
        return len(self._pids)

    def is_crash_looping(self) -> bool:
        """True if any slot has died immediately ``_CRASH_LOOP_THRESHOLD`` times in
        a row — the signal that the heartbeat alone can't be trusted fresh.

        Snapshots the values first (``tuple(...)`` is atomic under the GIL): this
        runs in the liveness daemon thread (via :meth:`freshness`) while the main
        thread mutates ``_consecutive_crashes`` in :meth:`schedule_restart`, so a
        bare ``.values()`` iteration could raise "dictionary changed size during
        iteration".
        """
        return any(
            n >= _CRASH_LOOP_THRESHOLD for n in tuple(self._consecutive_crashes.values())
        )

    def oldest_age(self) -> float:
        now = time.time()
        return max((now - hb for hb in self._heartbeats), default=0.0)

    def freshness(self) -> float:
        """Liveness verdict source: a crash-looping fleet is force-stale (``inf``)
        so the probe trips 503 even if a just-constructed child briefly looked
        fresh; otherwise the oldest child's staleness (catches a wedged-alive
        child).
        """
        return float("inf") if self.is_crash_looping() else self.oldest_age()


def _run_child(slot: int, heartbeats) -> None:  # noqa: ANN001 (ctypes array)
    """Build one consumer and run it forever, publishing its heartbeat.

    The worker import (and any connections it opens) happens HERE, in the child —
    never inherited across the fork — so each process owns its own connections.
    A *guarded* daemon thread publishes the consumer's last-poll wall-time into
    ``heartbeats[slot]`` for the supervisor's fleet liveness.
    """
    from pg_queue_consumer._bootstrap import select_source_worker_type

    select_source_worker_type()  # set WORKER_TYPE before importing worker
    import worker  # noqa: F401 — side-effect: registers the source worker's tasks
    from queue_backend.pg_queue.consumer import build_consumer_from_env

    consumer = build_consumer_from_env()

    def _publish_heartbeat() -> None:
        # last-poll wall-time = now − (seconds since last poll). Frozen while a
        # task runs (the consumer stamps its heartbeat at the top of poll_once),
        # so a child stuck on a too-long task goes stale exactly as the single
        # consumer does. Guarded so a transient error (e.g. teardown during
        # shutdown) logs loudly and the loop continues instead of dying silently
        # and false-staling a healthy child.
        while True:
            try:
                heartbeats[slot] = time.time() - consumer.seconds_since_last_poll()
            except Exception:
                logger.exception(
                    "PG-queue consumer: heartbeat publish failed for slot=%s", slot
                )
            time.sleep(_REPORT_INTERVAL_SECONDS)

    threading.Thread(target=_publish_heartbeat, daemon=True, name=f"pg-hb-{slot}").start()
    # consumer.run() installs its own SIGTERM/SIGINT handlers → graceful stop.
    consumer.run()


def _child_after_fork(slot: int, heartbeats) -> None:  # noqa: ANN001 (ctypes array)
    """Child side of the fork: reset inherited state, run, hard-exit on failure.

    Resets the supervisor's signal handlers to ``SIG_DFL`` *immediately* — until
    ``consumer.run()`` installs its own, a SIGTERM arriving in the fork→run window
    (which spans the slow ``import worker`` bootstrap) must NOT fire the parent's
    ``_on_term`` closure in the child (it captured a stale ``children`` dict and
    would signal sibling pids). ``SIG_DFL`` = terminate, the correct disposition
    for a not-yet-running child.
    """
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        _run_child(slot, heartbeats)
    except Exception:
        # A child that can't even start must not return into the supervisor loop
        # (it would fork grandchildren). Log + hard exit. Exception (not
        # BaseException) is the realistic startup-failure surface here — import,
        # connection, config; SystemExit/KeyboardInterrupt would exit anyway.
        logger.exception("PG-queue consumer: child slot=%s failed to run", slot)
        os._exit(1)
    os._exit(0)


def _try_fork_child(fleet: _Fleet, slot: int) -> bool:
    """Fork one child for ``slot``. Returns False (without raising) if ``os.fork``
    fails — EAGAIN (RLIMIT_NPROC) / ENOMEM are realistic under heavy-child load —
    so the caller can fail fast (initial fleet) or leave the slot for the next
    monitor tick (re-fork path) instead of an uncaught crash taking the fleet down.
    """
    try:
        pid = os.fork()
    except OSError:
        logger.exception(
            "PG-queue consumer: os.fork() failed for slot=%s (process/memory "
            "limit?) — will retry",
            slot,
        )
        return False
    if pid == 0:  # child — never returns
        _child_after_fork(slot, fleet.heartbeats)
    fleet.record_fork(slot, pid)
    logger.info("PG-queue consumer: forked child slot=%s pid=%s", slot, pid)
    return True


def _reap_dead(fleet: _Fleet, stopping: threading.Event) -> None:
    """Reap exited children and schedule their re-fork (unless shutting down)."""
    for slot, pid in fleet.alive_items():
        try:
            reaped, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            reaped = pid  # already reaped elsewhere — treat as gone
        if reaped == 0:
            continue  # still alive
        uptime = fleet.reap(slot)
        if stopping.is_set():
            continue  # do not resurrect during shutdown
        crashes = fleet.schedule_restart(slot, uptime)
        level = logging.ERROR if crashes >= _CRASH_LOOP_THRESHOLD else logging.WARNING
        logger.log(
            level,
            "PG-queue consumer: child slot=%s pid=%s exited after %.1fs "
            "(consecutive immediate crashes=%s) — re-fork scheduled",
            slot,
            pid,
            uptime,
            crashes,
        )


def _restart_due_children(fleet: _Fleet, stopping: threading.Event) -> None:
    """Re-fork the slots whose backoff has elapsed — non-blocking (the backoff is
    a scheduled not-before, not an in-loop sleep), and re-checking ``stopping``
    each iteration so a SIGTERM mid-cycle can't spawn a fresh child into shutdown.
    """
    for slot in fleet.due_restarts():
        if stopping.is_set():
            return
        # On success record_fork clears the pending restart; on fork failure the
        # slot stays due and is retried next tick.
        _try_fork_child(fleet, slot)


def run_supervised(concurrency: int) -> None:
    """Fork ``concurrency`` consumer children and supervise them until SIGTERM."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    fleet = _Fleet(concurrency)
    stopping = threading.Event()

    def _signal_children(sig: int) -> None:
        for _slot, pid in fleet.alive_items():
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, sig)

    def _on_term(signum: int, _frame: object) -> None:
        logger.info(
            "PG-queue consumer supervisor: signal %s — stopping %d child(ren)",
            signum,
            fleet.alive_count(),
        )
        stopping.set()
        _signal_children(signal.SIGTERM)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    # Fork the initial fleet while single-threaded (before the liveness thread).
    # A fork failure here is fatal + actionable rather than a half-started fleet.
    for slot in range(concurrency):
        if not _try_fork_child(fleet, slot):
            stopping.set()
            _signal_children(signal.SIGTERM)
            _join_children(fleet, _SHUTDOWN_GRACE_SECONDS)
            raise RuntimeError(
                f"PG-queue consumer: os.fork() failed starting child {slot}/"
                f"{concurrency} — reduce WORKER_PG_QUEUE_CONSUMER_CONCURRENCY or "
                "raise the process/memory limit"
            )

    health = _maybe_start_supervisor_health(fleet)
    try:
        while not stopping.is_set():
            _reap_dead(fleet, stopping)
            _restart_due_children(fleet, stopping)
            stopping.wait(_MONITOR_INTERVAL_SECONDS)  # responsive to SIGTERM
    finally:
        stopping.set()
        _signal_children(signal.SIGTERM)
        _join_children(fleet, _SHUTDOWN_GRACE_SECONDS)
        if health is not None:
            health.stop()
        logger.info("PG-queue consumer supervisor: stopped")


def _wait_for_exit(pid: int, deadline: float) -> bool:
    """Poll ``pid`` until it exits or ``deadline`` (monotonic) passes. True if it
    exited (or was already reaped).
    """
    while time.monotonic() < deadline:
        try:
            reaped, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        if reaped != 0:
            return True
        time.sleep(0.1)
    return False


def _join_children(fleet: _Fleet, grace_seconds: float) -> None:
    """Wait up to ``grace_seconds`` *per child* for a graceful drain; SIGKILL +
    reap any straggler. The budget is per-child (not a single shared deadline) so
    one slow-draining child can't starve the others of their grace.
    """
    for slot, pid in fleet.alive_items():
        if _wait_for_exit(pid, time.monotonic() + grace_seconds):
            continue
        logger.warning(
            "PG-queue consumer: child slot=%s pid=%s did not stop in %ss — SIGKILL",
            slot,
            pid,
            grace_seconds,
        )
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        with contextlib.suppress(ChildProcessError):
            os.waitpid(pid, 0)


def _maybe_start_supervisor_health(fleet: _Fleet) -> LivenessServer | None:
    """Start the fleet liveness server when a port is configured; else None.

    Reuses the single-process consumer's env knobs (``..._HEALTH_PORT`` /
    ``..._HEALTH_STALE_SECONDS``) and the same HTTP contract (``/health`` →
    200/503), so the k8s probe config is unchanged. The JSON body differs
    (``check="pg_queue_fleet"``, age key ``oldest_child_seconds_since_poll``) since
    the freshness source is the fleet's oldest child, not one poll loop.

    A bind failure does not abort the consumer (it must keep draining the queue),
    but ``EADDRINUSE`` usually signals a real config bug, so it's logged at error;
    either way ``liveness_probe_bound: false`` is surfaced in the status payload so
    the degradation is observable.
    """
    from queue_backend.pg_queue.consumer import (
        _DEFAULT_HEALTH_STALE_SECONDS,
        consumer_env,
    )
    from queue_backend.pg_queue.liveness import LivenessServer

    port: int | None = consumer_env("HEALTH_PORT", None, int)
    if port is None:
        logger.info("PG-queue consumer supervisor: HEALTH_PORT unset — liveness disabled")
        return None
    stale_after = consumer_env(
        "HEALTH_STALE_SECONDS", _DEFAULT_HEALTH_STALE_SECONDS, float
    )

    def _extra_status() -> dict[str, object]:
        return {
            "alive_children": fleet.alive_count(),
            "concurrency": fleet.concurrency,
            "crash_looping": fleet.is_crash_looping(),
            "liveness_probe_bound": True,
        }

    from queue_backend.pg_queue.metrics import ConsumerMetrics

    metrics = ConsumerMetrics(
        freshness_fn=fleet.freshness,
        alive_children_fn=lambda: float(fleet.alive_count()),
        concurrency_fn=lambda: float(fleet.concurrency),
    )
    server = LivenessServer(
        freshness_fn=fleet.freshness,
        stale_after=stale_after,
        port=port,
        check_name="pg_queue_fleet",
        age_key="oldest_child_seconds_since_poll",
        extra_status_fn=_extra_status,
        metrics_fn=metrics.render,
        thread_name="pg-supervisor-liveness",
        log_label="pg-queue supervisor",
    )
    try:
        server.start()
    except OSError as exc:
        import errno

        level = logging.ERROR if exc.errno == errno.EADDRINUSE else logging.WARNING
        logger.log(
            level,
            "PG-queue consumer supervisor: liveness could not bind :%s (%s) — "
            "continuing WITHOUT a probe",
            port,
            exc.strerror or exc,
            exc_info=True,
        )
        return None
    logger.info(
        "PG-queue consumer supervisor: fleet liveness on :%s/health (stale after "
        "%ss, %d children)",
        server.bound_port,
        stale_after,
        fleet.concurrency,
    )
    return server
