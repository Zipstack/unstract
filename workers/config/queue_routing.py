"""Queue Routing Configuration for Lightweight Workers

Defines task routing rules, queue priorities, and worker assignments.
"""

import logging

logger = logging.getLogger(__name__)


class QueueRoutingConfig:
    """Configuration for Celery task routing and queue management."""

    # Queue definitions with their characteristics
    QUEUE_DEFINITIONS = {
        # API Deployment Workers
        "celery_api_deployments": {
            "worker_type": "api_deployment",
            "priority": "high",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
            "routing_key": "api.deployment",
            "exchange": "unstract.api",
            "description": "API workflow deployments and executions",
        },
        # General Workers
        "celery": {
            "worker_type": "general",
            "priority": "medium",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
            "routing_key": "general.tasks",
            "exchange": "unstract.general",
            "description": "General tasks including webhooks and standard workflows",
        },
        # File Processing Workers (Phase 2)
        "file_processing": {
            "worker_type": "file_processing",
            "priority": "high",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 500,
            "routing_key": "file.processing",
            "exchange": "unstract.files",
            "description": "File processing and tool execution",
        },
        "api_file_processing": {
            "worker_type": "file_processing",
            "priority": "high",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 500,
            "routing_key": "api.file.processing",
            "exchange": "unstract.api",
            "description": "API file processing with auto-scaling",
        },
        # Callback Workers (Phase 2)
        "file_processing_callback": {
            "worker_type": "callback",
            "priority": "medium",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
            "routing_key": "file.callback",
            "exchange": "unstract.callbacks",
            "description": "File processing result aggregation",
        },
        "api_file_processing_callback": {
            "worker_type": "callback",
            "priority": "medium",
            "concurrency": 4,
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
            "routing_key": "api.file.callback",
            "exchange": "unstract.api",
            "description": "API file processing callbacks",
        },
        # Logging Workers (Phase 3)
        "celery_periodic_logs": {
            "worker_type": "logging",
            "priority": "low",
            "concurrency": 2,
            "prefetch_multiplier": 4,
            "max_tasks_per_child": 2000,
            "routing_key": "logs.periodic",
            "exchange": "unstract.logs",
            "description": "Periodic log processing",
        },
        "celery_log_task_queue": {
            "worker_type": "logging",
            "priority": "low",
            "concurrency": 2,
            "prefetch_multiplier": 4,
            "max_tasks_per_child": 2000,
            "routing_key": "logs.tasks",
            "exchange": "unstract.logs",
            "description": "Real-time log streaming",
        },
    }

    # Task routing rules mapping tasks to queues
    TASK_ROUTES = {
        # Phase 1: API Deployment & General Workers
        "async_execute_bin_api": "celery_api_deployments",
        "send_webhook_notification": "celery",
        "async_execute_bin_general": "celery",
        "send_webhook_batch": "celery",
        "webhook_delivery_status_check": "celery",
        # Phase 2: File Processing Workers
        "process_file_batch": "file_processing",
        "process_file_batch_api": "api_file_processing",
        "process_batch_callback": "file_processing_callback",
        "process_batch_callback_api": "api_file_processing_callback",
        # Phase 3: Logging Workers
        "process_periodic_logs": "celery_periodic_logs",
        "stream_logs": "celery_log_task_queue",
        # Default routing
        "*": "celery",  # Default queue for unspecified tasks
    }

    # Worker scaling configurations
    SCALING_CONFIG = {
        "api_deployment": {
            "min_workers": 1,
            "max_workers": 8,
            "scale_up_threshold": 10,  # Queue length
            "scale_down_threshold": 2,
            "scale_up_by": 2,
            "scale_down_by": 1,
            "cooldown_period": 60,  # seconds
        },
        "general": {
            "min_workers": 1,
            "max_workers": 6,
            "scale_up_threshold": 15,
            "scale_down_threshold": 3,
            "scale_up_by": 2,
            "scale_down_by": 1,
            "cooldown_period": 120,
        },
        "file_processing": {
            "min_workers": 2,
            "max_workers": 12,
            "scale_up_threshold": 20,
            "scale_down_threshold": 5,
            "scale_up_by": 3,
            "scale_down_by": 1,
            "cooldown_period": 30,
        },
        "callback": {
            "min_workers": 1,
            "max_workers": 4,
            "scale_up_threshold": 8,
            "scale_down_threshold": 2,
            "scale_up_by": 1,
            "scale_down_by": 1,
            "cooldown_period": 90,
        },
        "logging": {
            "min_workers": 1,
            "max_workers": 3,
            "scale_up_threshold": 50,
            "scale_down_threshold": 10,
            "scale_up_by": 1,
            "scale_down_by": 1,
            "cooldown_period": 300,
        },
    }

    @classmethod
    def get_queue_config(cls, queue_name: str) -> dict | None:
        """Get configuration for a specific queue."""
        return cls.QUEUE_DEFINITIONS.get(queue_name)

    @classmethod
    def get_route_for_task(cls, task_name: str) -> str:
        """Get the appropriate queue for a task."""
        return cls.TASK_ROUTES.get(task_name, cls.TASK_ROUTES["*"])

    @classmethod
    def get_queues_for_worker_type(cls, worker_type: str) -> list[str]:
        """Get all queues that should be consumed by a worker type."""
        return [
            queue_name
            for queue_name, config in cls.QUEUE_DEFINITIONS.items()
            if config["worker_type"] == worker_type
        ]

    @classmethod
    def get_scaling_config(cls, worker_type: str) -> dict | None:
        """Get scaling configuration for a worker type."""
        return cls.SCALING_CONFIG.get(worker_type)

    @classmethod
    def generate_celery_routes(cls) -> dict[str, dict[str, str]]:
        """Generate Celery task routes configuration."""
        routes = {}
        for task, queue in cls.TASK_ROUTES.items():
            if task != "*":  # Skip default route
                queue_config = cls.get_queue_config(queue)
                if queue_config:
                    routes[task] = {
                        "queue": queue,
                        "exchange": queue_config["exchange"],
                        "routing_key": queue_config["routing_key"],
                    }
        return routes

    @classmethod
    def generate_celery_queue_config(cls) -> dict[str, dict]:
        """Generate Celery queue configuration."""
        from kombu import Exchange, Queue

        queues = {}
        for queue_name, config in cls.QUEUE_DEFINITIONS.items():
            exchange = Exchange(config["exchange"], type="direct", durable=True)

            queues[queue_name] = Queue(
                queue_name,
                exchange=exchange,
                routing_key=config["routing_key"],
                durable=True,
                message_ttl=86400,  # 24 hours
                max_length=10000,  # Max queue length
            )

        return queues

    @classmethod
    def log_configuration(cls):
        """Log the current routing configuration."""
        logger.info("=== Queue Routing Configuration ===")
        for queue_name, config in cls.QUEUE_DEFINITIONS.items():
            logger.info(f"Queue: {queue_name}")
            logger.info(f"  Worker Type: {config['worker_type']}")
            logger.info(f"  Priority: {config['priority']}")
            logger.info(f"  Concurrency: {config['concurrency']}")
            logger.info(f"  Exchange: {config['exchange']}")
            logger.info(f"  Routing Key: {config['routing_key']}")
            logger.info(f"  Description: {config['description']}")
            logger.info("")

        logger.info("=== Task Routes ===")
        for task, queue in cls.TASK_ROUTES.items():
            logger.info(f"{task} -> {queue}")


# Export the configuration for easy import
CELERY_TASK_ROUTES = QueueRoutingConfig.generate_celery_routes()
CELERY_QUEUES = QueueRoutingConfig.generate_celery_queue_config()
WORKER_SCALING_CONFIG = QueueRoutingConfig.SCALING_CONFIG
