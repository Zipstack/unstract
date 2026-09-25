"""PG-queue dispatch for buffered webhook notifications (UN-3753, UN-4046).

Enqueues ``send_webhook_notification`` onto the PG queue the notification
consumer polls (``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE=notification``).

This used to route through ``resolve_transport``/``pg_queue_enabled`` and fall
back to ``celery_app.send_task``. The flag is gone (UN-4046) and PG is the only
transport, so the Celery branch went with it — along with the ``DispatchResult``
transport label, which existed only to tell the two apart during a ramp.

``args`` and ``queue`` are forwarded verbatim; the payload is JSON-normalized by
``enqueue_task`` (UUIDs/datetimes → str). Two ``kwargs`` are forced — see the
inline note at the enqueue.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pg_queue.producer import enqueue_task

logger = logging.getLogger(__name__)

# The fired task name — mirrors the Celery task registered by the notification
# worker; kept as a local constant so the backend doesn't import the workers pkg.
WEBHOOK_NOTIFICATION_TASK = "send_webhook_notification"


class PermanentDispatchError(Exception):
    """A dispatch failure that would fail identically on every retry.

    Raised when ``enqueue_task`` rejects the message for a permanent reason
    (priority range / reply_key+callback exclusivity validation, or a payload that
    can't be JSON-serialized), so a caller can dead-letter on it. A transient PG
    error (DB down) is deliberately NOT wrapped — it propagates as an ordinary
    ``Exception`` into the caller's retry path.
    """


def dispatch_webhook_notification(
    *,
    args: list[Any],
    kwargs: dict[str, Any],
    queue: str,
    org_string_id: str | None,
) -> str:
    """Enqueue ``send_webhook_notification`` on the PG queue.

    Args:
        args: Positional task args, forwarded verbatim.
        kwargs: Keyword task args. ``raise_on_final_failure`` is overridden to
            ``False`` and ``max_retries`` to ``0`` (the in-task retry loop is a
            no-op under the consumer's eager ``apply()`` — see the inline note).
            For the buffered path this carries ``organization_id`` = the buffer's
            org **pk** (the worker's buffer-mark contract) — deliberately a
            DIFFERENT identifier from ``org_string_id`` (the two must not be
            conflated).
        queue: Target queue name, forwarded verbatim.
        org_string_id: The org's **string** identifier
            (``Organization.organization_id``), recorded on the queue row for
            fairness/routing.

    Returns:
        The minted PG task id.
    """
    # A buffered notification is a single fire-and-forget task with no natural
    # sticky entity, so mint a fresh id to serve as the PG task id.
    dispatch_id = str(uuid.uuid4())
    # Two kwarg overrides, both about the SAME thing: the consumer runs the task
    # eagerly via ``task.apply(..., throw=True)``, where Celery's in-task retry
    # loop does not work and its terminal branch is what we need.
    #
    # 1. ``max_retries`` → 0. Under ``apply()`` ``self.request.retries`` is ALWAYS
    #    0, so the worker's ``if self.request.retries < max_retries`` guard
    #    (workers/notification/tasks.py) is true on the FIRST failure for any
    #    max_retries >= 1 and calls ``self.retry(...)``, which raises ``Retry``;
    #    with ``throw=True`` that propagates straight out of ``apply()`` and the
    #    terminal branch is never reached — so the buffers are never marked
    #    DEAD_LETTER and ``raise_on_final_failure`` is never even read. The
    #    consumer's ``except Exception`` then leaves the row for vt-expiry
    #    redelivery, re-POSTing the subscriber every time. Forcing 0 sends the
    #    task down the terminal branch on the first failure instead.
    # 2. ``raise_on_final_failure`` → False. The worker marks the buffers
    #    DEAD_LETTER over the internal API *before* it re-raises, so the re-raise
    #    carries no state the caller needs — and on the PG consumer that raise is
    #    treated as a failure and leaves the row for redelivery, so it must not
    #    raise.
    #
    # Together: one POST, buffers dead-lettered, task returns None → the consumer
    # acks (deletes) the row. Retry spacing belongs to the PG layer, not the task.
    pg_kwargs = {**kwargs, "raise_on_final_failure": False, "max_retries": 0}
    try:
        msg_id = enqueue_task(
            task_name=WEBHOOK_NOTIFICATION_TASK,
            queue=queue,
            args=args,
            kwargs=pg_kwargs,
            # enqueue_task types org_id as str; None→"" here satisfies that
            # type only, not runtime — enqueue_task itself re-coerces
            # ``org_id or ""`` at insert (producer.py), so this has no runtime
            # effect.
            org_id=org_string_id or "",
            task_id=dispatch_id,
        )
    except (ValueError, TypeError) as exc:
        # PG-only permanent failure (enqueue_task validation / JSON encode):
        # re-raise as PermanentDispatchError so the caller dead-letters it.
        # A transient PG error (DB down) is NOT wrapped — it propagates as an
        # ordinary Exception into the caller's retry (revert-to-PENDING) path.
        raise PermanentDispatchError(str(exc)) from exc
    # msg_id correlates this line with the producer's own ``msg_id=`` log, so a
    # dropped notification can be traced across the seam/producer boundary.
    logger.info(
        "Webhook notification enqueued on PG '%s' queue (task_id=%s msg_id=%s)",
        queue,
        dispatch_id,
        msg_id,
    )
    return dispatch_id
