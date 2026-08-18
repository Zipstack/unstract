"""Shared bootstrap for the PG-queue consumer entrypoints.

Both the single-process launcher (``__main__``) and the prefork supervisor's
children must select the source worker type *before* ``import worker`` (which
reads ``WORKER_TYPE`` at import time to register that type's tasks). Kept in a
neutral module — not ``__main__`` — so ``supervisor`` can import it without
triggering the ``python -m`` entry.
"""

import os


def select_source_worker_type() -> None:
    """Point ``WORKER_TYPE`` at the source worker whose tasks back this consumer.

    Overwrites (not ``setdefault``): the launcher's own ``WORKER_TYPE`` is the
    ``pg_queue_consumer`` pseudo-type, which owns no tasks — a plain ``import
    worker`` would fall back to the ``general`` worker and drop every message as an
    unknown task. Default ``notification`` (the worker owning the first migrated
    leaf task). Must run before ``import worker``.
    """
    os.environ["WORKER_TYPE"] = os.environ.get(
        "WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE", "notification"
    )
