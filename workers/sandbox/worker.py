"""Sandbox Worker — consumes ``sandbox_codegen``; runs generated code
out-of-process in a scrubbed, rlimit-bounded subprocess (spec §6.3).
"""
import sandbox.tasks  # noqa: F401 — registers execute_sandboxed_code
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.setup(WorkerType.SANDBOX)
app, config = WorkerBuilder.build_celery_app(WorkerType.SANDBOX)


def check_sandbox_health():
    """Custom health check for the sandbox worker.

    Kept fast and side-effect-free (no real subprocess): it only proves the
    gate module imports and behaves -- rejecting a known-bad snippet and
    allowing a trivial safe one -- which is the one in-process dependency
    every ``execute_sandboxed_code`` task relies on before it ever spawns a
    child. Mirrors ``ide_callback/worker.py``'s ``check_ide_callback_health``.
    """
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from sandbox.gate import check_code_safe

        bad_ok, _ = check_code_safe("import os\nos.system('id')\n")
        good_ok, good_reason = check_code_safe("x = 1 + 1\n")
        gate_healthy = bad_ok is False and good_ok is True

        if gate_healthy:
            return HealthCheckResult(
                name="sandbox_health",
                status=HealthStatus.HEALTHY,
                message="Sandbox worker is healthy",
                details={"worker_type": "sandbox", "gate": "healthy"},
            )
        return HealthCheckResult(
            name="sandbox_health",
            status=HealthStatus.DEGRADED,
            message="Sandbox safety gate check misbehaving",
            details={
                "bad_snippet_rejected": bad_ok is False,
                "good_snippet_allowed": good_ok,
                "good_snippet_reason": good_reason,
            },
        )

    except Exception as e:
        return HealthCheckResult(
            name="sandbox_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check
WorkerRegistry.register_health_check(
    WorkerType.SANDBOX, "sandbox_health", check_sandbox_health
)
