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

from ...enums.worker_enums import WorkerType
from ..logging import WorkerLogger
from ..monitoring.health import HealthChecker, HealthServer
from .registry import WorkerRegistry
from .worker_config import WorkerConfig

logger = logging.getLogger(__name__)


def get_chord_config_override() -> dict[str, Any]:
    """Get chord-specific configuration override for workers that use chords.

    This provides task annotations for celery.chord_unlock to:
    - Set custom retry intervals (default 3s instead of 1s)
    - Set maximum retries based on duration or explicit count
    - Support infinite retries with -1 flag

    Returns:
        Dictionary with task_annotations for chord_unlock configuration
    """
    import os

    def calculate_chord_max_retries() -> int | None:
        """Calculate max retries for chord unlock tasks."""
        # Check for direct override first
        retry_count_env = os.getenv("CELERY_RESULT_CHORD_RETRY_COUNT")
        if retry_count_env is not None:
            retry_count = int(retry_count_env)
            if retry_count == -1:
                return None  # Infinite retries
            return retry_count

        # Calculate from duration
        retry_delay = int(os.getenv("CELERY_RESULT_CHORD_RETRY_INTERVAL", "3"))
        target_days = int(os.getenv("CELERY_RESULT_CHORD_RETRY_DAYS", "2"))
        return (target_days * 24 * 60 * 60) // retry_delay

    chord_retry_delay = int(os.getenv("CELERY_RESULT_CHORD_RETRY_INTERVAL", "3"))
    chord_max_retries = calculate_chord_max_retries()

    logger.info(
        f"CHORD_CONFIG: retry_delay={chord_retry_delay}, max_retries={chord_max_retries}"
    )

    return {
        "task_annotations": {
            "celery.chord_unlock": {
                "default_retry_delay": chord_retry_delay,
                "max_retries": chord_max_retries,
            }
        }
    }


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

        # Apply chord configuration for workers that use chords
        chord_workers = {
            WorkerType.CALLBACK,
            WorkerType.GENERAL,
            WorkerType.API_DEPLOYMENT,
        }
        if worker_type in chord_workers:
            chord_config = get_chord_config_override()
            celery_config.update(chord_config)
            logger.info(
                f"Applied chord configuration for {worker_type}: {chord_config.get('task_annotations', {}).get('celery.chord_unlock', {})}"
            )

        # Apply any additional overrides
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
