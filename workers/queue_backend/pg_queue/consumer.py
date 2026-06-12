"""PG queue consumer — claims tasks from ``pg_queue_message`` and runs them.

The producer side (9b) enqueues a :class:`~queue_backend.pg_queue.TaskPayload`
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

Run as ``python -m queue_backend.pg_queue.consumer`` (config via env). The
worker bootstrap must have imported/registered the Celery tasks so they
resolve in ``current_app.tasks``.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from celery import current_app

from ..fairness import FAIRNESS_HEADER_NAME
from .client import PgQueueClient

if TYPE_CHECKING:
    from celery import Celery

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
_DEFAULT_POLL_INTERVAL = 0.1
_DEFAULT_BACKOFF_MAX = 2.0
# A task claimed more than this many times keeps failing — drop it (poison)
# rather than redeliver forever.
_DEFAULT_MAX_ATTEMPTS = 5
# Liveness: a poll loop that hasn't cycled in this many seconds is reported
# unhealthy. Well above _DEFAULT_BACKOFF_MAX (idle backoff) and any sane task
# duration, so only a genuinely wedged loop trips it.
_DEFAULT_HEALTH_STALE_SECONDS = 60.0


class PgQueueConsumer:
    """Polls one PG queue, runs each claimed task in-process, acks on success."""

    def __init__(
        self,
        queue_name: str,
        *,
        client: PgQueueClient | None = None,
        app: Celery | None = None,
        batch_size: int = _DEFAULT_BATCH,
        vt_seconds: int = _DEFAULT_VT_SECONDS,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        # Validate at construction so a misconfigured consumer fails here
        # rather than batch-after-batch once the loop starts.
        for name, value in (
            ("batch_size", batch_size),
            ("vt_seconds", vt_seconds),
            ("poll_interval", poll_interval),
            ("backoff_max", backoff_max),
            ("max_attempts", max_attempts),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")
        if backoff_max < poll_interval:
            # Otherwise min(poll_interval*2, backoff_max) shrinks the backoff
            # below poll_interval — it would decrease instead of grow.
            raise ValueError(
                f"backoff_max ({backoff_max}) must be >= poll_interval "
                f"({poll_interval})"
            )
        self.queue_name = queue_name
        self._client = client if client is not None else PgQueueClient()
        self._app = app if app is not None else current_app
        self.batch_size = batch_size
        self.vt_seconds = vt_seconds
        self.poll_interval = poll_interval
        self.backoff_max = backoff_max
        self.max_attempts = max_attempts
        self._running = False
        # Heartbeat for the liveness probe: monotonic timestamp of the most
        # recent poll attempt. Seeded at construction so a just-started consumer
        # reads healthy. Updated at the TOP of poll_once, so a loop wedged on a
        # long-running task (poll_once not returning) goes stale and is caught —
        # something pgrep-based --status and the launch-time check cannot see.
        self._last_poll_monotonic = time.monotonic()

    def poll_once(self) -> int:
        """Claim + process one batch; returns the number of messages claimed."""
        self._last_poll_monotonic = time.monotonic()
        messages = self._client.read(
            self.queue_name, vt_seconds=self.vt_seconds, qty=self.batch_size
        )
        for message in messages:
            self._handle(message)
        return len(messages)

    def _handle(self, message: QueueMessage) -> None:
        payload = message.message
        task_name = payload.get("task_name")

        # Malformed / foreign payload: no task name → can't run; drop with a
        # log that points at the payload, not at task registration.
        if not task_name:
            logger.error(
                "PG-queue consumer: payload missing task_name (msg_id=%s) — "
                "dropping malformed message: %r",
                message.msg_id,
                payload,
            )
            self._client.delete(message.msg_id)
            return

        # Poison message: a task re-claimed past the cap keeps failing. Drop
        # it (with the payload, so it's recoverable from logs) instead of
        # redelivering on every vt expiry forever.
        if message.read_ct > self.max_attempts:
            logger.error(
                "PG-queue consumer: task %r (msg_id=%s) exceeded max_attempts=%s "
                "(read_ct=%s) — dropping poison message: %r",
                task_name,
                message.msg_id,
                self.max_attempts,
                message.read_ct,
                payload,
            )
            self._client.delete(message.msg_id)
            return

        task = self._app.tasks.get(task_name)
        if task is None:
            # A named-but-unregistered task can never run → drop and shout.
            logger.error(
                "PG-queue consumer: unknown task %r (msg_id=%s) — dropping",
                task_name,
                message.msg_id,
            )
            self._client.delete(message.msg_id)
            return

        try:
            # Run the task body in-process (eager), carrying the fairness
            # header so a PG-routed run mirrors the Celery dispatch path.
            fairness = payload.get("fairness")
            headers = {FAIRNESS_HEADER_NAME: fairness} if fairness else None
            task.apply(
                args=payload.get("args") or [],
                kwargs=payload.get("kwargs") or {},
                headers=headers,
                throw=True,
            )
        except Exception:
            # Leave the row: its vt expires and it is redelivered (bounded by
            # max_attempts above).
            logger.exception(
                "PG-queue consumer: task %r (msg_id=%s, read_ct=%s) failed — "
                "leaving for vt-expiry redelivery",
                task_name,
                message.msg_id,
                message.read_ct,
            )
            return

        if not self._client.delete(message.msg_id):  # ack
            logger.warning(
                "PG-queue consumer: ack found no row for task %r (msg_id=%s) — "
                "it likely exceeded vt and was re-claimed (possible double-run)",
                task_name,
                message.msg_id,
            )

    def _registered_task_count(self) -> int:
        """Count application tasks (excluding Celery's built-ins)."""
        return sum(1 for name in self._app.tasks if not name.startswith("celery."))

    def seconds_since_last_poll(self) -> float:
        """Seconds since the last poll attempt (for the liveness heartbeat)."""
        return time.monotonic() - self._last_poll_monotonic

    def is_poll_stale(self, stale_after_seconds: float) -> bool:
        """True if the poll loop hasn't cycled within ``stale_after_seconds``.

        Drives the health endpoint: a stale loop means the consumer is wedged
        (deadlock, or a single task running longer than the threshold), so the
        liveness probe should report unhealthy and let the orchestrator restart
        it. Pick a threshold comfortably above ``backoff_max`` and the longest
        expected task so normal idle/backoff never trips it.
        """
        return self.seconds_since_last_poll() > stale_after_seconds

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
            "PG-queue consumer started (queue=%r, batch=%s, vt=%ss) — "
            "%d application task(s) registered: %s",
            self.queue_name,
            self.batch_size,
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
        logger.info("PG-queue consumer stopped (queue=%r)", self.queue_name)

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


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    def _env(suffix: str, default: _T, cast: Callable[[str], _T]) -> _T:
        # Preserve the default's type through to PgQueueConsumer's typed
        # __init__ (a bare `type` would erase it). On a bad value, fail with the
        # offending var name instead of a context-free `int('abc')` ValueError.
        var = f"WORKER_PG_QUEUE_CONSUMER_{suffix}"
        raw = os.getenv(var)
        if raw is None:
            return default
        try:
            return cast(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid {var}={raw!r}: {exc}") from exc

    consumer = PgQueueConsumer(
        queue_name=_env("QUEUE", _DEFAULT_QUEUE, str),
        batch_size=_env("BATCH", _DEFAULT_BATCH, int),
        vt_seconds=_env("VT_SECONDS", _DEFAULT_VT_SECONDS, int),
        poll_interval=_env("POLL_INTERVAL", _DEFAULT_POLL_INTERVAL, float),
        backoff_max=_env("BACKOFF_MAX", _DEFAULT_BACKOFF_MAX, float),
        max_attempts=_env("MAX_ATTEMPTS", _DEFAULT_MAX_ATTEMPTS, int),
    )
    health_server = _maybe_start_health_server(
        consumer,
        port=_env("HEALTH_PORT", None, int),
        stale_after=_env("HEALTH_STALE_SECONDS", _DEFAULT_HEALTH_STALE_SECONDS, float),
    )
    try:
        consumer.run()
    finally:
        if health_server is not None:
            health_server.stop()


def _maybe_start_health_server(
    consumer: PgQueueConsumer, *, port: int | None, stale_after: float
) -> LivenessServer | None:
    """Start the liveness server when a port is configured; else ``None``.

    Opt-in by ``WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT`` — a bare
    ``python -m pg_queue_consumer`` with no port set binds nothing (no stray
    port to collide).
    """
    if port is None:
        logger.info(
            "PG-queue consumer: WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT unset — "
            "liveness server disabled"
        )
        return None
    server = LivenessServer(consumer, port=port, stale_after=stale_after)
    server.start()
    logger.info(
        "PG-queue consumer: liveness server on :%s/health (stale after %ss)",
        server.bound_port,
        stale_after,
    )
    return server


class LivenessServer:
    """Tiny HTTP liveness probe: 200 while the poll loop is fresh, else 503.

    Deliberately lean. A *liveness* probe must answer one question — "is this
    process still making progress?" — and nothing else. It must NOT depend on
    broker/API reachability or resource pressure: a transient backend blip or a
    busy moment would otherwise make the orchestrator crash-loop an
    otherwise-healthy consumer. So this intentionally does *not* reuse the
    shared ``HealthChecker`` (which bundles api-connectivity / system-resource
    checks meant for richer health reporting, not liveness) — it reports solely
    on the poll-loop heartbeat (:meth:`PgQueueConsumer.is_poll_stale`).

    Serves ``/health`` (also ``/healthz``, ``/livez``) in a daemon thread.
    Bind ``port=0`` to let the OS pick a free port (read back via
    :attr:`bound_port`) — used in tests.
    """

    _PATHS = frozenset({"/health", "/healthz", "/livez"})

    def __init__(
        self, consumer: PgQueueConsumer, *, port: int, stale_after: float
    ) -> None:
        self._consumer = consumer
        self._port = port
        self._stale_after = stale_after
        self._httpd: Any = None
        self._thread: Any = None

    def start(self) -> None:
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        consumer = self._consumer
        stale_after = self._stale_after
        paths = self._PATHS

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path not in paths:
                    self.send_response(404)
                    self.end_headers()
                    return
                age = consumer.seconds_since_last_poll()
                stale = consumer.is_poll_stale(stale_after)
                body = json.dumps(
                    {
                        "status": "unhealthy" if stale else "healthy",
                        "check": "pg_queue_poll",
                        "seconds_since_last_poll": round(age, 3),
                        "stale_after_seconds": stale_after,
                    }
                ).encode()
                self.send_response(503 if stale else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                pass  # silence per-request access logging

        self._httpd = HTTPServer(("0.0.0.0", self._port), _Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="pg-consumer-liveness",
        )
        self._thread.start()

    @property
    def bound_port(self) -> int:
        """The actual listening port (resolves ``port=0`` to the OS choice)."""
        if self._httpd is not None:
            return self._httpd.server_address[1]
        return self._port

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


if __name__ == "__main__":
    main()
