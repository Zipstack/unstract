"""Task Backend Worker.

Simple worker that uses the task-abstraction library to start
backend-specific workers (Celery, Hatchet, Temporal).
"""

import logging
import logging.config
import signal
import socket
import sys

from dotenv import load_dotenv

# Import task abstraction library
from unstract.task_abstraction import TASK_REGISTRY, BackendConfig, get_backend

from .config import get_backend_config_for_type, get_task_backend_config

logger = logging.getLogger(__name__)


class TaskBackendWorker:
    """Simple worker that delegates to task-abstraction backends."""

    def __init__(
        self,
        backend_type: str | None = None,
        queues: list | None = None,
        worker_name: str | None = None,
        concurrency: int | None = None,
    ):
        """Initialize worker with backend type and queue configuration.

        Args:
            backend_type: Backend to use (celery, hatchet, temporal).
                         If None, uses config from environment.
            queues: List of queue names to listen to. If None, uses default queue for backend.
            worker_name: Worker instance name. If None, auto-generates from hostname and queues.
            concurrency: Number of worker processes/threads. If None, uses config default.
        """
        # Get backend type first, then load appropriate config
        if backend_type:
            self.backend_type = backend_type
            self.config = get_backend_config_for_type(backend_type)
        else:
            self.config = get_task_backend_config()
            self.backend_type = self.config.backend_type

        # Queue configuration with proper priority
        self.queues = self._resolve_queues(queues)

        # Concurrency override
        if concurrency:
            self.config.worker_concurrency = concurrency

        # Set worker name from argument or auto-generate
        if worker_name:
            self.config.worker_name = worker_name
        elif not self.config.worker_name:
            hostname = socket.gethostname()
            if len(self.queues) == 1:
                queue_suffix = f"-{self.queues[0]}"
            elif len(self.queues) > 1:
                queue_suffix = "-" + "-".join(sorted(self.queues))
            else:
                queue_suffix = ""
            self.config.worker_name = f"worker-{hostname}{queue_suffix}"

        self.backend = None
        self.shutdown_requested = False

    def _resolve_queues(self, cli_queues: list | None) -> list:
        """Resolve queue names with proper priority: CLI > ENV > Error.

        Args:
            cli_queues: Queue names from command line arguments

        Returns:
            List of queue names to listen to

        Raises:
            ValueError: If no queues specified anywhere
        """
        import os

        # Priority 1: CLI arguments (explicit deployment)
        if cli_queues:
            queues = [q.strip() for q in cli_queues if q and q.strip()]
            if not queues:
                raise ValueError(
                    "No queues specified via --queues after trimming empty entries."
                )
            logger.info(f"Using queues from CLI arguments: {', '.join(queues)}")
            return queues

        # Priority 2: Environment variable (dev convenience only)
        environment = os.getenv("ENVIRONMENT", "prod").lower()
        env_queues = os.getenv("TASK_QUEUES")

        if env_queues and environment != "prod":
            queues = [q.strip() for q in env_queues.split(",") if q.strip()]
            logger.info(
                f"Using queues from TASK_QUEUES environment (ENVIRONMENT={environment}): {', '.join(queues)}"
            )
            return queues
        elif env_queues and environment == "prod":
            logger.warning(
                "TASK_QUEUES ignored in production environment. Use --queues argument."
            )

        # Priority 3: Error - no queues specified
        if environment == "prod":
            raise ValueError(
                "No queues specified for production deployment.\n"
                "Use --queues argument: uv run task-backend-worker --queues file_processing"
            )
        else:
            raise ValueError(
                "No queues specified. Either:\n"
                "1. Use --queues argument: uv run task-backend-worker --queues file_processing\n"
                "2. Set TASK_QUEUES environment variable: TASK_QUEUES=file_processing,api_processing"
            )

    def start(self) -> None:
        """Start the worker for the configured backend."""
        logger.info(
            f"Starting task backend worker - backend: {self.backend_type}, "
            f"worker: {self.config.worker_name}"
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Create backend configuration
            backend_config = BackendConfig(
                backend_type=self.backend_type,
                connection_params=self._get_connection_params(),
                worker_config=self._get_worker_config(),
            )

            # Get backend instance using task-abstraction with our config
            self.backend = get_backend(backend_config)

            # Register any tasks that should be available
            self._register_tasks()

            # Start the backend worker (this blocks)
            logger.info(f"Starting backend worker: {self.backend_type}")
            self.backend.run_worker()

        except Exception as e:
            logger.error(f"Failed to start worker: {str(e)}", exc_info=True)
            sys.exit(1)

    def _register_tasks(self) -> None:
        """Register tasks with the backend.

        This registers all tasks from the tasks module with the backend.
        """
        if not self.backend:
            logger.error("Cannot register tasks: backend not initialized")
            return

        logger.info(f"Registering tasks with backend: {self.backend_type}")

        registered_tasks = []

        for task_func in TASK_REGISTRY:
            task_name = task_func.__name__

            try:
                # Register the task with the backend
                self.backend.register_task(task_func)
                registered_tasks.append(task_name)
                logger.debug(f"Registered task: {task_name}")
            except Exception as e:
                logger.error(f"Failed to register task {task_name}: {str(e)}")

        logger.info(
            f"Task registration completed - registered {len(registered_tasks)} tasks: "
            f"{', '.join(registered_tasks)}"
        )

        logger.info(f"Worker listening to queues: {', '.join(self.queues)}")

    def _get_connection_params(self) -> dict:
        """Get backend-specific connection parameters from config."""
        return self.config.get_backend_specific_config(self.queues)

    def _get_worker_config(self) -> dict:
        """Get worker configuration for the backend."""
        base_config = {
            "concurrency": self.config.worker_concurrency,
            "queues": self.queues,  # Pass queues to backend
        }

        # Add backend-specific worker settings
        if self.backend_type == "celery":
            base_config.update(
                {
                    "max_tasks_per_child": 100,
                }
            )
        elif self.backend_type == "hatchet":
            base_config.update(
                {
                    "max_runs": 100,
                    "workflows": self.queues,  # Map queues to workflows for Hatchet
                }
            )
        elif self.backend_type == "temporal":
            base_config.update(
                {
                    "task_queues": self.queues,  # Map queues to task queues for Temporal
                    "max_concurrent_activities": 100,
                    "max_concurrent_workflow_tasks": 100,
                }
            )

        return base_config

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received shutdown signal: {signum}")
        self.shutdown_requested = True

        logger.info("Initiating graceful worker shutdown")
        if self.backend and hasattr(self.backend, "stop"):
            try:
                # Give the backend a chance to finish current tasks
                logger.info("Requesting backend graceful shutdown")
                self.backend.stop(graceful=True)
            except Exception as e:
                logger.error(f"Error during graceful shutdown: {e}", exc_info=True)

        sys.exit(0)


def main() -> None:
    """Main entry point for the task backend worker."""
    # Load .env file to ensure environment variables are available
    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser(description="Task Backend Worker")
    parser.add_argument(
        "--backend",
        choices=["celery", "hatchet", "temporal"],
        help="Backend type to use (overrides environment config)",
    )
    parser.add_argument(
        "--queues",
        help="Comma-separated list of queues to listen to (e.g., 'file_processing,api_processing'). If not specified, uses default queue.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Number of worker processes/threads (overrides config)",
    )
    parser.add_argument(
        "--worker-name", help="Worker instance name (auto-generated if not provided)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )

    args = parser.parse_args()

    # Configure logging using Unstract's complete format with request_id
    log_level = getattr(logging, args.log_level, logging.INFO)

    # Define request_id filter for worker context
    class RequestIDFilter(logging.Filter):
        def filter(self, record):
            # For worker processes, we can use task_id or a generated request_id
            if not hasattr(record, "request_id"):
                record.request_id = "-"
            return True

    # Define OTel filter for consistency
    class OTelFieldFilter(logging.Filter):
        def filter(self, record):
            for attr in ["otelTraceID", "otelSpanID"]:
                if not hasattr(record, attr):
                    setattr(record, attr, "-")
            return True

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": RequestIDFilter},
                "otel_ids": {"()": OTelFieldFilter},
            },
            "formatters": {
                "enriched": {
                    "format": (
                        "%(levelname)s : [%(asctime)s]"
                        "{module:%(module)s process:%(process)d "
                        "thread:%(thread)d request_id:%(request_id)s "
                        "trace_id:%(otelTraceID)s span_id:%(otelSpanID)s} :- %(message)s"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "level": log_level,
                    "class": "logging.StreamHandler",
                    "filters": ["request_id", "otel_ids"],
                    "formatter": "enriched",
                },
            },
            "root": {
                "level": log_level,
                "handlers": ["console"],
            },
        }
    )

    # Parse queue arguments
    queues = args.queues.split(",") if args.queues else None

    # Create and start worker
    worker = TaskBackendWorker(
        backend_type=args.backend,
        queues=queues,
        worker_name=args.worker_name,
        concurrency=args.concurrency,
    )

    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
