"""Payload carried *inside* a PG queue row, for a dispatched task.

Not to be confused with the queue **row** itself (the backend's
``PgQueueMessage`` model / ``pg_queue_message`` table). This is the shape
of the row's ``message`` JSONB column when the message is a task: a
``dispatch()`` that routes to PG (9b) serialises a :class:`TaskPayload`
into that column, and the consumer poll loop (9c) decodes it and runs the
task. Producer↔consumer contract — keep both sides reading the same keys.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

# TaskPayload now lives in unstract.core (shared backend↔worker wire contract);
# re-exported here so existing ``from .task_payload import TaskPayload`` imports
# keep working. The ``to_payload`` builder stays worker-side (it depends on the
# worker-only ``FairnessKey``).
from unstract.core.data_models import ContinuationSpec, TaskPayload

if TYPE_CHECKING:
    from ..fairness import FairnessKey

__all__ = ["TaskPayload", "to_payload"]


def to_payload(
    task_name: str,
    *,
    args: Sequence[Any] | None = None,
    kwargs: Mapping[str, Any] | None = None,
    queue: str | None = None,
    fairness: FairnessKey | None = None,
    reply_key: str | None = None,
    on_success: ContinuationSpec | None = None,
    on_error: ContinuationSpec | None = None,
    task_id: str | None = None,
) -> TaskPayload:
    """Build the JSON-serialisable task payload for the PG queue.

    ``reply_key`` marks a **request-reply** dispatch (the executor RPC on PG):
    the executor consumer writes the task's result/error to ``pg_task_result``
    under it for the blocking caller to poll. Omitted = fire-and-forget.

    ``on_success`` / ``on_error`` mark an **async/callback** dispatch
    (``dispatch_with_callback``): the executor consumer self-chains the matching
    continuation after the task runs (success → ``on_success``, failure →
    ``on_error``). ``task_id`` is the dispatch id the consumer prepends to
    ``on_error`` as the failed id (Celery ``link_error`` parity). These are
    mutually exclusive with ``reply_key`` (blocking vs callback dispatch) — passing
    both is rejected, since the consumer checks ``reply_key`` first and would
    silently drop the callback.
    """
    if reply_key is not None and (on_success is not None or on_error is not None):
        raise ValueError(
            "reply_key (request-reply) and on_success/on_error (callback) are "
            "mutually exclusive"
        )
    payload = TaskPayload(
        task_name=task_name,
        args=list(args) if args is not None else [],
        kwargs=dict(kwargs) if kwargs is not None else {},
        queue=queue,
        fairness=fairness.to_dict() if fairness is not None else None,
    )
    # Each optional key is set only when present — keeps fire-and-forget rows
    # byte-identical to before these fields existed (mirrors the backend producer).
    if reply_key is not None:
        payload["reply_key"] = reply_key
    if on_success is not None:
        payload["on_success"] = on_success
    if on_error is not None:
        payload["on_error"] = on_error
    if task_id is not None:
        payload["task_id"] = task_id
    return payload
