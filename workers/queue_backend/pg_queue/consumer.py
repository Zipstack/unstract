"""PG queue consumer — claims tasks from ``pg_queue_message`` and runs them.

The producer side (9b) enqueues a :class:`~queue_backend.pg_queue.TaskPayload`
when a task is routed to PG. This is the other half: it polls the queue with
``SKIP LOCKED`` + a visibility timeout (via :class:`PgQueueClient`), runs each
claimed task **in-process** (no Celery broker), and acks by deleting the row.

A task that fails — or a crash before ack — is redelivered once its ``vt``
expires (at-least-once; tasks must be idempotent). A task name not in the
registry can never run, so it is dropped (with a loud log) rather than left to
redeliver forever as a poison message.

Run as ``python -m queue_backend.pg_queue.consumer`` (config via env). The
worker bootstrap must have imported/registered the Celery tasks so they
resolve in ``current_app.tasks``.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import TYPE_CHECKING

from celery import current_app

from .client import PgQueueClient

if TYPE_CHECKING:
    from celery import Celery

    from .client import QueueMessage

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE = "default"
_DEFAULT_BATCH = 10
_DEFAULT_VT_SECONDS = 30
_DEFAULT_POLL_INTERVAL = 0.1
_DEFAULT_BACKOFF_MAX = 2.0


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
    ) -> None:
        self.queue_name = queue_name
        self._client = client if client is not None else PgQueueClient()
        self._app = app if app is not None else current_app
        self.batch_size = batch_size
        self.vt_seconds = vt_seconds
        self.poll_interval = poll_interval
        self.backoff_max = backoff_max
        self._running = False

    def poll_once(self) -> int:
        """Claim + process one batch; returns the number of messages claimed."""
        messages = self._client.read(
            self.queue_name, vt_seconds=self.vt_seconds, qty=self.batch_size
        )
        for message in messages:
            self._handle(message)
        return len(messages)

    def _handle(self, message: QueueMessage) -> None:
        payload = message.message
        task_name = payload.get("task_name")
        task = self._app.tasks.get(task_name)
        if task is None:
            # Can never run → drop (and shout) rather than redeliver forever.
            logger.error(
                "PG-queue consumer: unknown task %r (msg_id=%s) — dropping",
                task_name,
                message.msg_id,
            )
            self._client.delete(message.msg_id)
            return
        try:
            # Run the task body in-process (eager), propagating failures.
            task.apply(
                args=payload.get("args") or [],
                kwargs=payload.get("kwargs") or {},
                throw=True,
            )
        except Exception:
            # Leave the row: its vt expires and it is redelivered.
            logger.exception(
                "PG-queue consumer: task %r (msg_id=%s) failed — leaving for "
                "vt-expiry redelivery",
                task_name,
                message.msg_id,
            )
            return
        self._client.delete(message.msg_id)  # ack

    def run(self, *, install_signals: bool = True) -> None:
        """Poll loop with empty-queue backoff and graceful shutdown."""
        self._running = True
        if install_signals:
            self._install_signal_handlers()
        logger.info(
            "PG-queue consumer started (queue=%r, batch=%s, vt=%ss)",
            self.queue_name,
            self.batch_size,
            self.vt_seconds,
        )
        backoff = self.poll_interval
        while self._running:
            if self.poll_once():
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
            logger.debug(
                "PG-queue consumer: signal handlers not installed (non-main thread)"
            )


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    PgQueueConsumer(
        queue_name=os.getenv("WORKER_PG_QUEUE_CONSUMER_QUEUE", _DEFAULT_QUEUE),
        batch_size=int(os.getenv("WORKER_PG_QUEUE_CONSUMER_BATCH", _DEFAULT_BATCH)),
        vt_seconds=int(
            os.getenv("WORKER_PG_QUEUE_CONSUMER_VT_SECONDS", _DEFAULT_VT_SECONDS)
        ),
        poll_interval=float(
            os.getenv("WORKER_PG_QUEUE_CONSUMER_POLL_INTERVAL", _DEFAULT_POLL_INTERVAL)
        ),
    ).run()


if __name__ == "__main__":
    main()
