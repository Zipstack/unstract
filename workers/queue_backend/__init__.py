"""Queue-backend seam.

Single place where the substrate choice (Celery today; PG Queue later)
lives. Both entry points are transparent passthroughs to Celery today.
"""

from .decorator import worker_task
from .dispatch import dispatch
from .fairness import FairnessKey

__all__ = ["FairnessKey", "dispatch", "worker_task"]
