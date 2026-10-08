"""Prefork supervisor for the PG-queue consumer.

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

**Child watchdog** (UN-4223, opt-in via ``CHILD_WATCHDOG``): a loaded child whose
heartbeat goes stale past ``HEALTH_STALE_SECONDS``, or a child still not loaded
that long after its fork, is SIGKILLed and re-forked on its own. Its lease-renewal
thread dies with it, so the claim lapses and the reaper redelivers the message
(the poison cap bounds a task that hangs on every attempt). The siblings keep
running, so a pod without a liveness probe on ``/health`` loses one slot for one
stale window instead of the whole fleet. ``/health`` itself still reports 503 from
the stale crossing until the replacement loads (~20s), because ``oldest_age``
counts the killed slot's heartbeat. SIGKILL rather than SIGTERM: a graceful stop
waits for the in-flight task, which is the thing that is hung.

**Readiness** (UN-4136): the same port serves ``/ready``, which answers 200 only
once EVERY child has finished its ``import worker`` bootstrap and built its
consumer. ``/health`` cannot say this — the heartbeats are seeded fresh at
construction so liveness does not trip during a slow import — which is why a pod
used to go Ready ~20s after start while its N children were still importing, and
the HPA counted that multi-core start-up burst as load. A k8s ``startupProbe`` on
``/ready`` keeps the pod NotReady until the burst is over.

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
import math
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
# Least time a child gets to finish ``import worker`` before the watchdog treats it
# as hung. HEALTH_STALE is sized for task runtime and can be short (ide-callback:
# 180s), while a bootstrap under a CPU cap can take minutes.
_MIN_BOOTSTRAP_BUDGET_SECONDS = 600.0
# Fallback graceful-drain budget (s, shared across all children) on shutdown, used
# only when neither an explicit override nor the consumer VT is set — see
# shutdown_grace_from_env().
# This is NOT the live value: the live grace defaults to the consumer's visibility
# timeout so a SIGTERM (deploy / HPA scale-down) lets an in-flight batch finish
# instead of a mid-flight SIGKILL that orphans it.
_DEFAULT_SHUTDOWN_GRACE_SECONDS = 30.0


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


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"expected a boolean, got {raw!r}")


def child_watchdog_from_env() -> float | None:
    """Heartbeat age (seconds) past which the supervisor SIGKILLs a single child, or
    ``None`` when the watchdog is off.

    Off unless ``WORKER_PG_QUEUE_CONSUMER_CHILD_WATCHDOG`` is true. Opt-in because
    it turns ``HEALTH_STALE_SECONDS`` into a hard per-task wall-clock cap: on k8s a
    liveness probe already killed at that threshold (the whole pod), but a
    docker-compose install has no healthcheck, so there it has never been enforced
    and may sit below a legitimately long batch. Enable it only where
    ``HEALTH_STALE_SECONDS`` exceeds the longest legitimate task. Enabling it
    without that knob is a misconfiguration (its 60s code default would kill any
    task longer than a minute), so it raises.
    """
    from queue_backend.pg_queue.consumer import consumer_env

    if not consumer_env("CHILD_WATCHDOG", False, _parse_bool):
        return None
    stale: float | None = consumer_env("HEALTH_STALE_SECONDS", None, float)
    if stale is None:
        raise ValueError(
            "WORKER_PG_QUEUE_CONSUMER_CHILD_WATCHDOG is enabled but "
            "WORKER_PG_QUEUE_CONSUMER_HEALTH_STALE_SECONDS is unset — set it above "
            "the longest legitimate task"
        )
    if not math.isfinite(stale) or stale <= 0:
        raise ValueError(
            "WORKER_PG_QUEUE_CONSUMER_HEALTH_STALE_SECONDS must be a finite number "
            f"> 0, got {stale!r}"
        )
    return stale


def shutdown_grace_from_env() -> float:
    """Graceful-drain budget (seconds) on shutdown, shared across all children,
    before SIGKILL.

    Defaults to the consumer's visibility timeout (``WORKER_PG_QUEUE_CONSUMER_VT_SECONDS``)
    — the by-design upper bound on a single task's runtime — so a graceful SIGTERM
    (deploy / HPA scale-down) lets an in-flight batch finish rather than being
    SIGKILLed mid-flight and orphaned. The chart sets the pod's
    ``terminationGracePeriodSeconds`` to VT + a buffer, so even a genuinely-wedged
    child is SIGKILLed here just BEFORE k8s reaps the pod. An explicit
    ``WORKER_PG_QUEUE_CONSUMER_SHUTDOWN_GRACE_SECONDS`` overrides (and is honoured
    as-is, e.g. a short dev drain); otherwise the VT is floored at
    ``_DEFAULT_SHUTDOWN_GRACE_SECONDS`` so a tiny/unset VT still gets a sane drain.

    A hardcoded 30s here previously undercut the chart's ~2.5h budget by ~300×,
    SIGKILLing in-flight batches on every scale-down/rollout.
    """
    from queue_backend.pg_queue.consumer import _DEFAULT_VT_SECONDS, consumer_env

    override: float | None = consumer_env("SHUTDOWN_GRACE_SECONDS", None, float)
    if override is not None:
        # A negative / non-finite drain budget is never intentional and would
        # re-introduce the exact failure this module prevents: <0 or nan → 0 → every
        # child SIGKILLed with no drain; inf → shutdown hangs until k8s hard-kills the
        # pod. Fail fast at startup, mirroring concurrency_from_env()'s validation.
        if not math.isfinite(override) or override < 0:
            raise ValueError(
                "WORKER_PG_QUEUE_CONSUMER_SHUTDOWN_GRACE_SECONDS must be a finite "
                f"number >= 0, got {override!r}"
            )
        return override
    vt = consumer_env("VT_SECONDS", _DEFAULT_VT_SECONDS, int)
    return max(_DEFAULT_SHUTDOWN_GRACE_SECONDS, float(vt))


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
        # Shared, fork-inherited "finished loading" flags (one per child), read by
        # /ready. Same write discipline as the heartbeats: the owning child sets
        # its slot once bootstrapped; the parent clears it in reap(), when no child
        # owns the slot. Zero-initialised, so a fresh fleet starts not-ready.
        self._loaded = multiprocessing.Array("b", concurrency, lock=False)
        self._pids: dict[int, int] = {}
        self._last_fork: dict[int, float] = {}
        self._consecutive_crashes: dict[int, int] = {}
        self._restart_due: dict[int, float] = {}  # slot -> monotonic not-before
        # Written by the main thread, read by the liveness thread for /metrics; an
        # int read is atomic under the GIL.
        self.watchdog_kills = 0

    @property
    def concurrency(self) -> int:
        return self._n

    @property
    def heartbeats(self):  # noqa: ANN201
        """The shared heartbeat array (a ctypes array, passed to forked children,
        which write their own slot directly).
        """
        return self._heartbeats

    @property
    def loaded(self):  # noqa: ANN201
        """The shared loaded-flag array (a ctypes array, passed to forked children,
        which set their own slot once bootstrapped).
        """
        return self._loaded

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
        """Drop the slot's pid + last-fork together; return the child's uptime (s).

        Also clears the slot's loaded flag: its replacement must finish its own
        bootstrap before the fleet counts as loaded again.
        """
        forked_at = self._last_fork.pop(slot, time.monotonic())
        self._pids.pop(slot, None)
        self._loaded[slot] = 0
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

    def loaded_count(self) -> int:
        """Children that have finished their bootstrap (``import worker`` + build)."""
        return sum(self._loaded)

    def all_loaded(self) -> bool:
        """Readiness verdict source: True once every slot's child has loaded."""
        return self.loaded_count() == self._n

    def is_loaded(self, slot: int) -> bool:
        self._validate(slot)
        return bool(self._loaded[slot])

    def fork_age(self, slot: int) -> float:
        """Seconds since ``slot``'s current child was forked."""
        self._validate(slot)
        return time.monotonic() - self._last_fork.get(slot, time.monotonic())

    def slot_age(self, slot: int) -> float:
        """Seconds since ``slot``'s child last polled, per its published heartbeat."""
        self._validate(slot)
        return time.time() - self._heartbeats[slot]

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


