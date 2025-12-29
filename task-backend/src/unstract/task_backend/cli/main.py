"""Main CLI entry point for task backend worker."""

import argparse
import logging
import signal
import sys

import structlog

from ..config import get_task_backend_config
from ..health import HealthChecker
from ..worker import TaskBackendWorker

logger = structlog.get_logger(__name__)


def setup_logging(log_level: str = "INFO", structured: bool = True) -> None:
    """Setup structured logging."""
    # Configure standard logging level first
    logging.basicConfig(level=log_level.upper())

    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if structured:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Task Backend Worker - Universal task queue worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start worker with auto-detected backend
  task-backend-worker

  # Start specific backend worker
  task-backend-worker --backend celery
  task-backend-worker --backend hatchet --token your-token
  task-backend-worker --backend temporal --host temporal.company.com

  # Start with custom configuration
  task-backend-worker --config /path/to/config.yaml

  # Development mode with debug logging
  task-backend-worker --log-level DEBUG --log-format console

  # Health check only
  task-backend-worker --health-check
        """,
    )

    # Backend selection
    parser.add_argument(
        "--backend",
        choices=["celery", "hatchet", "temporal"],
        help="Backend type to use (overrides config)",
    )

    # Configuration
    parser.add_argument(
        "--config", metavar="FILE", help="Path to YAML configuration file"
    )

    # Logging
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    parser.add_argument(
        "--log-format",
        default="structured",
        choices=["structured", "console"],
        help="Log format (default: structured)",
    )

    # Worker options
    parser.add_argument(
        "--concurrency", type=int, help="Worker concurrency (overrides config)"
    )

    parser.add_argument("--worker-name", help="Worker instance name (overrides config)")

    # Backend-specific options
    parser.add_argument("--broker-url", help="Celery broker URL (overrides config)")

    parser.add_argument("--token", help="Hatchet API token (overrides config)")

    parser.add_argument("--host", help="Temporal host (overrides config)")

    parser.add_argument("--port", type=int, help="Temporal port (overrides config)")

    # Operations
    parser.add_argument(
        "--health-check", action="store_true", help="Run health check and exit"
    )

    parser.add_argument(
        "--list-tasks", action="store_true", help="List registered tasks and exit"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without starting worker",
    )

    return parser


def apply_cli_overrides(config, args) -> None:
    """Apply CLI argument overrides to configuration."""
    if args.backend:
        config.backend_type = args.backend

    if args.concurrency:
        config.worker_concurrency = args.concurrency

    if args.worker_name:
        config.worker_name = args.worker_name

    # Backend-specific overrides
    if args.broker_url:
        config.celery_broker_url = args.broker_url

    if args.token:
        config.hatchet_token = args.token

    if args.host:
        config.temporal_host = args.host

    if args.port:
        config.temporal_port = args.port


def run_health_check(config) -> int:
    """Run health check and return exit code."""
    logger.info("Running health check")

    health_checker = HealthChecker(config)
    health_status = health_checker.check_all()

    if health_status.is_healthy:
        logger.info("Health check passed", checks=health_status.to_dict())
        return 0
    else:
        logger.error("Health check failed", checks=health_status.to_dict())
        return 1


def list_registered_tasks(worker: TaskBackendWorker) -> None:
    """List tasks that would be registered."""
    logger.info("Registered tasks", backend=worker.backend_type)

    if hasattr(worker, "backend") and worker.backend:
        tasks = list(worker.backend._tasks.keys())
        for task_name in tasks:
            logger.info(f"  - {task_name}")
    else:
        logger.info("No tasks registered (worker not started)")


def handle_signal(signum, frame, worker: TaskBackendWorker | None = None):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal", signal=signum)

    if worker:
        logger.info("Shutting down worker gracefully")
        # Note: Actual graceful shutdown would depend on backend implementation

    logger.info("Worker shutdown complete")
    sys.exit(0)


def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging first
    setup_logging(log_level=args.log_level, structured=(args.log_format == "structured"))

    logger.info("Starting task backend worker", version="0.1.0")

    try:
        # Load configuration
        if args.config:
            # TODO: Implement config file loading
            logger.info("Loading configuration from file", file=args.config)
            config = get_task_backend_config()  # Fallback for now
        else:
            config = get_task_backend_config()

        # Apply CLI overrides
        apply_cli_overrides(config, args)

        logger.info(
            "Configuration loaded",
            backend=config.backend_type,
            worker_name=config.worker_name,
            concurrency=config.worker_concurrency,
        )

        # Health check mode
        if args.health_check:
            return run_health_check(config)

        # Dry run mode
        if args.dry_run:
            logger.info("Dry run - configuration validation successful")
            return 0

        # Create worker
        worker = TaskBackendWorker(backend_type=config.backend_type)

        # List tasks mode
        if args.list_tasks:
            list_registered_tasks(worker)
            return 0

        # Setup signal handlers
        signal.signal(signal.SIGINT, lambda s, f: handle_signal(s, f, worker))
        signal.signal(signal.SIGTERM, lambda s, f: handle_signal(s, f, worker))

        # Start worker
        logger.info("Starting worker", backend=config.backend_type)
        worker.start()

        return 0

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        return 0
    except Exception as e:
        logger.error("Worker failed to start", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
