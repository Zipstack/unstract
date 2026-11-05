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


def test_sandbox_health_check_degrades_when_the_gate_raises():
    from unittest.mock import patch

    with patch("sandbox.gate.check_code_safe", side_effect=RuntimeError("boom")):
        from sandbox.worker import check_sandbox_health

        result = check_sandbox_health()
    assert result.status == HealthStatus.DEGRADED


def test_sandbox_health_is_degraded_when_the_gate_returns_wrong_answers():
    """The branch `test_sandbox_health_check_degrades_if_gate_misbehaves` is
    named for but never reaches.

    That test raises from `check_code_safe`, which lands in the outer
    `except Exception` and returns "Health check failed: ...". The branch that
    matters is the gate ANSWERING WRONGLY -- accepting hostile code -- which
    reports `bad_snippet_rejected` in `details`. A regression making
    `gate_healthy` always true would otherwise ship a probe reporting HEALTHY
    for a gate that accepts `os.system('id')`.
    """
    from unittest.mock import patch

    # The gate accepts everything, including the hostile probe snippet.
    with patch("sandbox.gate.check_code_safe", return_value=(True, "")):
        from sandbox.worker import check_sandbox_health

        result = check_sandbox_health()
    assert result.status == HealthStatus.DEGRADED, result
    assert result.details["bad_snippet_rejected"] is False, result.details
