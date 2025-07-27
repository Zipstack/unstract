"""Prometheus Metrics Collection for Lightweight Workers

Provides comprehensive metrics collection for monitoring worker performance,
task execution, and system health.
"""

import logging
import time
from typing import Any

import psutil
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

logger = logging.getLogger(__name__)


class WorkerMetrics:
    """Prometheus metrics collector for lightweight Celery workers."""

    def __init__(self, worker_type: str, registry: CollectorRegistry | None = None):
        """Initialize metrics collector.

        Args:
            worker_type: Type of worker (api_deployment, general, etc.)
            registry: Prometheus registry to use
        """
        self.worker_type = worker_type
        self.registry = registry or CollectorRegistry()
        self.start_time = time.time()

        # Initialize metrics
        self._init_metrics()

        logger.info(f"Initialized Prometheus metrics for {worker_type} worker")

    def _init_metrics(self):
        """Initialize all Prometheus metrics."""
        # Worker information
        self.worker_info = Info(
            "unstract_worker_info", "Information about the worker", registry=self.registry
        )
        self.worker_info.info(
            {
                "worker_type": self.worker_type,
                "version": "1.0.0",
                "python_version": "3.12",
            }
        )

        # Task execution metrics
        self.tasks_total = Counter(
            "unstract_worker_tasks_total",
            "Total number of tasks processed",
            ["worker_type", "task_name", "status"],
            registry=self.registry,
        )

        self.task_duration = Histogram(
            "unstract_worker_task_duration_seconds",
            "Task execution duration in seconds",
            ["worker_type", "task_name"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
            registry=self.registry,
        )

        self.active_tasks = Gauge(
            "unstract_worker_active_tasks",
            "Number of currently active tasks",
            ["worker_type"],
            registry=self.registry,
        )

        # API call metrics
        self.api_calls_total = Counter(
            "unstract_worker_api_calls_total",
            "Total number of internal API calls",
            ["worker_type", "endpoint", "method", "status_code"],
            registry=self.registry,
        )

        self.api_call_duration = Histogram(
            "unstract_worker_api_call_duration_seconds",
            "Internal API call duration in seconds",
            ["worker_type", "endpoint", "method"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry,
        )

        # Error metrics
        self.errors_total = Counter(
            "unstract_worker_errors_total",
            "Total number of errors encountered",
            ["worker_type", "error_type"],
            registry=self.registry,
        )

        self.retries_total = Counter(
            "unstract_worker_retries_total",
            "Total number of task retries",
            ["worker_type", "task_name"],
            registry=self.registry,
        )

        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            "unstract_worker_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half-open)",
            ["worker_type", "circuit_name"],
            registry=self.registry,
        )

        self.circuit_breaker_failures = Counter(
            "unstract_worker_circuit_breaker_failures_total",
            "Total number of circuit breaker failures",
            ["worker_type", "circuit_name"],
            registry=self.registry,
        )

        # System metrics
        self.system_cpu_usage = Gauge(
            "unstract_worker_cpu_usage_percent",
            "CPU usage percentage",
            ["worker_type"],
            registry=self.registry,
        )

        self.system_memory_usage = Gauge(
            "unstract_worker_memory_usage_bytes",
            "Memory usage in bytes",
            ["worker_type"],
            registry=self.registry,
        )

        self.system_memory_percent = Gauge(
            "unstract_worker_memory_usage_percent",
            "Memory usage percentage",
            ["worker_type"],
            registry=self.registry,
        )

        # Worker uptime
        self.worker_uptime = Gauge(
            "unstract_worker_uptime_seconds",
            "Worker uptime in seconds",
            ["worker_type"],
            registry=self.registry,
        )

        # Health check metrics
        self.health_check_status = Gauge(
            "unstract_worker_health_check_status",
            "Health check status (1=healthy, 0=unhealthy)",
            ["worker_type", "check_name"],
            registry=self.registry,
        )

        self.health_check_duration = Histogram(
            "unstract_worker_health_check_duration_seconds",
            "Health check duration in seconds",
            ["worker_type", "check_name"],
            registry=self.registry,
        )

    def record_task_start(self, task_name: str):
        """Record task start."""
        self.active_tasks.labels(worker_type=self.worker_type).inc()
        logger.debug(f"Task started: {task_name}")

    def record_task_completion(
        self, task_name: str, duration: float, status: str = "success"
    ):
        """Record task completion."""
        self.tasks_total.labels(
            worker_type=self.worker_type, task_name=task_name, status=status
        ).inc()

        self.task_duration.labels(
            worker_type=self.worker_type, task_name=task_name
        ).observe(duration)

        self.active_tasks.labels(worker_type=self.worker_type).dec()

        logger.debug(
            f"Task completed: {task_name}, duration: {duration:.2f}s, status: {status}"
        )

    def record_api_call(
        self, endpoint: str, method: str, duration: float, status_code: int
    ):
        """Record internal API call."""
        self.api_calls_total.labels(
            worker_type=self.worker_type,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
        ).inc()

        self.api_call_duration.labels(
            worker_type=self.worker_type, endpoint=endpoint, method=method
        ).observe(duration)

    def record_error(self, error_type: str):
        """Record error occurrence."""
        self.errors_total.labels(
            worker_type=self.worker_type, error_type=error_type
        ).inc()

    def record_retry(self, task_name: str):
        """Record task retry."""
        self.retries_total.labels(worker_type=self.worker_type, task_name=task_name).inc()

    def update_circuit_breaker_state(self, circuit_name: str, state: int):
        """Update circuit breaker state (0=closed, 1=open, 2=half-open)."""
        self.circuit_breaker_state.labels(
            worker_type=self.worker_type, circuit_name=circuit_name
        ).set(state)

    def record_circuit_breaker_failure(self, circuit_name: str):
        """Record circuit breaker failure."""
        self.circuit_breaker_failures.labels(
            worker_type=self.worker_type, circuit_name=circuit_name
        ).inc()

    def update_system_metrics(self):
        """Update system resource metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage.labels(worker_type=self.worker_type).set(cpu_percent)

            # Memory usage
            memory = psutil.virtual_memory()
            process = psutil.Process()
            process_memory = process.memory_info()

            self.system_memory_usage.labels(worker_type=self.worker_type).set(
                process_memory.rss
            )
            self.system_memory_percent.labels(worker_type=self.worker_type).set(
                (process_memory.rss / memory.total) * 100
            )

            # Worker uptime
            uptime = time.time() - self.start_time
            self.worker_uptime.labels(worker_type=self.worker_type).set(uptime)

        except Exception as e:
            logger.error(f"Failed to update system metrics: {e}")

    def record_health_check(self, check_name: str, status: bool, duration: float):
        """Record health check result."""
        self.health_check_status.labels(
            worker_type=self.worker_type, check_name=check_name
        ).set(1 if status else 0)

        self.health_check_duration.labels(
            worker_type=self.worker_type, check_name=check_name
        ).observe(duration)

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        return generate_latest(self.registry).decode("utf-8")

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get metrics summary for JSON responses."""
        try:
            # Get current values
            process = psutil.Process()
            memory_info = process.memory_info()

            return {
                "worker_type": self.worker_type,
                "uptime_seconds": time.time() - self.start_time,
                "system": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_bytes": memory_info.rss,
                    "memory_percent": (memory_info.rss / psutil.virtual_memory().total)
                    * 100,
                },
                "tasks": {
                    "active": self._get_gauge_value(
                        self.active_tasks, {"worker_type": self.worker_type}
                    )
                },
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {"error": str(e)}

    def _get_gauge_value(self, gauge: Gauge, labels: dict[str, str]) -> float:
        """Helper to get current gauge value."""
        try:
            # This is a simplified approach - in practice you might want
            # to use the registry to get the actual current value
            return 0.0
        except Exception:
            return 0.0


# Global metrics instance - will be initialized by worker
metrics: WorkerMetrics | None = None


def init_metrics(worker_type: str) -> WorkerMetrics:
    """Initialize global metrics instance."""
    global metrics
    metrics = WorkerMetrics(worker_type)
    return metrics


def get_metrics() -> WorkerMetrics | None:
    """Get global metrics instance."""
    return metrics
