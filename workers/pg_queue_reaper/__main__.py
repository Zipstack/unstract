"""Entry point: run the PG-queue reaper (leader-elected recovery loop).

Unlike the consumer, the reaper runs no Celery tasks — it only does SQL recovery
(the barrier-orphan sweep) — so it needs **no** worker-app bootstrap (no
``import worker``, no ``WORKER_TYPE`` juggling). This package exists purely so the
process has a stable ``python -m pg_queue_reaper`` name that ``run-worker.sh`` can
launch and match, parallel to ``pg_queue_consumer``.

Launch via ``python -m pg_queue_reaper`` or ``./run-worker.sh reaper``.
"""

from queue_backend.pg_queue.reaper import main

if __name__ == "__main__":
    main()
