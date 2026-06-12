"""Transparent wrapper over ``celery.shared_task``.

Accepts both decorator forms (bare and parameterised); a later phase
may register the task body with non-Celery substrates from here too.
"""

from __future__ import annotations

from typing import Any

from celery import shared_task


def worker_task(*args: Any, **kwargs: Any) -> Any:
    """Register a function as a worker task.

    ``Any`` return type because ``shared_task`` produces a
    ``PromiseProxy`` for the bare form and a decorator factory for the
    parameterised form.
    """
    return shared_task(*args, **kwargs)
