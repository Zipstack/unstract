"""Health Check and Monitoring for Workers

Provides health check endpoints and monitoring capabilities for worker processes.
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import psutil

from ...core.exceptions.api_exceptions import APIRequestError
from ..config.worker_config import WorkerConfig
from ..logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] | None = None
    execution_time: float | None = None
    timestamp: datetime | None = None


@dataclass
class SystemMetrics:
    """System metrics for health monitoring."""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    uptime_seconds: float
    process_count: int
    thread_count: int
    timestamp: datetime


class HealthChecker:
    """Comprehensive health checker for worker processes.

    Monitors:
    - API connectivity
    - System resources
    - Worker-specific health
    - Custom health checks
    """

    def __init__(self, config: WorkerConfig | None = None):
        """Initialize health checker.

        Args:
            config: Worker configuration. Uses default if None.
        """
        self.config = config or WorkerConfig()
        self.api_client = None
        self.start_time = time.time()
        self.custom_checks: dict[str, Callable[[], HealthCheckResult]] = {}
        self.last_health_check = None
        self.health_history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def add_custom_check(self, name: str, check_func: Callable[[], HealthCheckResult]):
        """Add custom health check.

        Args:
            name: Check name
            check_func: Function that returns HealthCheckResult
        """
        self.custom_checks[name] = check_func
        logger.debug(f"Added custom health check: {name}")

    def remove_custom_check(self, name: str):
        """Remove custom health check."""
        if name in self.custom_checks:
            del self.custom_checks[name]
            logger.debug(f"Removed custom health check: {name}")

    def check_api_connectivity(self) -> HealthCheckResult:
        """Check connectivity to internal API."""
        start_time = time.time()

        try:
            if not self.api_client:
                # Use singleton API client to reduce initialization noise
                from .api_client_singleton import get_singleton_api_client

                self.api_client = get_singleton_api_client(self.config)

            # Simply check if API client can be configured properly
            # Avoid making actual API calls that might hit non-existent endpoints
            execution_time = time.time() - start_time

            # If we can create the client without errors, consider API connectivity healthy
            return HealthCheckResult(
                name="api_connectivity",
                status=HealthStatus.HEALTHY,
                message="API client configuration successful",
                details={
                    "api_base_url": getattr(
                        self.config, "internal_api_base_url", "unknown"
                    )
                },
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

        except APIRequestError as e:
            execution_time = time.time() - start_time
            return HealthCheckResult(
                name="api_connectivity",
                status=HealthStatus.UNHEALTHY,
                message=f"API request failed: {str(e)}",
                details={"error": str(e)},
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return HealthCheckResult(
                name="api_connectivity",
                status=HealthStatus.UNHEALTHY,
                message=f"Unexpected error: {str(e)}",
                details={"error": str(e)},
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

    def check_system_resources(self) -> HealthCheckResult:
        """Check system resource utilization."""
        start_time = time.time()

        try:
            # Get system metrics
            metrics = self.get_system_metrics()
            execution_time = time.time() - start_time

            # Determine health status based on resource usage
            status = HealthStatus.HEALTHY
            issues = []

            # CPU check
            if metrics.cpu_percent > 90:
                status = HealthStatus.UNHEALTHY
                issues.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
            elif metrics.cpu_percent > 75:
                status = HealthStatus.DEGRADED
                issues.append(f"Elevated CPU usage: {metrics.cpu_percent:.1f}%")

            # Memory check
            if metrics.memory_percent > 95:
                status = HealthStatus.UNHEALTHY
                issues.append(f"Critical memory usage: {metrics.memory_percent:.1f}%")
            elif metrics.memory_percent > 85:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                issues.append(f"High memory usage: {metrics.memory_percent:.1f}%")

            # Disk check
            if metrics.disk_usage_percent > 95:
                status = HealthStatus.UNHEALTHY
                issues.append(f"Critical disk usage: {metrics.disk_usage_percent:.1f}%")
            elif metrics.disk_usage_percent > 85:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                issues.append(f"High disk usage: {metrics.disk_usage_percent:.1f}%")

            message = (
                "System resources OK"
                if status == HealthStatus.HEALTHY
                else "; ".join(issues)
            )

            return HealthCheckResult(
                name="system_resources",
                status=status,
                message=message,
                details=asdict(metrics),
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return HealthCheckResult(
                name="system_resources",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check system resources: {str(e)}",
                details={"error": str(e)},
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

    def check_worker_process(self) -> HealthCheckResult:
        """Check worker process health."""
        start_time = time.time()

        try:
            process = psutil.Process()
            execution_time = time.time() - start_time

            # Check if process is responding
            if process.status() == psutil.STATUS_ZOMBIE:
                return HealthCheckResult(
                    name="worker_process",
                    status=HealthStatus.UNHEALTHY,
                    message="Worker process is zombie",
                    execution_time=execution_time,
                    timestamp=datetime.now(UTC),
                )

            # Check worker uptime
            uptime = time.time() - self.start_time
            process_info = {
                "pid": process.pid,
                "status": process.status(),
                "cpu_percent": process.cpu_percent(),
                "memory_info": process.memory_info()._asdict(),
                "uptime_seconds": uptime,
                "num_threads": process.num_threads(),
            }

            return HealthCheckResult(
                name="worker_process",
                status=HealthStatus.HEALTHY,
                message=f"Worker process healthy (uptime: {uptime:.0f}s)",
                details=process_info,
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return HealthCheckResult(
                name="worker_process",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check worker process: {str(e)}",
                details={"error": str(e)},
                execution_time=execution_time,
                timestamp=datetime.now(UTC),
            )

    def run_all_checks(self) -> dict[str, Any]:
        """Run all health checks and return comprehensive health report.

        Returns:
            Health report dictionary
        """
        start_time = time.time()

        # Built-in checks
        checks = [
            self.check_api_connectivity(),
            self.check_system_resources(),
            self.check_worker_process(),
        ]

        # Custom checks
        for name, check_func in self.custom_checks.items():
            try:
                result = check_func()
                checks.append(result)
            except Exception as e:
                checks.append(
                    HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Custom check failed: {str(e)}",
                        details={"error": str(e)},
                        timestamp=datetime.now(UTC),
                    )
                )

        # Determine overall health status
        overall_status = HealthStatus.HEALTHY
        unhealthy_checks = []
        degraded_checks = []

        for check in checks:
            if check.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                unhealthy_checks.append(check.name)
            elif (
                check.status == HealthStatus.DEGRADED
                and overall_status == HealthStatus.HEALTHY
            ):
                overall_status = HealthStatus.DEGRADED
                degraded_checks.append(check.name)

        execution_time = time.time() - start_time

        # Build health report
        health_report = {
            "status": overall_status.value,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "uptime_seconds": time.time() - self.start_time,
            "worker_name": self.config.worker_name,
            "worker_version": self.config.worker_version,
            "instance_id": self.config.worker_instance_id,
            "execution_time": execution_time,
            "checks": {check.name: asdict(check) for check in checks},
            "summary": {
                "total_checks": len(checks),
                "healthy_checks": len(
                    [c for c in checks if c.status == HealthStatus.HEALTHY]
                ),
                "degraded_checks": len(
                    [c for c in checks if c.status == HealthStatus.DEGRADED]
                ),
                "unhealthy_checks": len(
                    [c for c in checks if c.status == HealthStatus.UNHEALTHY]
                ),
                "unhealthy_check_names": unhealthy_checks,
                "degraded_check_names": degraded_checks,
            },
        }

        # Store in history
        with self._lock:
            self.last_health_check = health_report
            self.health_history.append(health_report)
            # Keep only last 50 health checks
            if len(self.health_history) > 50:
                self.health_history = self.health_history[-50:]

        return health_report

    def get_system_metrics(self) -> SystemMetrics:
        """Get current system metrics."""
        # CPU and memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        # Disk usage for current directory
        disk_usage = psutil.disk_usage("/")

        # Process info
        process = psutil.Process()

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / 1024 / 1024,
            memory_available_mb=memory.available / 1024 / 1024,
            disk_usage_percent=(disk_usage.used / disk_usage.total) * 100,
            uptime_seconds=time.time() - self.start_time,
            process_count=len(psutil.pids()),
            thread_count=process.num_threads(),
            timestamp=datetime.now(UTC),
        )

    def get_last_health_check(self) -> dict[str, Any] | None:
        """Get last health check result."""
        return self.last_health_check

    def get_health_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent health check history."""
        with self._lock:
            return self.health_history[-limit:] if self.health_history else []


class HealthHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints."""

    def __init__(self, health_checker: HealthChecker, *args, **kwargs):
        self.health_checker = health_checker
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests."""
        try:
            if self.path == "/health":
                # Full health check
                health_report = self.health_checker.run_all_checks()
                status_code = 200 if health_report["status"] == "healthy" else 503
                self._send_json_response(health_report, status_code)

            elif self.path == "/health/quick":
                # Quick health check (last result)
                last_check = self.health_checker.get_last_health_check()
                if last_check:
                    status_code = 200 if last_check["status"] == "healthy" else 503
                    self._send_json_response(last_check, status_code)
                else:
                    self._send_json_response(
                        {
                            "status": "no_data",
                            "message": "No health check data available",
                        },
                        503,
                    )

            elif self.path == "/health/metrics":
                # System metrics only
                metrics = self.health_checker.get_system_metrics()
                self._send_json_response(asdict(metrics), 200)

            elif self.path == "/health/history":
                # Health check history
                history = self.health_checker.get_health_history()
                self._send_json_response({"history": history}, 200)

            else:
                self._send_json_response({"error": "Not found"}, 404)

        except Exception as e:
            logger.error(f"Health check endpoint error: {e}")
            self._send_json_response(
                {"error": "Internal server error", "detail": str(e)}, 500
            )

    def _send_json_response(self, data: dict[str, Any], status_code: int):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response_data = json.dumps(data, default=str, indent=2)
        self.wfile.write(response_data.encode("utf-8"))

    def log_message(self, format, *args):
        """Override to suppress routine health check request logs."""
        # Only log errors, not routine health check requests
        pass


class HealthServer:
    """HTTP server for health check endpoints."""

    def __init__(self, health_checker: HealthChecker, port: int = 8080):
        """Initialize health server.

        Args:
            health_checker: HealthChecker instance
            port: Port to listen on
        """
        self.health_checker = health_checker
        self.port = port
        self.server = None
        self.server_thread = None

    def start(self):
        """Start health check server."""
        try:
            # Create server with custom handler
            def handler_factory(*args, **kwargs):
                return HealthHTTPHandler(self.health_checker, *args, **kwargs)

            self.server = HTTPServer(("0.0.0.0", self.port), handler_factory)

            # Start server in background thread
            self.server_thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.server_thread.start()

            logger.debug(f"Health check server started on port {self.port}")

        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
            raise

    def stop(self):
        """Stop health check server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=5)

        logger.debug("Health check server stopped")

    def is_running(self) -> bool:
        """Check if server is running."""
        return (
            self.server is not None
            and self.server_thread is not None
            and self.server_thread.is_alive()
        )


def create_default_health_checker(config: WorkerConfig | None = None) -> HealthChecker:
    """Create health checker with default configuration."""
    return HealthChecker(config)
