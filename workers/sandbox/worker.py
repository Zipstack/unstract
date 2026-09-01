"""Sandbox Worker — consumes ``sandbox_codegen``; runs generated code
out-of-process in a scrubbed, rlimit-bounded subprocess (spec §6.3).
"""
import sandbox.tasks  # noqa: F401 — registers execute_sandboxed_code
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.setup(WorkerType.SANDBOX)
app, config = WorkerBuilder.build_celery_app(WorkerType.SANDBOX)
