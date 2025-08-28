"""Worker Configuration Data Models

This module provides dataclasses for worker configuration, task routing,
and queue management. These replace dictionary-based configurations with
type-safe, validated dataclasses.

Migration Note: Part of the worker refactoring initiative to improve
code maintainability and reduce duplication across workers.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shared.enums.worker_enums import QueueName, WorkerType


@dataclass
class TaskRoute:
    """Single task routing configuration.

    Defines how a task pattern maps to a specific queue.
    """

    pattern: str  # Task name or pattern (e.g., "process_file_batch" or "worker.*")
    queue: QueueName  # Target queue enum

    def to_dict(self) -> dict[str, str]:
        """Convert to Celery-compatible routing dict."""
        return {"queue": self.queue.value}


@dataclass
class WorkerQueueConfig:
    """Queue configuration for a worker.

    Defines primary and additional queues that a worker consumes from.
    """

    primary_queue: QueueName
    additional_queues: list[QueueName] = field(default_factory=list)

    def all_queues(self) -> set[str]:
        """Get all queue names as strings.

        Returns:
            Set of queue name strings
        """
        queues = {self.primary_queue.value}
        queues.update(q.value for q in self.additional_queues)
        return queues

    def to_queue_list(self) -> list[str]:
        """Get ordered list of queue names.

        Returns:
            List with primary queue first, then additional queues
        """
        result = [self.primary_queue.value]
        result.extend(q.value for q in self.additional_queues)
        return result

    def to_cli_queues(self) -> str:
        """Format queues for Celery CLI --queues parameter.

        Returns:
            Comma-separated queue names
        """
        return ",".join(self.to_queue_list())


@dataclass
class WorkerTaskRouting:
    """Complete task routing configuration for a worker.

    Encapsulates all task routes for a specific worker type.
    """

    worker_type: WorkerType
    routes: list[TaskRoute]

    def to_celery_config(self) -> dict[str, dict[str, str]]:
        """Convert to Celery task_routes configuration.

        Returns:
            Dictionary compatible with Celery's task_routes setting
        """
        return {route.pattern: route.to_dict() for route in self.routes}

    def add_route(self, pattern: str, queue: QueueName) -> None:
        """Add a new task route.

        Args:
            pattern: Task name or pattern
            queue: Target queue
        """
        self.routes.append(TaskRoute(pattern, queue))

    def get_queue_for_task(self, task_name: str) -> QueueName | None:
        """Find queue for a specific task name.

        Args:
            task_name: Full task name

        Returns:
            Queue name if route found, None otherwise
        """
        # Check exact matches first
        for route in self.routes:
            if route.pattern == task_name:
                return route.queue

        # Check wildcard patterns
        for route in self.routes:
            if route.pattern.endswith("*"):
                prefix = route.pattern[:-1]
                if task_name.startswith(prefix):
                    return route.queue

        return None


@dataclass
class WorkerHealthConfig:
    """Health check configuration for a worker."""

    port: int
    custom_checks: list[Callable] = field(default_factory=list)
    check_interval: int = 30  # seconds

    def add_check(self, name: str, check_func: Callable) -> None:
        """Add a custom health check function."""
        self.custom_checks.append((name, check_func))


@dataclass
class WorkerCeleryConfig:
    """Complete Celery configuration for a worker.

    Combines all configuration aspects into a single dataclass.
    """

    worker_type: WorkerType
    queue_config: WorkerQueueConfig
    task_routing: WorkerTaskRouting
    health_config: WorkerHealthConfig | None = None

    # Celery worker settings
    prefetch_multiplier: int = 1
    max_tasks_per_child: int = 1000
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True

    # Timeouts
    task_time_limit: int = 7200  # 2 hours
    task_soft_time_limit: int = 6300  # 1h 45m

    # Retry settings
    task_default_retry_delay: int = 60
    task_max_retries: int = 3

    # Pool settings
    pool_type: str = "prefork"  # or "threads", "solo", "eventlet"
    concurrency: int | None = None  # None means auto
    autoscale: tuple[int, int] | None = None  # (max, min) workers

    def to_celery_dict(self, broker_url: str, result_backend: str) -> dict[str, Any]:
        """Generate complete Celery configuration dictionary.

        All settings check environment variables first, then use defaults.
        Environment variables follow pattern: CELERY_<SETTING_NAME> or
        <WORKER_TYPE>_<SETTING_NAME> for worker-specific overrides.

        Args:
            broker_url: Celery broker URL
            result_backend: Celery result backend URL

        Returns:
            Dictionary suitable for app.conf.update()
        """
        import os

        # Helper to get env var with fallback
        def get_env_config(key: str, default: Any, cast_type=None) -> Any:
            """Get config from environment with worker-specific and global fallbacks."""
            # Try worker-specific env var first
            worker_env_key = f"{self.worker_type.name}_{key}"
            value = os.getenv(worker_env_key)

            # Try global Celery env var
            if value is None:
                celery_env_key = f"CELERY_{key}"
                value = os.getenv(celery_env_key)

            # Use default if not found
            if value is None:
                return default

            # Cast to appropriate type
            if cast_type == bool:
                return value.lower() in ("true", "1", "yes")
            elif cast_type == int:
                try:
                    return int(value)
                except ValueError:
                    return default
            return value

        config = {
            # Connection settings
            "broker_url": broker_url,
            "result_backend": result_backend,
            # Task routing
            "task_routes": self.task_routing.to_celery_config(),
            # Serialization (configurable from env)
            "task_serializer": get_env_config("TASK_SERIALIZER", "json"),
            "accept_content": ["json"],  # Could make this configurable too
            "result_serializer": get_env_config("RESULT_SERIALIZER", "json"),
            "timezone": get_env_config("TIMEZONE", "UTC"),
            "enable_utc": get_env_config("ENABLE_UTC", True, bool),
            # Worker settings (all configurable from env)
            "worker_prefetch_multiplier": get_env_config(
                "WORKER_PREFETCH_MULTIPLIER", self.prefetch_multiplier, int
            ),
            "task_acks_late": get_env_config("TASK_ACKS_LATE", self.task_acks_late, bool),
            "worker_max_tasks_per_child": get_env_config(
                "WORKER_MAX_TASKS_PER_CHILD", self.max_tasks_per_child, int
            ),
            "task_reject_on_worker_lost": get_env_config(
                "TASK_REJECT_ON_WORKER_LOST", self.task_reject_on_worker_lost, bool
            ),
            "task_acks_on_failure_or_timeout": get_env_config(
                "TASK_ACKS_ON_FAILURE_OR_TIMEOUT", True, bool
            ),
            "worker_disable_rate_limits": get_env_config(
                "WORKER_DISABLE_RATE_LIMITS", False, bool
            ),
            # Timeouts (configurable from env)
            "task_time_limit": get_env_config(
                "TASK_TIME_LIMIT", self.task_time_limit, int
            ),
            "task_soft_time_limit": get_env_config(
                "TASK_SOFT_TIME_LIMIT", self.task_soft_time_limit, int
            ),
            # Retry configuration (configurable from env)
            "task_default_retry_delay": get_env_config(
                "TASK_DEFAULT_RETRY_DELAY", self.task_default_retry_delay, int
            ),
            "task_max_retries": get_env_config(
                "TASK_MAX_RETRIES", self.task_max_retries, int
            ),
            # Stability (configurable from env)
            "worker_pool_restarts": get_env_config("WORKER_POOL_RESTARTS", True, bool),
            "broker_connection_retry_on_startup": get_env_config(
                "BROKER_CONNECTION_RETRY_ON_STARTUP", True, bool
            ),
            # Monitoring (configurable from env)
            "worker_send_task_events": get_env_config(
                "WORKER_SEND_TASK_EVENTS", True, bool
            ),
            "task_send_sent_event": get_env_config("TASK_SEND_SENT_EVENT", True, bool),
            # Task imports
            "imports": [self.worker_type.to_import_path()],
        }

        # Add pool-specific settings if configured (also check env)
        pool_type = os.getenv(f"{self.worker_type.name}_POOL_TYPE", self.pool_type)
        if pool_type == "threads":
            config["worker_pool"] = "threads"

        # Check for concurrency override from env
        concurrency_env = os.getenv(f"{self.worker_type.name}_CONCURRENCY")
        if concurrency_env:
            try:
                config["worker_concurrency"] = int(concurrency_env)
            except ValueError:
                pass
        elif self.concurrency is not None:
            config["worker_concurrency"] = self.concurrency

        # Check for autoscale override from env
        autoscale_env = os.getenv(f"{self.worker_type.name}_AUTOSCALE")
        if autoscale_env:
            try:
                max_w, min_w = autoscale_env.split(",")
                config["worker_autoscaler"] = "celery.worker.autoscale.Autoscaler"
                config["worker_autoscale_max"] = int(max_w)
                config["worker_autoscale_min"] = int(min_w)
            except (ValueError, AttributeError):
                pass
        elif self.autoscale is not None:
            config["worker_autoscaler"] = "celery.worker.autoscale.Autoscaler"
            config["worker_autoscale_max"] = self.autoscale[0]
            config["worker_autoscale_min"] = self.autoscale[1]

        return config

    def to_cli_args(self) -> list[str]:
        """Generate Celery worker CLI arguments.

        Returns:
            List of CLI arguments for celery worker command
        """
        args = [
            "worker",
            "--loglevel=info",
            f"--queues={self.queue_config.to_cli_queues()}",
        ]

        if self.pool_type == "threads":
            args.append("--pool=threads")

        if self.concurrency:
            args.append(f"--concurrency={self.concurrency}")

        if self.autoscale:
            args.append(f"--autoscale={self.autoscale[0]},{self.autoscale[1]}")

        return args


@dataclass
class WorkerMigrationStatus:
    """Track migration status of a worker."""

    worker_type: WorkerType
    migrated: bool = False
    validated: bool = False
    notes: str = ""

    def __post_init__(self):
        """Mark in worker file with __migrated__ flag."""
        self.marker = f"__migrated__ = {self.migrated}"
