"""Tests for worker registry configuration."""

from shared.enums.worker_enums import WorkerType
from shared.enums.worker_enums_base import QueueName
from shared.infrastructure.config.registry import WorkerRegistry


def test_sandbox_worker_registered():
    cfg = WorkerRegistry._QUEUE_CONFIGS[WorkerType.SANDBOX]
    assert cfg.primary_queue == QueueName.SANDBOX_CODEGEN


def test_sandbox_task_route():
    routing = WorkerRegistry._TASK_ROUTES[WorkerType.SANDBOX]
    routed = {r.pattern: r.queue for r in routing.routes}
    assert routed["execute_sandboxed_code"] == QueueName.SANDBOX_CODEGEN
