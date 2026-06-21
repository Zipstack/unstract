"""Transport-agnostic helpers for the executor-RPC dispatchers.

The PG executor dispatch lives in two near-identical mirrors — backend (Django
ORM) and workers (psycopg2) ``pg_queue/executor_rpc.py`` — because neither
codebase can import the other and there is no shared home for the transport logic
yet (the SDK is transport-agnostic by contract, and ``unstract.sdk1`` →
``unstract.core`` would be circular). Retiring that mirror wholesale is tracked
as a follow-up (a dedicated shared executor-RPC package).

These two helpers, however, are the genuinely **transport-agnostic** pieces of
the async/callback path: they have no Django / psycopg / SDK dependency. So they
live here in ``unstract.core`` (alongside :class:`ContinuationSpec`, the wire
type one of them produces) and BOTH mirrors import them — removing that slice of
the duplication today rather than waiting for the full package.
"""

from __future__ import annotations

from typing import Any

from .data_models import ContinuationSpec


class DispatchHandle:
    """Minimal duck-type of Celery ``AsyncResult`` for the PG callback path.

    ``dispatch_with_callback`` callers read only ``.id`` (to return the task id in
    the HTTP 202 response); they must NOT call ``.get()`` — the result arrives via
    the self-chained callback (WebSocket), not by polling here. Exposing just
    ``.id`` lets a PG dispatch return the same shape the call sites already use.
    """

    __slots__ = ("id",)

    def __init__(self, task_id: str) -> None:
        self.id = task_id


def signature_to_continuation(sig: Any | None) -> ContinuationSpec | None:
    """Translate a Celery ``Signature`` to a serialisable continuation spec.

    Reads only the three attributes PG self-chaining needs — task name, kwargs,
    target queue — so the prompt-studio call sites keep passing
    ``signature(name, kwargs=..., queue=...)`` unchanged; only the PG branch
    translates. ``None`` (no callback for that outcome) passes through. A signature
    without a queue is a configuration error: PG routes by the row's queue and must
    not silently default it, so we fail fast.
    """
    if sig is None:
        return None
    queue = (getattr(sig, "options", None) or {}).get("queue")
    if not queue:
        raise ValueError(
            f"callback signature {getattr(sig, 'task', sig)!r} has no queue; "
            "PG self-chaining routes by the row's queue and cannot default it"
        )
    return ContinuationSpec(
        task_name=sig.task,
        kwargs=dict(getattr(sig, "kwargs", None) or {}),
        queue=queue,
    )
