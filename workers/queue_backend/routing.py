"""Queue-transport routing.

PG is the only transport. :func:`select_backend` returns ``PG``
unconditionally and :func:`resolve_backend` applies the per-call override on
top of it.

**History (UN-4046).** This was the Strangler-Fig gate: a per-task opt-in
allow-list, ``WORKER_PG_QUEUE_ENABLED_TASKS``, with everything not listed
routed to Celery. That allow-list was never set in any environment, so every
dispatch lacking an explicit ``backend=`` override went to Celery — harmless
while Celery consumers existed, and a queue nothing drains once they were
scaled to zero. The allow-list and the Celery default went with the
``pg_queue_enabled`` flag.

**The per-call override survives** (``resolve_backend(task_name, override)``).
It is how the coupled execution pipeline (``async_execute_bin`` → file
processing → callback, with the barrier fan-in) pins a whole execution to one
substrate. That mattered when two substrates existed; it is kept because
stating the transport at the dispatch site reads as intent rather than as
reliance on a module default, and because the barrier's fan-in still threads it.

**Observability.** The first dispatch of each task name is logged at INFO by
``dispatch()``, so the signal survives a default log config.
"""

from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class QueueBackend(StrEnum):
    """Transport a dispatch is routed to.

    ``StrEnum`` (3.11+) is inherited for symmetry with ``BarrierBackend``,
    but unlike that enum this one is never read from / written to env —
    it is never read from env at all. So callers MUST compare by identity
    (``backend is QueueBackend.PG``), never ``== "pg"``: ``StrEnum`` makes a
    typo'd ``== "cellery"`` a silent ``False`` rather than an error.
    """

    CELERY = "celery"
    PG = "pg"


def select_backend() -> QueueBackend:
    """Return the transport a dispatch should ride: always ``PG``.

    This used to consult a ``WORKER_PG_QUEUE_ENABLED_TASKS`` allow-list and fall
    back to ``CELERY`` for anything not opted in. The allow-list was set nowhere,
    so every dispatch without an explicit ``backend=`` override published to
    RabbitMQ — which, with no Celery consumers, is a queue nothing drains
    (UN-4046). PG is the only transport now, so there is nothing to select.

    Takes no argument: the answer no longer depends on the task. It used to.
    """
    return QueueBackend.PG


def resolve_backend(task_name: str, override: QueueBackend | None) -> QueueBackend:
    """Resolve the transport for a dispatch, applying the per-call override.

    The single home for the override-wins-else-``select_backend`` precedence so the
    rule reads in one place (and ``dispatch()`` plus the call sites
    share it):

    - ``override`` is ``None`` → defer to :func:`select_backend`, which is now
      unconditionally ``PG``.
    - ``override`` is a :class:`QueueBackend` → it wins. Retained because the
      execution-level pipeline pins a whole execution's header/callback
      dispatches explicitly, which reads at the call site as intent rather than
      as reliance on a default.

    Never raises — both branches resolve to a valid :class:`QueueBackend`.
    """
    return override if override is not None else select_backend()
