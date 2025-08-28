"""Worker Registry - Central Configuration Hub

This module provides a centralized registry for all worker configurations,
including queue configs, task routing, health checks, and logging settings.

Migration Note: This replaces scattered configuration across multiple worker.py
files with a single source of truth, making it easier to maintain and update
worker configurations.
"""

import logging
from collections.abc import Callable

from shared.enums.worker_enums import QueueName, WorkerType
from shared.models.worker_models import (
    TaskRoute,
    WorkerCeleryConfig,
    WorkerHealthConfig,
    WorkerQueueConfig,
    WorkerTaskRouting,
)

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """Central registry for all worker configurations.

    This class acts as the single source of truth for:
    - Queue configurations
    - Task routing rules
    - Health check functions
    - Logging configurations
    - Worker-specific settings
    """

    # Queue configurations for each worker type
    _QUEUE_CONFIGS: dict[WorkerType, WorkerQueueConfig] = {
        WorkerType.API_DEPLOYMENT: WorkerQueueConfig(
            primary_queue=QueueName.API_DEPLOYMENTS
        ),
        WorkerType.GENERAL: WorkerQueueConfig(primary_queue=QueueName.GENERAL),
        WorkerType.FILE_PROCESSING: WorkerQueueConfig(
            primary_queue=QueueName.FILE_PROCESSING,
            additional_queues=[QueueName.FILE_PROCESSING_API],
        ),
        WorkerType.CALLBACK: WorkerQueueConfig(
            primary_queue=QueueName.CALLBACK, additional_queues=[QueueName.CALLBACK_API]
        ),
        WorkerType.NOTIFICATION: WorkerQueueConfig(
            primary_queue=QueueName.NOTIFICATION,
            additional_queues=[
                QueueName.NOTIFICATION_WEBHOOK,
                QueueName.NOTIFICATION_EMAIL,
                QueueName.NOTIFICATION_SMS,
                QueueName.NOTIFICATION_PRIORITY,
            ],
        ),
        WorkerType.LOG_CONSUMER: WorkerQueueConfig(
            primary_queue=QueueName.LOG_CONSUMER,
            additional_queues=[QueueName.PERIODIC_LOGS],
        ),
        WorkerType.SCHEDULER: WorkerQueueConfig(primary_queue=QueueName.SCHEDULER),
    }

    # Task routing rules for each worker type
    _TASK_ROUTES: dict[WorkerType, WorkerTaskRouting] = {
        WorkerType.API_DEPLOYMENT: WorkerTaskRouting(
            worker_type=WorkerType.API_DEPLOYMENT,
            routes=[
                TaskRoute("async_execute_bin_api", QueueName.API_DEPLOYMENTS),
                TaskRoute("api_deployment_cleanup", QueueName.API_DEPLOYMENTS),
                TaskRoute("api_deployment_status_check", QueueName.API_DEPLOYMENTS),
                TaskRoute("api_deployment_worker.*", QueueName.API_DEPLOYMENTS),
            ],
        ),
        WorkerType.GENERAL: WorkerTaskRouting(
            worker_type=WorkerType.GENERAL,
            routes=[
                TaskRoute("async_execute_bin", QueueName.GENERAL),
                TaskRoute("async_execute_bin_general", QueueName.GENERAL),
                TaskRoute("general_worker.*", QueueName.GENERAL),
            ],
        ),
        WorkerType.FILE_PROCESSING: WorkerTaskRouting(
            worker_type=WorkerType.FILE_PROCESSING,
            routes=[
                TaskRoute("process_file_batch", QueueName.FILE_PROCESSING),
                TaskRoute("process_file_batch_api", QueueName.FILE_PROCESSING_API),
            ],
        ),
        WorkerType.CALLBACK: WorkerTaskRouting(
            worker_type=WorkerType.CALLBACK,
            routes=[
                TaskRoute("process_batch_callback", QueueName.CALLBACK),
                TaskRoute("process_batch_callback_api", QueueName.CALLBACK_API),
                TaskRoute("finalize_execution_callback", QueueName.CALLBACK),
            ],
        ),
        WorkerType.NOTIFICATION: WorkerTaskRouting(
            worker_type=WorkerType.NOTIFICATION,
            routes=[
                TaskRoute("process_notification", QueueName.NOTIFICATION),
                TaskRoute("send_webhook_notification", QueueName.NOTIFICATION),
                TaskRoute("send_batch_notifications", QueueName.NOTIFICATION),
                TaskRoute("notification_health_check", QueueName.NOTIFICATION),
                TaskRoute("notification.tasks.*", QueueName.NOTIFICATION),
                TaskRoute("send_email_notification", QueueName.NOTIFICATION_EMAIL),
                TaskRoute("send_sms_notification", QueueName.NOTIFICATION_SMS),
                TaskRoute("priority_notification", QueueName.NOTIFICATION_PRIORITY),
            ],
        ),
        WorkerType.LOG_CONSUMER: WorkerTaskRouting(
            worker_type=WorkerType.LOG_CONSUMER,
            routes=[
                TaskRoute("logs_consumer", QueueName.LOG_CONSUMER),
                TaskRoute("consume_log_history", QueueName.PERIODIC_LOGS),
                TaskRoute("log_consumer.tasks.*", QueueName.LOG_CONSUMER),
                TaskRoute("log_consumer_health_check", QueueName.LOG_CONSUMER),
            ],
        ),
        WorkerType.SCHEDULER: WorkerTaskRouting(
            worker_type=WorkerType.SCHEDULER,
            routes=[
                TaskRoute("execute_pipeline_task", QueueName.SCHEDULER),
                TaskRoute("execute_pipeline_task_v2", QueueName.SCHEDULER),
                TaskRoute("scheduler_health_check", QueueName.SCHEDULER),
                TaskRoute("scheduler.tasks.*", QueueName.SCHEDULER),
            ],
        ),
    }

    # Health check functions registry
    _HEALTH_CHECKS: dict[WorkerType, list[tuple[str, Callable]]] = {}

    # Worker-specific Celery settings
    _WORKER_SETTINGS: dict[WorkerType, dict] = {
        WorkerType.FILE_PROCESSING: {
            "pool_type": "threads",
            "concurrency": 4,
            "max_tasks_per_child": 100,  # Lower due to memory usage
        },
        WorkerType.CALLBACK: {
            "autoscale": (4, 1),
            "prefetch_multiplier": 2,
            "max_tasks_per_child": 2000,
            "task_time_limit": 3600,  # 1 hour
            "task_soft_time_limit": 3300,  # 55 minutes
        },
        WorkerType.NOTIFICATION: {
            "task_time_limit": 30,  # 30 seconds for webhooks
            "task_max_retries": 3,
        },
        WorkerType.LOG_CONSUMER: {
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
        },
    }

    # Logging configurations
    _LOGGING_CONFIGS: dict[WorkerType, dict] = {
        WorkerType.API_DEPLOYMENT: {
            "log_format": "django",
            "log_level": "INFO",
        },
        WorkerType.GENERAL: {
            "log_format": "structured",
            "log_level": "INFO",
        },
        WorkerType.FILE_PROCESSING: {
            "log_format": "django",
            "log_level": "INFO",
        },
        WorkerType.CALLBACK: {
            "log_format": "django",
            "log_level": "INFO",
        },
        WorkerType.NOTIFICATION: {
            "log_format": "structured",
            "log_level": "INFO",
        },
        WorkerType.LOG_CONSUMER: {
            "log_format": "structured",
            "log_level": "INFO",
        },
        WorkerType.SCHEDULER: {
            "log_format": "structured",
            "log_level": "INFO",
        },
    }

    @classmethod
    def get_queue_config(cls, worker_type: WorkerType) -> WorkerQueueConfig:
        """Get queue configuration for a worker type.

        Args:
            worker_type: Type of worker

        Returns:
            Queue configuration

        Raises:
            KeyError: If worker type not registered
        """
        if worker_type not in cls._QUEUE_CONFIGS:
            raise KeyError(f"No queue config registered for {worker_type}")
        return cls._QUEUE_CONFIGS[worker_type]

    @classmethod
    def get_task_routing(cls, worker_type: WorkerType) -> WorkerTaskRouting:
        """Get task routing configuration for a worker type.

        Args:
            worker_type: Type of worker

        Returns:
            Task routing configuration

        Raises:
            KeyError: If worker type not registered
        """
        if worker_type not in cls._TASK_ROUTES:
            raise KeyError(f"No task routing registered for {worker_type}")
        return cls._TASK_ROUTES[worker_type]

    @classmethod
    def register_health_check(
        cls, worker_type: WorkerType, name: str, check_func: Callable
    ) -> None:
        """Register a health check function for a worker type.

        Args:
            worker_type: Type of worker
            name: Name of the health check
            check_func: Health check function
        """
        if worker_type not in cls._HEALTH_CHECKS:
            cls._HEALTH_CHECKS[worker_type] = []

        cls._HEALTH_CHECKS[worker_type].append((name, check_func))
        logger.info(f"Registered health check '{name}' for {worker_type}")

    @classmethod
    def get_health_checks(cls, worker_type: WorkerType) -> list[tuple[str, Callable]]:
        """Get all health check functions for a worker type.

        Args:
            worker_type: Type of worker

        Returns:
            List of (name, function) tuples
        """
        return cls._HEALTH_CHECKS.get(worker_type, [])

    @classmethod
    def get_worker_settings(cls, worker_type: WorkerType) -> dict:
        """Get worker-specific Celery settings.

        Args:
            worker_type: Type of worker

        Returns:
            Dictionary of worker-specific settings
        """
        return cls._WORKER_SETTINGS.get(worker_type, {})

    @classmethod
    def get_logging_config(cls, worker_type: WorkerType) -> dict:
        """Get logging configuration for a worker type.

        Args:
            worker_type: Type of worker

        Returns:
            Logging configuration dict
        """
        return cls._LOGGING_CONFIGS.get(
            worker_type,
            {
                "log_format": "structured",
                "log_level": "INFO",
            },
        )

    @classmethod
    def get_complete_config(cls, worker_type: WorkerType) -> WorkerCeleryConfig:
        """Get complete configuration for a worker type.

        Args:
            worker_type: Type of worker

        Returns:
            Complete WorkerCeleryConfig object
        """
        queue_config = cls.get_queue_config(worker_type)
        task_routing = cls.get_task_routing(worker_type)
        settings = cls.get_worker_settings(worker_type)

        # Build health config
        health_checks = cls.get_health_checks(worker_type)
        health_config = WorkerHealthConfig(
            port=worker_type.to_health_port(), custom_checks=health_checks
        )

        # Create complete config with defaults and overrides
        config = WorkerCeleryConfig(
            worker_type=worker_type,
            queue_config=queue_config,
            task_routing=task_routing,
            health_config=health_config,
        )

        # Apply worker-specific settings
        for key, value in settings.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    @classmethod
    def validate_registry(cls) -> list[str]:
        """Validate the registry configuration.

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Check all WorkerTypes have configurations
        for worker_type in WorkerType:
            if worker_type not in cls._QUEUE_CONFIGS:
                errors.append(f"Missing queue config for {worker_type}")

            if worker_type not in cls._TASK_ROUTES:
                errors.append(f"Missing task routes for {worker_type}")

        # Validate queue names in task routes
        for worker_type, routing in cls._TASK_ROUTES.items():
            queue_config = cls._QUEUE_CONFIGS.get(worker_type)
            if not queue_config:
                continue

            valid_queues = queue_config.all_queues()
            for route in routing.routes:
                if route.queue.value not in valid_queues:
                    # Check if it's a valid queue for cross-worker routing
                    if route.queue not in QueueName:
                        errors.append(
                            f"Invalid queue {route.queue} in {worker_type} routing"
                        )

        return errors

    @classmethod
    def list_workers(cls) -> list[dict]:
        """List all registered workers with their configurations.

        Returns:
            List of worker configuration summaries
        """
        workers = []
        for worker_type in WorkerType:
            try:
                queue_config = cls.get_queue_config(worker_type)
                task_routing = cls.get_task_routing(worker_type)
                health_checks = cls.get_health_checks(worker_type)

                workers.append(
                    {
                        "type": worker_type.value,
                        "name": worker_type.to_worker_name(),
                        "import_path": worker_type.to_import_path(),
                        "health_port": worker_type.to_health_port(),
                        "queues": list(queue_config.all_queues()),
                        "task_count": len(task_routing.routes),
                        "health_checks": len(health_checks),
                    }
                )
            except KeyError:
                workers.append(
                    {
                        "type": worker_type.value,
                        "name": worker_type.to_worker_name(),
                        "error": "Not configured in registry",
                    }
                )

        return workers
