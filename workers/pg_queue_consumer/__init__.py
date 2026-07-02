"""PG-queue consumer worker — a standalone process that drains ``pg_queue_message``.

It bootstraps a source worker's Celery app (registering that worker type's
tasks, like ``celery -A worker worker`` for a single type) so the consumer can
resolve and run them, then runs the
:class:`~queue_backend.pg_queue.consumer.PgQueueConsumer` poll loop. The source
worker type is selected by ``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE`` (default
``notification``); see ``__main__`` for why this must precede ``import worker``.

Launch via ``python -m pg_queue_consumer`` or ``./run-worker.sh
pg-queue-consumer``. Config via ``WORKER_PG_QUEUE_CONSUMER_*`` env.
"""
