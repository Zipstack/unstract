"""Transport-routed dispatch for buffered webhook notifications (UN-3753).

Routes the ``send_webhook_notification`` task through the same
:func:`resolve_transport` flag as the execution path: the PG queue when
``pg_queue_enabled`` for this org, else Celery. **Fail-closed** — with the gate
off (the production default) it resolves to Celery, behaving exactly like the
prior unconditional ``celery_app.send_task`` (zero regression). On PG the task
is drained by the PG notification consumer on the ``notifications`` queue.

The same ``args``/``kwargs``/``queue`` are forwarded on both paths; on PG they're
JSON-normalized by ``enqueue_task`` (UUIDs/datetimes → str), so the consumer sees
the same payload the Celery worker would.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pg_queue.producer import enqueue_task
from workflow_manager.workflow_v2.transport import resolve_transport

from unstract.core.data_models import is_pg_transport

logger = logging.getLogger(__name__)

# The fired task name — mirrors the Celery task registered by the notification
# worker; kept as a local constant so the backend doesn't import the workers pkg.
WEBHOOK_NOTIFICATION_TASK = "send_webhook_notification"


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
) -> str:
    """Dispatch ``send_webhook_notification`` on the resolved transport.

    ``args``/``kwargs``/``queue`` are forwarded unchanged on both paths, so the
    flag-off (Celery) path is byte-identical to the legacy ``send_task`` call.

    Args:
        celery_app: Injected Celery app (the backend's ``celery_service.app``);
            passed in rather than imported so this seam stays trivially testable.
        args: Positional task args, forwarded verbatim.
        kwargs: Keyword task args, forwarded verbatim. For the buffered path this
            carries ``organization_id`` = the buffer's org **pk** (the worker's
            buffer-mark contract) — deliberately a DIFFERENT identifier from the
            ``org_string_id`` param below (the two must not be conflated).
        queue: Target queue name, forwarded verbatim.
        org_string_id: The org's **string** identifier
            (``Organization.organization_id``), used solely for the Flipt
            transport decision — NOT the org pk carried in ``kwargs``. ``None`` (or
            empty) fails closed to Celery.

    Returns:
        A task id string — the Celery ``AsyncResult`` id on the Celery path, or
        the minted PG task id on the PG path. Returned for symmetry / any future
        caller; the sole current caller (fire-and-forget) discards it.
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
        try:
            enqueue_task(
                task_name=WEBHOOK_NOTIFICATION_TASK,
                queue=queue,
                args=args,
                kwargs=kwargs,
                # enqueue_task's org_id is str-typed — coerce None→"" (unlike the
                # routing arg above, this `or ""` is load-bearing).
                org_id=org_string_id or "",
                task_id=dispatch_id,
            )
        except (ValueError, TypeError) as exc:
            # PG-only permanent failure (enqueue_task validation / JSON encode):
            # re-raise as PermanentDispatchError so the caller dead-letters it.
            # A transient PG error (DB down) is NOT wrapped — it propagates as an
            # ordinary Exception into the caller's retry (revert-to-PENDING) path.
            raise PermanentDispatchError(str(exc)) from exc
        logger.info(
            "Webhook notification enqueued on PG '%s' queue (task_id=%s)",
            queue,
            dispatch_id,
        )
        return dispatch_id
    result = celery_app.send_task(
        WEBHOOK_NOTIFICATION_TASK,
        args=args,
        kwargs=kwargs,
        queue=queue,
    )
    return result.id
