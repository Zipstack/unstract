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
from unstract.core.data_models import TaskPayload

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
) -> TaskPayload:
    """Build the JSON-serialisable task payload for the PG queue."""
    return TaskPayload(
        task_name=task_name,
        args=list(args) if args is not None else [],
        kwargs=dict(kwargs) if kwargs is not None else {},
        queue=queue,
        fairness=fairness.to_dict() if fairness is not None else None,
    )
