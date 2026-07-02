"""Entry point: bootstrap a worker app's tasks, then run the PG-queue consumer.

The root ``worker`` module loads exactly ONE worker type's tasks, chosen by the
``WORKER_TYPE`` env: ``worker.py`` builds the Celery app via
``WorkerBuilder.build_celery_app`` (which configures, but does NOT import
tasks), then — in separate module-level logic in ``worker.py`` — ``importlib``-
loads that type's ``tasks.py``. The PG consumer drains a specific source
worker's queue, so it must register THAT worker's tasks: we set ``WORKER_TYPE``
from ``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE`` (default ``notification`` — the
worker that owns the first migrated leaf task, ``send_webhook_notification``)
BEFORE importing ``worker``.

This override is required: ``run-worker.sh`` exports its own ``WORKER_TYPE``
(the consumer pseudo-type ``pg_queue_consumer``, which owns no tasks), so a
plain import would fall back to the ``general`` worker's tasks and every
message for the intended worker would be dropped as an unknown task. The
consumer's startup guard only catches an *empty* registry, not a *wrong* one —
so the right worker type must be selected here.

Launch via ``python -m pg_queue_consumer`` or ``./run-worker.sh pg-queue-consumer``.
"""


def _bootstrap_and_run() -> None:
    # CONCURRENCY > 1 → run a prefork supervisor (UN-3606): N isolated consumer
    # children, the PG analogue of Celery --pool=prefork --concurrency=N. The
    # supervisor forks the children (each does its OWN worker bootstrap, so no
    # connections are inherited across the fork) and owns the single health port.
    # CONCURRENCY = 1 (default) keeps the plain single-process path below,
    # byte-identical to before the supervisor existed.
    #
    # Kept inside this guarded function (not at module scope) so the env mutation
    # and the heavy `import worker` bootstrap only happen on the `python -m`
    # entry — never as a side-effect if this module is imported by a test, IDE,
    # or type-checker walking `__main__` files.
    from pg_queue_consumer.supervisor import concurrency_from_env, run_supervised

    concurrency = concurrency_from_env()
    if concurrency > 1:
        run_supervised(concurrency)
        return

    # Single-process path: select the source worker whose tasks back this
    # consumer's queue (must run BEFORE `import worker`, which reads WORKER_TYPE at
    # import time). Shared with the supervisor's children via _bootstrap.
    from pg_queue_consumer._bootstrap import select_source_worker_type

    select_source_worker_type()

    import worker  # noqa: F401 — side-effect: registers the source worker's tasks
    from queue_backend.pg_queue.consumer import main

    main()


if __name__ == "__main__":
    _bootstrap_and_run()