def _run_child(slot: int, heartbeats, loaded) -> None:  # noqa: ANN001 (ctypes arrays)
    """Build one consumer and run it forever, publishing its heartbeat.

    The worker import (and any connections it opens) happens HERE, in the child —
    never inherited across the fork — so each process owns its own connections.
    A *guarded* daemon thread publishes the consumer's last-poll wall-time into
    ``heartbeats[slot]`` for the supervisor's fleet liveness, and ``loaded[slot]``
    is set once the bootstrap is done, for the supervisor's ``/ready``.
    """
    started = time.monotonic()
    from pg_queue_consumer._bootstrap import select_source_worker_type

    select_source_worker_type()  # set WORKER_TYPE before importing worker
    import worker  # noqa: F401 — side-effect: registers the source worker's tasks
    from queue_backend.pg_queue.consumer import build_consumer_from_env

    consumer = build_consumer_from_env()

    def _publish_heartbeat() -> None:
        # last-poll wall-time = now − (seconds since last poll). Frozen while a
        # task runs (the consumer stamps its heartbeat before each queue read),
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

    # Publish once before ``loaded`` so the watchdog never pairs a loaded slot with
    # the previous child's stale heartbeat.
    heartbeats[slot] = time.time() - consumer.seconds_since_last_poll()
    threading.Thread(target=_publish_heartbeat, daemon=True, name=f"pg-hb-{slot}").start()
    loaded[slot] = 1
    logger.info(
        "PG-queue consumer: child slot=%s loaded in %.1fs",
        slot,
        time.monotonic() - started,
    )
    # consumer.run() installs its own SIGTERM/SIGINT handlers → graceful stop.
    consumer.run()


