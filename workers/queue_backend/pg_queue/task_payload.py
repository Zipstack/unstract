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
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ..fairness import FairnessKey


class TaskPayload(TypedDict):
    """Everything the 9c consumer needs to run a PG-routed task.

    ``fairness`` is the serialised :class:`FairnessKey` (``to_dict()``) or
    ``None`` — the consumer rebuilds the ``x-fairness-key`` header from it,
    mirroring the Celery dispatch path.
    """

    task_name: str
    args: list[Any]
    kwargs: dict[str, Any]
    queue: str | None
    fairness: dict[str, Any] | None


def to_payload(
    task_name: str,
    *,
    args: Sequence[Any] | None = None,
    kwargs: Mapping[str, Any] | None = None,
    queue: str | None = None,
    fairness: FairnessKey | None = None,
) -> TaskPayload:
    """Build the JSON-serialisable task payload for the PG queue."""
    return TaskPayload(
        task_name=task_name,
        args=list(args) if args is not None else [],
        kwargs=dict(kwargs) if kwargs is not None else {},
        queue=queue,
        fairness=fairness.to_dict() if fairness is not None else None,
    )
