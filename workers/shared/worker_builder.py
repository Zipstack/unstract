"""Worker Builder - Factory for Creating Configured Celery Workers

This module provides a builder pattern for creating Celery workers with
standardized configuration, reducing duplication across worker implementations.

Migration Note: This is the core factory that creates workers using the
centralized registry, replacing individual worker.py configuration code.
"""

import logging
import os
from typing import Any

from celery import Celery
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger
from shared.infrastructure.monitoring.health import HealthChecker, HealthServer

logger = logging.getLogger(__name__)


class WorkerBuilder:
    """Builder for creating configured Celery workers.

    This class uses the builder pattern to create fully configured
    Celery workers with health checks, logging, and proper routing.
    """

    @staticmethod
    def build_celery_app(
        worker_type: WorkerType,
        app_name: str | None = None,
        override_config: dict[str, Any] | None = None,
    ) -> tuple[Celery, WorkerConfig]:
        """Build a configured Celery app for the specified worker type.

        Args:
            worker_type: Type of worker to build
            app_name: Optional custom app name
            override_config: Optional config overrides

        Returns:
            Tuple of (Celery app, WorkerConfig)

        Raises:
            ValueError: If worker type is not properly configured
        """
        logger.info(f"Building Celery app for {worker_type}")

        # Get configuration from environment
        config = WorkerConfig.from_env(worker_type.name)

        # Get complete configuration from registry
        worker_celery_config = WorkerRegistry.get_complete_config(worker_type)

        # Create Celery app
        app_name = app_name or f"{worker_type.value}_worker"
        app = Celery(app_name)

        # Build Celery configuration
        celery_config = worker_celery_config.to_celery_dict(
            broker_url=config.celery_broker_url,
            result_backend=config.celery_result_backend,
        )

        # Apply any overrides
        if override_config:
            celery_config.update(override_config)

        # Apply configuration to Celery app
        app.conf.update(celery_config)

        logger.info(
            f"Built {worker_type} worker with queues: "
            f"{worker_celery_config.queue_config.all_queues()}"
        )

        return app, config

    @staticmethod
    def setup_logging(worker_type: WorkerType) -> logging.Logger:
        """Setup standardized logging for a worker.

        Args:
            worker_type: Type of worker

        Returns:
            Configured logger instance
        """
        logging_config = WorkerRegistry.get_logging_config(worker_type)

        WorkerLogger.configure(
            log_level=os.getenv("LOG_LEVEL", logging_config.get("log_level", "INFO")),
            log_format=os.getenv(
                "LOG_FORMAT", logging_config.get("log_format", "structured")
            ),
            worker_name=worker_type.to_worker_name(),
        )

        return WorkerLogger.get_logger(worker_type.to_worker_name())

    @staticmethod
    def setup_health_monitoring(
        worker_type: WorkerType, config: WorkerConfig
    ) -> tuple[HealthChecker, HealthServer]:
        """Setup health monitoring for a worker.

        Args:
            worker_type: Type of worker
            config: Worker configuration

        Returns:
            Tuple of (HealthChecker, HealthServer)
        """
        health_checker = HealthChecker(config)

        # Register all health checks from registry
        for name, check_func in WorkerRegistry.get_health_checks(worker_type):
            health_checker.add_custom_check(name, check_func)

        # Get health port from worker type or environment
        health_port = int(
            os.getenv(
                f"{worker_type.name}_HEALTH_PORT", str(worker_type.to_health_port())
            )
        )

        health_server = HealthServer(health_checker=health_checker, port=health_port)

        logger.info(f"Health monitoring configured on port {health_port}")

        return health_checker, health_server

    @staticmethod
    def create_worker(
        worker_type: WorkerType,
        with_health: bool = True,
        with_logging: bool = True,
        override_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a complete worker with all components.

        Args:
            worker_type: Type of worker to create
            with_health: Enable health monitoring
            with_logging: Setup logging
            override_config: Optional config overrides

        Returns:
            Dictionary with worker components:
                - app: Celery application
                - config: WorkerConfig
                - logger: Logger instance (if with_logging)
                - health_checker: HealthChecker (if with_health)
                - health_server: HealthServer (if with_health)
        """
        components = {}

        # Setup logging if requested
        if with_logging:
            components["logger"] = WorkerBuilder.setup_logging(worker_type)
            components["logger"].info(f"Creating {worker_type} worker")

        # Build Celery app
        app, config = WorkerBuilder.build_celery_app(
            worker_type, override_config=override_config
        )
        components["app"] = app
        components["config"] = config

        # Setup health monitoring if requested
        if with_health:
            health_checker, health_server = WorkerBuilder.setup_health_monitoring(
                worker_type, config
            )
            components["health_checker"] = health_checker
            components["health_server"] = health_server

        if with_logging:
            components["logger"].info(f"{worker_type} worker created successfully")

        return components

    @staticmethod
    def validate_worker(worker_type: WorkerType) -> list[str]:
        """Validate worker configuration before building.

        Args:
            worker_type: Type of worker to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check if worker is registered
        try:
            WorkerRegistry.get_queue_config(worker_type)
        except KeyError:
            errors.append(f"No queue configuration for {worker_type}")

        try:
            WorkerRegistry.get_task_routing(worker_type)
        except KeyError:
            errors.append(f"No task routing for {worker_type}")

        # Check if tasks module exists
        import_path = worker_type.to_import_path()
        try:
            import importlib

            importlib.import_module(import_path)
        except ImportError as e:
            errors.append(f"Cannot import {import_path}: {e}")

        return errors

    @staticmethod
    def get_cli_command(worker_type: WorkerType) -> list[str]:
        """Get Celery CLI command for running the worker.

        Args:
            worker_type: Type of worker

        Returns:
            List of command arguments for celery worker
        """
        worker_config = WorkerRegistry.get_complete_config(worker_type)
        return worker_config.to_cli_args()


# LegacyWorkerAdapter removed - no more fallback logic
# All workers now use the direct WorkerBuilder.build_celery_app() approach
