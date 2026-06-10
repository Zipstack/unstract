"""Queue-backend seam.

Single place where the substrate choice (Celery today; PG Queue later)
lives. Both entry points are transparent passthroughs to Celery today.
"""

from .barrier import Barrier, BarrierHandle, CeleryChordBarrier
from .decorator import worker_task
from .dispatch import dispatch
from .fairness import FairnessKey

__all__ = [
    "Barrier",
    "BarrierHandle",
    "CeleryChordBarrier",
    "FairnessKey",
    "dispatch",
    "worker_task",
]
