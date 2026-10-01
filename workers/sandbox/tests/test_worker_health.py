"""Sandbox worker registers a custom health check (pre-Greptile Important #3).

Every sibling worker (executor, ide_callback, ...) registers a custom health
check via ``WorkerRegistry.register_health_check``; before this fix the
sandbox worker registered none, so ``get_health_checks(WorkerType.SANDBOX)``
returned ``[]`` and port 8092 reported bare liveness only.
"""
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.monitoring.health import HealthStatus


def test_sandbox_worker_registers_a_health_check():
    import sandbox.worker  # noqa: F401 — import triggers registration

    checks = WorkerRegistry.get_health_checks(WorkerType.SANDBOX)
    names = [name for name, _ in checks]
    assert "sandbox_health" in names


def test_sandbox_health_check_returns_healthy():
    from sandbox.worker import check_sandbox_health

    result = check_sandbox_health()
    assert result.status == HealthStatus.HEALTHY
    assert result.name == "sandbox_health"


def test_sandbox_health_check_degrades_if_gate_misbehaves():
    from unittest.mock import patch

    with patch("sandbox.gate.check_code_safe", side_effect=RuntimeError("boom")):
        from sandbox.worker import check_sandbox_health

        result = check_sandbox_health()
    assert result.status == HealthStatus.DEGRADED
