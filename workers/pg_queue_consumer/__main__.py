"""Entry point: bootstrap a worker app's tasks, then run the PG-queue consumer.

The root ``worker`` module loads exactly ONE worker type's tasks, chosen by the
``WORKER_TYPE`` env (``worker.py`` → ``WorkerBuilder.build_celery_app`` →
imports that type's ``tasks.py``). The PG consumer drains a specific source
worker's queue, so it must register THAT worker's tasks: we set ``WORKER_TYPE``
from ``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE`` (default ``notification`` — the
first migrated leaf task) BEFORE importing ``worker``.

This override is required: ``run-worker.sh`` exports its own ``WORKER_TYPE``
(the consumer pseudo-type ``pg_queue_consumer``, which owns no tasks), so a
plain import would fall back to the ``general`` worker's tasks and every
notification message would be dropped as an unknown task. The consumer's
startup guard only catches an *empty* registry, not a *wrong* one — so the
right worker type must be selected here.

Launch via ``python -m pg_queue_consumer`` or ``./run-worker.sh pg-queue-consumer``.
"""

import os

# Select the source worker whose tasks back this consumer's queue. Must run
# BEFORE `import worker`, which reads WORKER_TYPE at import time. We overwrite
# (not setdefault) because the launcher's own WORKER_TYPE owns no tasks.
os.environ["WORKER_TYPE"] = os.environ.get(
    "WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE", "notification"
)

import worker  # noqa: E402,F401 — side-effect: registers the source worker's tasks
from queue_backend.pg_queue.consumer import main  # noqa: E402

if __name__ == "__main__":
    main()