def _child_after_fork(slot: int, heartbeats, loaded) -> None:  # noqa: ANN001 (ctypes arrays)
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
        _run_child(slot, heartbeats, loaded)
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
        _child_after_fork(slot, fleet.heartbeats, fleet.loaded)
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


def _kill_stale_children(fleet: _Fleet, stale_after: float, killed: set[int]) -> None:
    """SIGKILL every child silent for longer than ``stale_after``.

    A *loaded* child is judged by its heartbeat. A child not yet loaded is judged
    by time since its fork, against the larger of ``stale_after`` and
    ``_MIN_BOOTSTRAP_BUDGET_SECONDS``: a re-forked slot keeps its predecessor's old
    heartbeat until the new child bootstraps (record_fork does not reseed it), so
    the heartbeat would kill every replacement during import, while a child that
    hangs in ``import worker`` would otherwise never be judged at all. ``killed``
    holds pids already signalled and not yet reaped, so a child is killed and
    logged once; the next ``_reap_dead`` reaps it and schedules the re-fork like
    any other exit.
    """
    bootstrap_budget = max(stale_after, _MIN_BOOTSTRAP_BUDGET_SECONDS)
    for slot, pid in fleet.alive_items():
        if pid in killed:
            continue
        loaded = fleet.is_loaded(slot)
        age = fleet.slot_age(slot) if loaded else fleet.fork_age(slot)
        limit = stale_after if loaded else bootstrap_budget
        if age <= limit:
            continue
        logger.error(
            "PG-queue consumer: child slot=%s pid=%s %s for %.0fs (> %.0fs) — "
            "presumed hung; SIGKILL so its message redelivers and the slot is "
            "re-forked",
            slot,
            pid,
            "has not polled" if loaded else "has not finished loading",
            age,
            limit,
        )
        killed.add(pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue  # exited on its own first; the reap handles it, not a kill
        fleet.watchdog_kills += 1


def _monitor_tick(
    fleet: _Fleet,
    stopping: threading.Event,
    watchdog_after: float | None,
    killed: set[int],
) -> None:
    """One supervisor iteration: reap exits, re-fork due slots, then the watchdog.

    ``killed`` is trimmed to live pids right after the reap, so a recycled pid is
    never mistaken for one already signalled.
    """
    _reap_dead(fleet, stopping)
    killed.intersection_update(pid for _slot, pid in fleet.alive_items())
    _restart_due_children(fleet, stopping)
    if watchdog_after is not None and not stopping.is_set():
        _kill_stale_children(fleet, watchdog_after, killed)


def run_supervised(concurrency: int) -> None:
    """Fork ``concurrency`` consumer children and supervise them until SIGTERM."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    fleet = _Fleet(concurrency)
    grace_seconds = shutdown_grace_from_env()
    logger.info(
        "PG-queue consumer supervisor: shutdown drain grace = %.0fs (shared across "
        "children)",
        grace_seconds,
    )
    watchdog_after = child_watchdog_from_env()
    if watchdog_after is None:
        logger.info("PG-queue consumer supervisor: child watchdog off")
    else:
        logger.info(
            "PG-queue consumer supervisor: child watchdog kills a child silent for "
            "> %.0fs",
            watchdog_after,
        )
    killed: set[int] = set()
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
            _join_children(fleet, grace_seconds)
            raise RuntimeError(
                f"PG-queue consumer: os.fork() failed starting child {slot}/"
                f"{concurrency} — reduce WORKER_PG_QUEUE_CONSUMER_CONCURRENCY or "
                "raise the process/memory limit"
            )

    health = _maybe_start_supervisor_health(fleet)
    try:
        while not stopping.is_set():
            _monitor_tick(fleet, stopping, watchdog_after, killed)
            stopping.wait(_MONITOR_INTERVAL_SECONDS)  # responsive to SIGTERM
    finally:
        stopping.set()
        _signal_children(signal.SIGTERM)
        _join_children(fleet, grace_seconds)
        if health is not None:
            health.stop()
        logger.info("PG-queue consumer supervisor: stopped")


def _wait_for_exit(pid: int, deadline: float) -> bool:
    """Poll ``pid`` until it exits or ``deadline`` (monotonic) passes. True if it
    exited (or was already reaped).

    Polls ``waitpid`` at least once regardless of the deadline: with the single
    SHARED shutdown deadline, a child iterated after the window has already elapsed
    would otherwise be reported "did not drain" and SIGKILLed — a false hard-kill
    alarm — even though it exited cleanly within the grace.
    """
    while True:
        try:
            reaped, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        if reaped != 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _join_children(fleet: _Fleet, grace_seconds: float) -> None:
    """Wait up to ``grace_seconds`` TOTAL for all children to drain, then SIGKILL +
    reap any straggler. A SINGLE shared deadline (not per-child): the children are
    all SIGTERM'd together *before* this call and drain in parallel, so one shared
    window still gives every child its full grace from that common SIGTERM — while
    bounding the total wait to ~``grace_seconds``. A per-child deadline would instead
    sum to N×grace and, at grace≈VT (thousands of seconds), blow past the pod's
    ``terminationGracePeriodSeconds`` — so k8s SIGKILLs the whole pod, hard-killing
    siblings that were still draining cleanly.
    """
    deadline = time.monotonic() + grace_seconds
    for slot, pid in fleet.alive_items():
        if _wait_for_exit(pid, deadline):
            continue
        logger.warning(
            "PG-queue consumer: child slot=%s pid=%s did not drain within the "
            "shared %.0fs grace — SIGKILL",
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

    ``/ready`` → 200 only once every child has loaded (:meth:`_Fleet.all_loaded`),
    for the chart's opt-in ``startupProbe``.

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
            "loaded_children": fleet.loaded_count(),
            "concurrency": fleet.concurrency,
            "crash_looping": fleet.is_crash_looping(),
            "liveness_probe_bound": True,
        }

    from queue_backend.pg_queue.metrics import ConsumerMetrics

    metrics = ConsumerMetrics(
        freshness_fn=fleet.freshness,
        alive_children_fn=lambda: float(fleet.alive_count()),
        concurrency_fn=lambda: float(fleet.concurrency),
        watchdog_kills_fn=lambda: float(fleet.watchdog_kills),
    )
    server = LivenessServer(
        freshness_fn=fleet.freshness,
        stale_after=stale_after,
        port=port,
        check_name="pg_queue_fleet",
        age_key="oldest_child_seconds_since_poll",
        extra_status_fn=_extra_status,
        metrics_fn=metrics.render,
        ready_fn=fleet.all_loaded,
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
        "PG-queue consumer supervisor: fleet liveness on :%s/health, readiness on "
        "/ready (stale after %ss, %d children)",
        server.bound_port,
        stale_after,
        fleet.concurrency,
    )
    return server
