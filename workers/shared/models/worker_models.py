"""Worker Configuration Data Models

This module provides dataclasses for worker configuration, task routing,
and queue management. These replace dictionary-based configurations with
type-safe, validated dataclasses.

Migration Note: Part of the worker refactoring initiative to improve
code maintainability and reduce duplication across workers.
"""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shared.enums.worker_enums import QueueName, WorkerType

# Global cache for command-line Celery settings
_CMDLINE_CELERY_SETTINGS: dict[str, str] | None = None


def _parse_celery_cmdline_args() -> dict[str, str]:
    """Parse Celery settings from command-line arguments.

    Extracts --setting=value pairs from sys.argv and converts them to
    setting names compatible with get_celery_setting().

    Returns:
        Dictionary mapping setting names to values from command-line

    Examples:
        --pool=prefork -> {"POOL_TYPE": "prefork"}
        --concurrency=20 -> {"CONCURRENCY": "20"}
        --loglevel=INFO -> {"LOG_LEVEL": "INFO"}
    """
    settings = {}

    # Convert common Celery argument names to setting names
    setting_mapping = {
        "pool": "POOL_TYPE",
        "concurrency": "CONCURRENCY",
        "loglevel": "LOG_LEVEL",
        "prefetch-multiplier": "PREFETCH_MULTIPLIER",
        "max-tasks-per-child": "MAX_TASKS_PER_CHILD",
        "time-limit": "TASK_TIME_LIMIT",
        "soft-time-limit": "TASK_SOFT_TIME_LIMIT",
        "without-gossip": "WORKER_GOSSIP",
        "without-mingle": "WORKER_MINGLE",
        "without-heartbeat": "WORKER_HEARTBEAT",
        # Add more mappings as needed
    }

    for arg in sys.argv:
        if arg.startswith("--"):
            if "=" in arg:
                # Handle --setting=value
                setting_arg, value = arg[2:].split("=", 1)
                setting_name = setting_mapping.get(
                    setting_arg, setting_arg.upper().replace("-", "_")
                )
                settings[setting_name] = value
            elif arg[2:] in setting_mapping:
                # Handle --without-* flags (they don't have values)
                setting_arg = arg[2:]
                if setting_arg.startswith("without-"):
                    setting_name = setting_mapping[setting_arg]
                    settings[setting_name] = "false"

    return settings


def _get_cmdline_celery_settings() -> dict[str, str]:
    """Get cached command-line Celery settings, parsing if needed."""
    global _CMDLINE_CELERY_SETTINGS
    if _CMDLINE_CELERY_SETTINGS is None:
        _CMDLINE_CELERY_SETTINGS = _parse_celery_cmdline_args()
    return _CMDLINE_CELERY_SETTINGS


def get_celery_setting(
    setting_name: str, worker_type: WorkerType, default: Any, setting_type: type = str
) -> Any:
    """Get Celery configuration setting with 4-tier hierarchy resolution.

    Resolution order (most specific wins):
    1. Command-line arguments (--pool=prefork, --concurrency=20, etc.) - HIGHEST
    2. {WORKER_TYPE}_{SETTING_NAME} (worker-specific env override)
    3. CELERY_{SETTING_NAME} (global env override)
    4. default (Celery standard/provided default) - LOWEST

    Args:
        setting_name: The setting name (e.g., "TASK_TIME_LIMIT")
        worker_type: Worker type for worker-specific overrides
        default: Default value if no settings are found
        setting_type: Type to convert the setting value to (str, int, bool, etc.)

    Returns:
        Resolved configuration value with proper type conversion

    Examples:
        # Check --pool=, then FILE_PROCESSING_POOL_TYPE, then CELERY_POOL_TYPE, then default
        pool = get_celery_setting("POOL_TYPE", WorkerType.FILE_PROCESSING, "prefork", str)

        # Check --concurrency=, then CALLBACK_CONCURRENCY, then CELERY_CONCURRENCY, then default
        concurrency = get_celery_setting("CONCURRENCY", WorkerType.CALLBACK, 4, int)
    """
    # 1. Check command-line arguments first (highest priority)
    cmdline_settings = _get_cmdline_celery_settings()
    if setting_name in cmdline_settings:
        cmdline_value = cmdline_settings[setting_name]
        converted_value = _convert_setting_value(cmdline_value, setting_type)
        if converted_value is not None:
            return converted_value

    # 2. Check worker-specific setting (high priority)
    worker_specific_key = f"{worker_type.name}_{setting_name}"
    worker_value = os.getenv(worker_specific_key)
    if worker_value is not None:
        converted_value = _convert_setting_value(worker_value, setting_type)
        if converted_value is not None:
            return converted_value

    # 3. Check global Celery setting (medium priority)
    global_key = f"CELERY_{setting_name}"
    global_value = os.getenv(global_key)
    if global_value is not None:
        converted_value = _convert_setting_value(global_value, setting_type)
        if converted_value is not None:
            return converted_value

    # 4. Use provided default (lowest priority)
    return default


