"""Shared polling helper for the PG result backends.

A capped-exponential-backoff poll loop (PgBouncer-safe; no LISTEN/NOTIFY) used by
*both* PG result pollers — the backend's ``DjangoQueueTransport.wait_for_result``
(Django ORM) and the workers' ``PgResultBackend.wait_for_result`` (psycopg2). It
has no Django / psycopg / SDK dependency, so it lives in ``unstract.core`` where
both trees import it — the backoff lives in exactly one place to tune.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

_T = TypeVar("_T")


def poll_for_row(
    fetch: Callable[[], _T | None],
    timeout: float,
    *,
    between_polls: Callable[[], None] | None = None,
    initial: float = 0.2,
    maximum: float = 2.0,
) -> _T | None:
    """Poll ``fetch()`` until it returns non-``None`` or *timeout* elapses.

    Capped exponential backoff; the final sleep is clamped so we never overshoot the
    deadline. ``between_polls`` runs once before each sleep — the backend poller
    passes ``close_old_connections`` to release the DB connection between polls.
    Returns the fetched row, or ``None`` on timeout.
    """
    deadline = time.monotonic() + timeout
    delay = initial
    while True:
        row = fetch()
        if row is not None:
            return row
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        if between_polls is not None:
            between_polls()
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, maximum)
