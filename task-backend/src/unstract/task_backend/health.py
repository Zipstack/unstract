"""Health check system for task backend worker."""

import logging
import time
from dataclasses import dataclass

from unstract.task_abstraction import get_backend
from unstract.task_abstraction.models import BackendConfig

from .config import TaskBackendConfig

logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Individual health check result."""

    name: str
    status: str  # "healthy", "unhealthy", "unknown"
    message: str
    duration_ms: float | None = None
    metadata: dict | None = None

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"


@dataclass
class HealthStatus:
    """Overall health status."""

    is_healthy: bool
    checks: list[HealthCheck]
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "is_healthy": self.is_healthy,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                    "duration_ms": check.duration_ms,
                    "metadata": check.metadata or {},
                }
                for check in self.checks
            ],
        }


class HealthChecker:
    """Health checker for task backend worker."""

    def __init__(self, config: TaskBackendConfig):
        self.config = config

    def check_backend_connection(self) -> HealthCheck:
        """Check if backend is reachable and healthy."""
        start_time = time.time()

        try:
            # Create backend configuration
            backend_config = BackendConfig(
                backend_type=self.config.backend_type,
                connection_params=self._get_connection_params(),
                worker_config={},
            )

            # Create backend instance
            backend = get_backend(config=backend_config)

            # Test connection
            is_connected = backend.is_connected()

            duration_ms = (time.time() - start_time) * 1000

            if is_connected:
                return HealthCheck(
                    name="backend_connection",
                    status="healthy",
                    message=f"{self.config.backend_type} backend is reachable",
                    duration_ms=duration_ms,
                    metadata={"backend_type": self.config.backend_type},
                )
            else:
                return HealthCheck(
                    name="backend_connection",
                    status="unhealthy",
                    message=f"{self.config.backend_type} backend is not reachable",
                    duration_ms=duration_ms,
                    metadata={"backend_type": self.config.backend_type},
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="backend_connection",
                status="unhealthy",
                message=f"Backend connection failed: {str(e)}",
                duration_ms=duration_ms,
                metadata={"backend_type": self.config.backend_type, "error": str(e)},
            )

    def check_configuration(self) -> HealthCheck:
        """Check if configuration is valid."""
        start_time = time.time()

        try:
            # Validate backend type
            if self.config.backend_type not in ["celery", "hatchet", "temporal"]:
                return HealthCheck(
                    name="configuration",
                    status="unhealthy",
                    message=f"Invalid backend type: {self.config.backend_type}",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Get backend-specific configuration and validate required fields
            connection_params = self._get_connection_params()

            if self.config.backend_type == "celery":
                if not connection_params.get("broker_url"):
                    return HealthCheck(
                        name="configuration",
                        status="unhealthy",
                        message="Celery broker_url not configured",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            elif self.config.backend_type == "hatchet":
                if not connection_params.get("token"):
                    return HealthCheck(
                        name="configuration",
                        status="unhealthy",
                        message="Hatchet token not configured",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            elif self.config.backend_type == "temporal":
                required_fields = ["host", "port", "namespace", "task_queue"]
                missing = [
                    field for field in required_fields if not connection_params.get(field)
                ]
                if missing:
                    return HealthCheck(
                        name="configuration",
                        status="unhealthy",
                        message=f"Temporal configuration missing: {', '.join(missing)}",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="configuration",
                status="healthy",
                message="Configuration is valid",
                duration_ms=duration_ms,
                metadata={"backend_type": self.config.backend_type},
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="configuration",
                status="unhealthy",
                message=f"Configuration validation failed: {str(e)}",
                duration_ms=duration_ms,
                metadata={"error": str(e)},
            )

    def check_dependencies(self) -> HealthCheck:
        """Check if required dependencies are installed."""
        start_time = time.time()

        try:
            # Check backend-specific dependencies
            if self.config.backend_type == "celery":
                try:
                    import celery

                    version = celery.__version__
                    metadata = {"celery_version": version}
                except ImportError:
                    return HealthCheck(
                        name="dependencies",
                        status="unhealthy",
                        message="Celery is not installed",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            elif self.config.backend_type == "hatchet":
                try:
                    import hatchet_sdk

                    version = getattr(hatchet_sdk, "__version__", "unknown")
                    metadata = {"hatchet_sdk_version": version}
                except ImportError:
                    return HealthCheck(
                        name="dependencies",
                        status="unhealthy",
                        message="Hatchet SDK is not installed",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            elif self.config.backend_type == "temporal":
                try:
                    import temporalio

                    version = getattr(temporalio, "__version__", "unknown")
                    metadata = {"temporalio_version": version}
                except ImportError:
                    return HealthCheck(
                        name="dependencies",
                        status="unhealthy",
                        message="Temporal SDK is not installed",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="dependencies",
                status="healthy",
                message=f"{self.config.backend_type} dependencies are available",
                duration_ms=duration_ms,
                metadata=metadata,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="dependencies",
                status="unhealthy",
                message=f"Dependency check failed: {str(e)}",
                duration_ms=duration_ms,
                metadata={"error": str(e)},
            )

    def check_all(self) -> HealthStatus:
        """Run all health checks."""
        logger.info(f"Running health checks for backend: {self.config.backend_type}")

        checks = [
            self.check_configuration(),
            self.check_dependencies(),
            self.check_backend_connection(),
        ]

        # Overall health is healthy if all individual checks are healthy
        is_healthy = all(check.is_healthy for check in checks)

        return HealthStatus(is_healthy=is_healthy, checks=checks, timestamp=time.time())

    def _get_connection_params(self) -> dict:
        """Get backend-specific connection parameters."""
        return self.config.get_backend_specific_config()
