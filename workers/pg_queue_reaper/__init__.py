"""Launcher package for the PG-queue reaper process.

A thin top-level package so the reaper has a stable ``python -m pg_queue_reaper``
invocation that ``run-worker.sh`` can launch and pgrep-match — mirroring
``pg_queue_consumer``. The actual loop lives in
``queue_backend.pg_queue.reaper``.
"""
