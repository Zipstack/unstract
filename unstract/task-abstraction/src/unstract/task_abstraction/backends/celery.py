"""Celery backend implementation for task abstraction."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from celery import Celery
    from celery.result import AsyncResult

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

from ..base import TaskBackend
from ..models import BackendConfig, TaskResult

if TYPE_CHECKING:
    from ..workflow import WorkflowResult

logger = logging.getLogger(__name__)


class CeleryBackend(TaskBackend):
    """Celery task queue backend implementation.

    This backend maps the TaskBackend interface to Celery operations:
    - register_task() → @celery_app.task decorator
    - submit() → task.delay() call
    - get_result() → AsyncResult query
    - run_worker() → celery worker process
    """

    def __init__(self, config: BackendConfig | None = None):
        """Initialize Celery backend.

        Args:
            config: Backend configuration with Celery connection parameters
        """
        if not CELERY_AVAILABLE:
            raise ImportError("Missing dependency: celery")

        super().__init__(config)
        logger.info("Initializing Celery backend")

        if config:
            self.config = config
        else:
            # Use default Redis configuration
            self.config = BackendConfig(
                backend_type="celery",
                connection_params={
                    "broker_url": "redis://localhost:6379/0",
                    "result_backend": "redis://localhost:6379/0",
                },
            )

        # Initialize Celery app
        logger.debug(
            f"Configuring Celery with broker: {self.config.connection_params['broker_url']}"
        )
        self.app = Celery("task-abstraction")
        self.app.conf.update(
            broker_url=self.config.connection_params["broker_url"],
            result_backend=self.config.connection_params.get("result_backend"),
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
        )

        # Apply worker configuration
        if self.config.worker_config:
            self.app.conf.update(**self.config.worker_config)

    def register_task(self, fn: Callable, name: str | None = None) -> Callable:
        """Register a function as a Celery task.

        Args:
            fn: Python function to register as task
            name: Optional task name (defaults to function name)

        Returns:
            The registered Celery task

        Example:
            @backend.register_task
            def add(x, y):
                return x + y
        """
        task_name = name or fn.__name__
        logger.debug(f"Registering Celery task: {task_name}")

        # Create Celery task with the original function
        celery_task = self.app.task(name=task_name)(fn)

        # Store in our tasks registry
        self._tasks[task_name] = celery_task
        logger.info(f"Successfully registered Celery task: {task_name}")

        return celery_task

    def submit(self, name: str, *args, **kwargs) -> str:
        """Submit a task for execution.

        Args:
            name: Name of registered task
            *args: Positional arguments for task
            **kwargs: Keyword arguments for task

        Returns:
            Task ID for tracking execution

        Example:
            task_id = backend.submit("add", 2, 3)
        """
        if name not in self._tasks:
            raise ValueError(f"Task '{name}' not registered")

        celery_task = self._tasks[name]
        result = celery_task.delay(*args, **kwargs)

        return result.id

    def get_result(self, task_id: str) -> TaskResult:
        """Retrieve the result of a task execution.

        Args:
            task_id: Task execution ID from submit()

        Returns:
            TaskResult with standardized result format

        Example:
            result = backend.get_result(task_id)
            if result.is_completed:
                print(result.result)
        """
        async_result = AsyncResult(task_id, app=self.app)

        # Map Celery states to our standard states
        status_mapping = {
            "PENDING": "pending",
            "STARTED": "running",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "RETRY": "running",
            "REVOKED": "failed",
        }

        status = status_mapping.get(async_result.state, "pending")

        # Get task name from result info (if available)
        task_name = getattr(async_result, "name", "unknown")

        # Build TaskResult
        task_result = TaskResult(
            task_id=task_id,
            task_name=task_name,
            status=status,
        )

        if status == "completed":
            task_result.result = async_result.result
        elif status == "failed":
            task_result.error = (
                str(async_result.result) if async_result.result else "Task failed"
            )

        # Get timing info if available
        if hasattr(async_result, "date_done") and async_result.date_done:
            task_result.completed_at = async_result.date_done

        return task_result

    def run_worker(self) -> None:
        """Start the Celery worker process.

        This method blocks and runs the Celery worker with the configured
        settings. The worker will consume tasks from the broker and execute
        registered tasks.

        Example:
            backend.run_worker()  # Blocks until shutdown
        """
        import os

        # Get worker configuration
        worker_config = self.config.worker_config or {}

        # Get queues to listen to
        queues = worker_config.get("queues", ["celery"])
        logger.info(f"Celery worker starting with queues: {', '.join(queues)}")

        # Check if events should be enabled (for monitoring with Flower, etc.)
        events_enabled = os.getenv("CELERY_EVENTS_ENABLED", "false").lower() == "true"

        # Configure app to send task events if enabled
        if events_enabled:
            # Set the worker_send_task_events configuration
            # This is equivalent to the -E flag
            self.app.conf.worker_send_task_events = True
            logger.info("Task events enabled for monitoring")

        # Build worker options
        worker_options = {
            "concurrency": worker_config.get("concurrency", 4),
            "max_tasks_per_child": worker_config.get("max_tasks_per_child", 100),
            "queues": queues,  # Pass queues to worker
        }

        # Start Celery worker
        # This is equivalent to running: celery -A app worker -Q queue1,queue2 [-E]
        worker = self.app.Worker(**worker_options)

        worker.start()

    @property
    def backend_type(self) -> str:
        """Get the backend type identifier."""
        return "celery"

    def is_connected(self) -> bool:
        """Check if backend is connected to broker."""
        try:
            # Try to inspect the broker
            inspect = self.app.control.inspect()
            inspect.stats()
            return True
        except Exception:
            return False

    def submit_workflow(self, name: str, initial_input: Any) -> str:
        """Submit a workflow using Celery chains.

        Args:
            name: Name of registered workflow
            initial_input: Initial input data for workflow

        Returns:
            Workflow execution ID (chain result ID)

        This implementation uses Celery's chain feature to execute
        workflow steps sequentially.
        """
        if name not in self._workflows:
            raise ValueError(f"Workflow '{name}' not registered")

        workflow_def = self._workflows[name]

        try:
            # Import chain from celery
            from celery import chain

            # Build chain of tasks
            chain_tasks = []
            for step in workflow_def.steps:
                if step.task_name not in self._tasks:
                    raise ValueError(
                        f"Task '{step.task_name}' not registered in workflow '{name}'"
                    )

                celery_task = self._tasks[step.task_name]

                # Create signature with kwargs
                if step.kwargs:
                    # For steps with kwargs, we need to handle them specially
                    # This is a simplified implementation
                    chain_tasks.append(celery_task.s(**step.kwargs))
                else:
                    chain_tasks.append(celery_task.s())

            # Create and execute chain
            if chain_tasks:
                # For the first task, apply the initial input
                if chain_tasks:
                    # Start with initial input
                    workflow_chain = chain(*chain_tasks)
                    result = workflow_chain.apply_async(args=[initial_input])
                    return result.id

        except ImportError:
            # Fallback to sequential execution if chain is not available
            return super().submit_workflow(name, initial_input)
        except Exception:
            # Fallback to default implementation
            return super().submit_workflow(name, initial_input)

        return super().submit_workflow(name, initial_input)

    def get_workflow_result(self, workflow_id: str):
        """Get workflow result for Celery chain execution."""
        try:
            from celery.result import AsyncResult

            # Get the chain result
            chain_result = AsyncResult(workflow_id, app=self.app)

            # Map Celery chain status to workflow status
            status_mapping = {
                "PENDING": "pending",
                "STARTED": "running",
                "SUCCESS": "completed",
                "FAILURE": "failed",
                "RETRY": "running",
                "REVOKED": "failed",
            }

            status = status_mapping.get(chain_result.state, "pending")

            from ..workflow import WorkflowResult

            workflow_result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="celery_workflow",  # Could be enhanced to track actual name
                status=status,
                steps_completed=1 if status == "completed" else 0,
                total_steps=1,  # Chain is treated as single unit
            )

            if status == "completed":
                workflow_result.final_result = chain_result.result
            elif status == "failed":
                workflow_result.error = (
                    str(chain_result.result) if chain_result.result else "Workflow failed"
                )

            return workflow_result

        except Exception:
            # Fallback to default implementation
            return super().get_workflow_result(workflow_id)

    def _get_native_workflow_result(self, workflow_id: str) -> "WorkflowResult":
        """Get workflow result using Celery's native result backend.

        Uses Celery's AsyncResult to query workflow state from the configured
        result backend (Redis, Database, etc.).
        """
        try:
            from celery.result import AsyncResult

            from ..workflow import WorkflowResult

            # Get the task/chain result from Celery's result backend
            async_result = AsyncResult(workflow_id, app=self.app)

            # Map Celery status to workflow status
            status_mapping = {
                "PENDING": "pending",
                "STARTED": "running",
                "SUCCESS": "completed",
                "FAILURE": "failed",
                "RETRY": "running",
                "REVOKED": "failed",
            }

            status = status_mapping.get(async_result.state, "pending")

            # Create WorkflowResult from Celery result
            workflow_result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name=getattr(async_result, "name", "unknown"),
                status=status,
                steps_completed=1 if status == "completed" else 0,
                total_steps=1,
            )

            if status == "completed":
                workflow_result.final_result = async_result.result
            elif status == "failed":
                workflow_result.error = (
                    str(async_result.result) if async_result.result else "Workflow failed"
                )

            # Add timing information if available
            if hasattr(async_result, "date_done") and async_result.date_done:
                workflow_result.step_results = [
                    {
                        "completed_at": async_result.date_done.isoformat(),
                        "result": async_result.result if status == "completed" else None,
                        "error": str(async_result.result) if status == "failed" else None,
                    }
                ]

            return workflow_result

        except Exception as e:
            logger.error(f"Failed to get native workflow result for {workflow_id}: {e}")
            # Return not found result
            from ..workflow import WorkflowResult

            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="unknown",
                status="not_found",
                steps_completed=0,
                total_steps=0,
                error=f"Failed to retrieve from Celery result backend: {e}",
            )

    def _store_native_workflow_result(
        self, workflow_id: str, workflow_name: str, result_data: dict
    ) -> None:
        """Store workflow result using Celery's native result backend.

        Celery automatically stores task results in the configured result backend,
        but for workflow-level results we need to store additional metadata.
        """
        try:
            # For Celery, we can store workflow metadata as a separate result
            # using a special workflow metadata task
            workflow_metadata_key = f"workflow_meta:{workflow_id}"

            # Create a metadata record in Celery's result backend
            # This uses the same storage mechanism as regular task results

            # Create a synthetic result to store workflow metadata
            # Note: This is a simplified approach - in production you might want
            # to use Celery's result backend directly or store in a dedicated table
            metadata = {
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "stored_at": datetime.now().isoformat(),
                **result_data,
            }

            # Store using Celery's result backend
            backend = self.app.backend
            backend.store_result(workflow_metadata_key, metadata, status="SUCCESS")

            logger.debug(
                f"Stored workflow metadata in Celery result backend: {workflow_id}"
            )

        except Exception as e:
            logger.error(f"Failed to store workflow result in Celery backend: {e}")
            # Don't raise - this is supplementary storage
