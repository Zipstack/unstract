"""Queue-backend seam.

Single place where the queue substrate lives. Postgres is the only transport and
:class:`~queue_backend.pg_barrier.PgBarrier` the only fan-in barrier.

**History.** Both were once selectable. ``dispatch()`` read a
``WORKER_PG_QUEUE_ENABLED_TASKS`` allow-list (set nowhere, so everything
defaulted to Celery — removed in UN-4046), and the barrier substrate was chosen
at import time by ``WORKER_BARRIER_BACKEND`` from ``chord`` /
``redis`` / ``pg``. The Celery and Redis barriers, the env var and the
``get_barrier()`` factory went with the Celery transport in UN-4078.

**Every dispatch rides PG and needs its consumer running**, or the message is
durably enqueued and never executed, with no error at the producer. The
deployment chart (``validate-pg-worker-fleet.yaml``, in the closed-source
``unstract-cloud`` repo — it is not in this tree) refuses a partial fleet at
render time for exactly this reason.
"""

from .barrier import Barrier, BarrierHandle
from .decorator import worker_task
from .dispatch import dispatch
from .fairness import FairnessKey
from .pg_barrier import PgBarrier, barrier_pg_abort
from .routing import QueueBackend, select_backend

__all__ = [
    "Barrier",
    "BarrierHandle",
    "FairnessKey",
    "PgBarrier",
    "QueueBackend",
    "barrier_pg_abort",
    "dispatch",
    "select_backend",
    "worker_task",
]