def _convert_setting_value(value: str, setting_type: type) -> Any:
    """Convert string environment variable to appropriate type.

    Args:
        value: String value from environment variable
        setting_type: Target type for conversion

    Returns:
        Converted value or None if empty/invalid

    Raises:
        ValueError: If conversion fails for non-empty values
    """
    # Handle empty or whitespace-only values
    if not value or not value.strip():
        return None

    # Clean the value
    value = value.strip()

    if setting_type == bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif setting_type == int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to integer")
    elif setting_type == float:
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to float")
    elif setting_type == tuple:
        # For autoscale tuples like "4,1" -> (4, 1)
        try:
            parts = [x.strip() for x in value.split(",") if x.strip()]
            if not parts:
                return None
            return tuple(int(x) for x in parts)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to tuple of integers")
    else:
        # Default to string (already cleaned)
        return value


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
    task_reject_on_worker_lost: bool = False

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

    # Task annotations (for task-specific settings like retry policies)
    task_annotations: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _get_worker_specific_timeout_defaults(self) -> tuple[int, int]:
        """Get worker-specific timeout defaults.

        Returns static defaults based on worker type that will be overridden
        by environment variables like FILE_PROCESSING_TASK_TIME_LIMIT.

        Returns:
            tuple[int, int]: (hard_timeout, soft_timeout) in seconds
        """
        # Worker-specific defaults (will be overridden by env vars)
        if self.worker_type == WorkerType.FILE_PROCESSING:
            return 7200, 6300  # 2 hours / 1h 45m (large files)
        elif self.worker_type == WorkerType.CALLBACK:
            return 3600, 3300  # 1 hour / 55 min
        else:
            # Conservative defaults for other workers
            return 3600, 3300  # 1 hour / 55 min

    def to_celery_dict(self, broker_url: str, result_backend: str) -> dict[str, Any]:
        """Generate complete Celery configuration dictionary with hierarchical resolution.

        Uses 3-tier hierarchy: Worker-specific > Global > Default
        Includes feature-specific logic for chord workers, pool types, etc.

        Args:
            broker_url: Celery broker URL
            result_backend: Celery result backend URL

        Returns:
            Dictionary suitable for app.conf.update()
        """
        config = {
            # Connection settings
            "broker_url": broker_url,
            "result_backend": result_backend,
            # Task routing
            "task_routes": self.task_routing.to_celery_config(),
            # Serialization (configurable from env)
            "task_serializer": get_celery_setting(
                "TASK_SERIALIZER", self.worker_type, "json"
            ),
            "accept_content": ["json"],  # Could make this configurable too
            "result_serializer": get_celery_setting(
                "RESULT_SERIALIZER", self.worker_type, "json"
            ),
            "timezone": get_celery_setting("TIMEZONE", self.worker_type, "UTC"),
            "enable_utc": get_celery_setting("ENABLE_UTC", self.worker_type, True, bool),
            # Worker settings (all configurable from env with Celery defaults)
            "worker_prefetch_multiplier": get_celery_setting(
                "PREFETCH_MULTIPLIER",
                self.worker_type,
                1,
                int,  # Celery default is 4, but 1 is safer
            ),
            "task_acks_late": get_celery_setting(
                "TASK_ACKS_LATE", self.worker_type, True, bool
            ),
            "worker_max_tasks_per_child": get_celery_setting(
                "MAX_TASKS_PER_CHILD",
                self.worker_type,
                1000,
                int,  # Prevent memory leaks
            ),
            "task_reject_on_worker_lost": get_celery_setting(
                "TASK_REJECT_ON_WORKER_LOST",
                self.worker_type,
                self.task_reject_on_worker_lost,
                bool,
            ),
            "task_acks_on_failure_or_timeout": get_celery_setting(
                "TASK_ACKS_ON_FAILURE_OR_TIMEOUT", self.worker_type, True, bool
            ),
            "worker_disable_rate_limits": get_celery_setting(
                "DISABLE_RATE_LIMITS", self.worker_type, False, bool
            ),
            # Timeouts (configurable from env with worker-specific defaults)
            # Falls back to task-specific timeout env vars (FILE_PROCESSING_TIMEOUT, etc.)
            "task_time_limit": get_celery_setting(
                "TASK_TIME_LIMIT",
                self.worker_type,
                self._get_worker_specific_timeout_defaults()[0],
                int,
            ),
            "task_soft_time_limit": get_celery_setting(
                "TASK_SOFT_TIME_LIMIT",
                self.worker_type,
                self._get_worker_specific_timeout_defaults()[1],
                int,
            ),
            # Retry configuration (configurable from env)
            "task_default_retry_delay": get_celery_setting(
                "TASK_DEFAULT_RETRY_DELAY",
                self.worker_type,
                60,
                int,  # 1 minute default
            ),
            "task_max_retries": get_celery_setting(
                "TASK_MAX_RETRIES", self.worker_type, 3, int
            ),
            # Stability (configurable from env)
            "worker_pool_restarts": get_celery_setting(
                "POOL_RESTARTS", self.worker_type, True, bool
            ),
            "broker_connection_retry_on_startup": get_celery_setting(
                "BROKER_CONNECTION_RETRY_ON_STARTUP", self.worker_type, True, bool
            ),
            # Monitoring (configurable from env)
            "worker_send_task_events": get_celery_setting(
                "SEND_TASK_EVENTS", self.worker_type, True, bool
            ),
            "task_send_sent_event": get_celery_setting(
                "TASK_SEND_SENT_EVENT", self.worker_type, True, bool
            ),
            # Task imports
            "imports": [self.worker_type.to_import_path()],
        }

        # Feature-specific configurations
        self._add_pool_configuration(config)
        self._add_worker_scaling_configuration(config)
        self._add_chord_configuration(config)

        # Add task annotations if present
        if self.task_annotations:
            config["task_annotations"] = self.task_annotations

        return config

    def _add_pool_configuration(self, config: dict[str, Any]) -> None:
        """Add worker pool configuration based on worker type and environment."""
        # All workers use prefork as default (consistent with command-line args)
        default_pool = "prefork"

        pool_type = get_celery_setting("POOL_TYPE", self.worker_type, default_pool)
        if pool_type == "threads":
            config["worker_pool"] = "threads"
        # prefork is Celery's default, so no need to set it explicitly

    def _add_worker_scaling_configuration(self, config: dict[str, Any]) -> None:
        """Add concurrency and autoscaling configuration."""
        # Concurrency (fixed number of workers)
        concurrency = get_celery_setting("CONCURRENCY", self.worker_type, None, int)
        if concurrency is not None:
            config["worker_concurrency"] = concurrency

        # Autoscaling (dynamic worker count)
        autoscale = get_celery_setting("AUTOSCALE", self.worker_type, None, tuple)
        if autoscale is not None:
            config["worker_autoscaler"] = "celery.worker.autoscale.Autoscaler"
            config["worker_autoscale_max"] = autoscale[0]
            config["worker_autoscale_min"] = autoscale[1]

    def _add_chord_configuration(self, config: dict[str, Any]) -> None:
        """Add chord-specific configuration only for workers that use chords."""
        # Only workers that actually use chords need chord configuration
        chord_workers = {
            WorkerType.CALLBACK,
            WorkerType.GENERAL,
            WorkerType.API_DEPLOYMENT,
        }

        if self.worker_type in chord_workers:
            # Chord retry interval - defaults to Celery standard (1 second)
            config["result_chord_retry_interval"] = get_celery_setting(
                "RESULT_CHORD_RETRY_INTERVAL", self.worker_type, 1, int
            )

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
