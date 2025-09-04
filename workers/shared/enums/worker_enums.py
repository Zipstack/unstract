"""Worker Type and Queue Name Enumerations

This module provides centralized enums for worker types and queue names,
ensuring type safety and preventing hardcoded string errors.

Migration Note: This is part of the worker refactoring to reduce duplication
and improve maintainability. All workers should use these enums instead of
hardcoded strings.
"""

from enum import Enum
from typing import Optional


class WorkerType(str, Enum):
    """Worker types matching actual worker implementations.

    Values match Python module names (underscores, not hyphens).
    Directory names may differ (e.g., api-deployment vs api_deployment).
    """

    API_DEPLOYMENT = "api_deployment"
    GENERAL = "general"
    FILE_PROCESSING = "file_processing"
    CALLBACK = "callback"
    NOTIFICATION = "notification"
    LOG_CONSUMER = "log_consumer"
    SCHEDULER = "scheduler"

    @classmethod
    def from_directory_name(cls, name: str) -> "WorkerType":
        """Convert directory name to enum value.

        Args:
            name: Directory name (e.g., 'api-deployment', 'file_processing')

        Returns:
            Corresponding WorkerType enum

        Example:
            >>> WorkerType.from_directory_name("api-deployment")
            <WorkerType.API_DEPLOYMENT: 'api_deployment'>
        """
        normalized = name.replace("-", "_")
        return cls(normalized)

    def to_import_path(self) -> str:
        """Return standardized Python import path for tasks module.

        Returns:
            Import path string (e.g., 'api-deployment.tasks')

        Note:
            Handles the directory naming convention where some workers
            use hyphens in directory names but underscores in Python modules.
        """
        # Map to actual directory structure
        directory_mapping = {
            "api_deployment": "api-deployment",
            # All others use same name for directory and module
        }
        directory = directory_mapping.get(self.value, self.value)
        return f"{directory}.tasks"

    def to_worker_name(self) -> str:
        """Return human-readable worker name for logging.

        Returns:
            Worker name (e.g., 'api-deployment-worker')
        """
        return f"{self.value.replace('_', '-')}-worker"

    def to_health_port(self) -> int:
        """Return health check port for this worker.

        Checks environment variable first, then falls back to defaults.

        Returns:
            Port number for health server
        """
        import os

        # Check for environment variable first
        env_var = f"{self.name}_HEALTH_PORT"
        if env_port := os.getenv(env_var):
            try:
                return int(env_port)
            except ValueError:
                pass  # Fall back to default

        # Default port mapping
        port_mapping = {
            WorkerType.API_DEPLOYMENT: 8080,
            WorkerType.GENERAL: 8081,
            WorkerType.FILE_PROCESSING: 8082,
            WorkerType.CALLBACK: 8083,
            WorkerType.NOTIFICATION: 8085,
            WorkerType.LOG_CONSUMER: 8086,
            WorkerType.SCHEDULER: 8087,
        }
        return port_mapping.get(self, 8080)


class QueueName(str, Enum):
    """Standard queue names used across the platform.

    These match the actual queue names in RabbitMQ/Redis.
    Using enums prevents typos and makes refactoring easier.
    """

    # Core queues
    API_DEPLOYMENTS = "celery_api_deployments"
    GENERAL = "celery"  # Default Celery queue

    # File processing queues
    FILE_PROCESSING = "file_processing"
    FILE_PROCESSING_API = "api_file_processing"

    # Callback queues
    CALLBACK = "file_processing_callback"
    CALLBACK_API = "api_file_processing_callback"

    # Notification queues
    NOTIFICATION = "notifications"
    NOTIFICATION_WEBHOOK = "notifications_webhook"
    NOTIFICATION_EMAIL = "notifications_email"
    NOTIFICATION_SMS = "notifications_sms"
    NOTIFICATION_PRIORITY = "notifications_priority"

    # Log processing queues
    LOG_CONSUMER = "celery_log_task_queue"
    PERIODIC_LOGS = "celery_periodic_logs"

    # Scheduler queue
    SCHEDULER = "scheduler"

    def to_env_var_name(self) -> str:
        """Convert queue name to environment variable name.

        Returns:
            Environment variable name (e.g., 'CELERY_API_DEPLOYMENTS_QUEUE')
        """
        return f"{self.value.upper().replace('-', '_')}_QUEUE"

    @classmethod
    def from_string(cls, queue_name: str) -> Optional["QueueName"]:
        """Safe conversion from string to QueueName enum.

        Args:
            queue_name: Queue name string

        Returns:
            QueueName enum or None if not found
        """
        for queue in cls:
            if queue.value == queue_name:
                return queue
        return None


class WorkerStatus(str, Enum):
    """Worker migration status for tracking."""

    NOT_MIGRATED = "not_migrated"
    IN_PROGRESS = "in_progress"
    MIGRATED = "migrated"
    VALIDATED = "validated"
