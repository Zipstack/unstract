"""Transport-routed dispatch for buffered webhook notifications (UN-3753).

Routes the ``send_webhook_notification`` task through the same
:func:`resolve_transport` flag as the execution path: the PG queue when
``pg_queue_enabled`` for this org, else Celery. **Fail-closed** — with the gate
off (the production default) it resolves to Celery, behaving exactly like the
prior unconditional ``celery_app.send_task`` (zero regression).

DEPLOYMENT PREREQUISITE (PG path): on PG the task lands on the ``notifications``
queue and requires a pg-queue consumer configured with
``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE=notification`` /
``WORKER_PG_QUEUE_CONSUMER_QUEUE=notifications``. **No such service exists in this
repo's compose yet** — none of the ``pg-queue-consumer`` services in
``docker/docker-compose.yaml`` polls ``notifications``, and ``run-worker.sh``'s
``PG_CONSUMER_ROLES`` has no notification role. Until one is deployed the flag must
stay off for the org: enqueued rows would sit undrained (no TTL sweep covers
``pg_queue_message``) and every buffered webhook for that org would be lost.

``args`` and ``queue`` are forwarded verbatim on both paths. ``kwargs`` differ in
exactly two keys, forced on the PG branch only (see the inline note at the branch):
``raise_on_final_failure`` → ``False`` and ``max_retries`` → ``0``. On PG the
payload is additionally JSON-normalized by ``enqueue_task`` (UUIDs/datetimes → str).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, NamedTuple

from pg_queue.producer import enqueue_task
from unstract.core.data_models import is_pg_transport
from workflow_manager.workflow_v2.transport import resolve_transport

logger = logging.getLogger(__name__)

# The fired task name — mirrors the Celery task registered by the notification
# worker; kept as a local constant so the backend doesn't import the workers pkg.
WEBHOOK_NOTIFICATION_TASK = "send_webhook_notification"


# Transport labels for the dispatch metric. During a percentage ramp the one thing
# you need from the logs is "are PG-routed notifications succeeding at the same rate
# as Celery-routed ones?" — a bare task id can't answer that, since a minted PG id
# and a Celery AsyncResult id are indistinguishable to the caller.
PG_TRANSPORT = "pg_queue"
CELERY_TRANSPORT = "celery"


class DispatchResult(NamedTuple):
    """Which transport actually took the dispatch, plus the resulting task id."""

    transport: str
    task_id: str


class PermanentDispatchError(Exception):
    """A dispatch failure that would fail identically on every retry.

    Raised ONLY on the PG path, when ``enqueue_task`` rejects the message for a
    permanent reason (priority range / reply_key+callback exclusivity validation,
    or a payload that can't be JSON-serialized). The Celery path never raises it,
    so a caller can dead-letter on this exception without altering the flag-off
    (Celery) error flow — a Celery ``send_task`` failure stays an ordinary
    ``Exception`` the caller's transient handler owns, exactly as before.
    """


def dispatch_webhook_notification(
    *,
    celery_app: Any,
    args: list[Any],
    kwargs: dict[str, Any],
    queue: str,
    org_string_id: str | None,
) -> DispatchResult:
    """Dispatch ``send_webhook_notification`` on the resolved transport.

    ``args``/``queue`` are forwarded unchanged on both paths, and on the Celery
    branch ``kwargs`` too — so the flag-off path is byte-identical to the legacy
    ``send_task`` call. The PG branch overrides two retry-semantics kwargs (see
    below); nothing else differs.

    Args:
        celery_app: Injected Celery app (the backend's ``celery_service.app``);
            passed in rather than imported so this seam stays trivially testable.
        args: Positional task args, forwarded verbatim.
        kwargs: Keyword task args. Forwarded as-is on Celery; on PG,
            ``raise_on_final_failure`` is overridden to ``False`` and
            ``max_retries`` to ``0`` (the in-task retry loop is a no-op under the
            consumer's eager ``apply()`` — see the inline note). For the buffered
            path this
            carries ``organization_id`` = the buffer's org **pk** (the worker's
            buffer-mark contract) — deliberately a DIFFERENT identifier from the
            ``org_string_id`` param below (the two must not be conflated).
        queue: Target queue name, forwarded verbatim.
        org_string_id: The org's **string** identifier
            (``Organization.organization_id``), used solely for the Flipt
            transport decision — NOT the org pk carried in ``kwargs``. ``None`` (or
            empty) fails closed to Celery.

    Returns:
        A :class:`DispatchResult` carrying which transport took the dispatch and
        the resulting task id (the Celery ``AsyncResult`` id, or the minted PG task
        id). The transport is what makes the caller's dispatch metric answerable
        during a ramp — the two id flavours are otherwise indistinguishable.
    """
    # A buffered notification is a single fire-and-forget task with no natural
    # sticky entity, so mint a fresh id to drive Flipt's percentage bucketing and
    # to serve as the PG task id.
    dispatch_id = str(uuid.uuid4())
    # resolve_transport already normalizes falsy input to Celery, so pass the id
    # straight through (no `or None` needed).
    transport = resolve_transport(
        execution_id=dispatch_id,
        organization_id=org_string_id,
    )
    # Use the shared is_pg_transport() — the single source for "what counts as PG
    # transport" — rather than opening a second comparison site.
    if is_pg_transport(transport):
        # Two PG-only kwarg overrides, both about the SAME thing: the consumer runs
        # the task eagerly via ``task.apply(..., throw=True)``, where Celery's
        # in-task retry loop does not work and its terminal branch is what we need.
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
        # 2. ``raise_on_final_failure`` → False. On BOTH transports the worker marks
        #    the buffers DEAD_LETTER over the internal API *before* it re-raises, so
        #    the re-raise is only a FAILURE-state signal for Celery monitoring (no
        #    redelivery there). On the PG consumer that same raise is treated as a
        #    failure and leaves the row for redelivery, so it must not raise.
        #
        # Together: one POST, buffers dead-lettered, task returns None → the consumer
        # acks (deletes) the row. Retry spacing belongs to the PG layer, not the task.
        # (The Celery branch below keeps kwargs verbatim — byte-identical.)
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
        return DispatchResult(transport=PG_TRANSPORT, task_id=dispatch_id)
    result = celery_app.send_task(
        WEBHOOK_NOTIFICATION_TASK,
        args=args,
        kwargs=kwargs,
        queue=queue,
    )
    return DispatchResult(transport=CELERY_TRANSPORT, task_id=result.id)
