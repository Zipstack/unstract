"""Core TaskBackend interface - the heart of the abstraction.

This is the "SQLAlchemy for task queues" - a simple, clean interface
that works across Celery, Hatchet, and Temporal backends.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import BackendConfig, TaskResult
    from .workflow import WorkflowDefinition


class TaskBackend(ABC):
    """Abstract base class for task queue backends.

    This interface provides the core operations that all backend
    implementations (Celery, Hatchet, Temporal) must provide.

    The focus is on a minimal, clean API that delegates production
    features (retries, DLQ, persistence) to the underlying backend.
    """

    def __init__(self, config: Optional["BackendConfig"] = None):
        """Initialize backend with configuration.

        Note: Persistence is handled by the backend's native mechanisms.
        Configure retries, DLQ, and state storage in your backend configuration.
        """

        self.config = config
        self._tasks = {}
        self._workflows = {}

    @abstractmethod
    def register_task(self, fn: Callable, name: str | None = None) -> Callable:
        """Register a function as a task.

        Args:
            fn: Function to register as a task
            name: Optional task name (defaults to function name)

        Returns:
            The registered function (for use as decorator)

        Example:
            @backend.register_task
            def add_numbers(a: int, b: int) -> int:
                return a + b
        """
        pass

    @abstractmethod
    def submit(self, task_name: str, *args, **kwargs) -> str:
        """Submit a task for execution.

        Args:
            task_name: Name of the registered task
            *args: Positional arguments for the task
            **kwargs: Keyword arguments for the task

        Returns:
            Task ID for tracking execution

        Example:
            task_id = backend.submit("add_numbers", 10, 20)
        """
        pass

    @abstractmethod
    def get_result(self, task_id: str) -> "TaskResult":
        """Get task execution result.

        Args:
            task_id: Task ID returned from submit()

        Returns:
            TaskResult with status and result/error information

        Note:
            Backends handle their own retry logic. This just returns
            the current state of the task.

        Example:
            result = backend.get_result(task_id)
            if result.is_completed:
                print(f"Result: {result.result}")
        """
        pass

    @abstractmethod
    def run_worker(self, **kwargs) -> None:
        """Start a worker process to execute tasks.

        Args:
            **kwargs: Backend-specific worker configuration

        Note:
            This blocks and runs the worker. Configure retries, queues,
            and other production features in backend-specific config.

        Example:
            backend.run_worker(concurrency=4, loglevel="info")
        """
        pass

    def register_workflow(self, workflow_def: "WorkflowDefinition") -> None:
        """Register a workflow definition.

        Args:
            workflow_def: WorkflowDefinition to register

        Example:
            workflow = WorkflowDefinition.sequential([
                "extract_data",
                "transform_data"
            ])
            backend.register_workflow(workflow)
        """
        self._workflows[workflow_def.name] = workflow_def

    def submit_workflow(self, name: str, initial_input: Any) -> str:
        """Submit a workflow for execution.

        Args:
            name: Registered workflow name
            initial_input: Initial input data

        Returns:
            Workflow execution ID

        Note:
            Simple implementation that delegates to WorkflowExecutor.
            For production use, configure resilience in your backend.
        """
        import uuid

        from .workflow import WorkflowExecutor

        workflow_def = self._workflows[name]
        workflow_id = f"workflow-{uuid.uuid4()}"

        # Use simple WorkflowExecutor (no resilience bloat)
        executor = WorkflowExecutor(self)
        try:
            final_result = executor.execute_workflow_patterns(workflow_def, initial_input)
            return workflow_id
        except Exception as e:
            # In production, backends should handle workflow retry/recovery
            raise Exception(f"Workflow {name} failed: {e}") from e

    def get_workflow_result(self, workflow_id: str) -> "TaskResult":
        """Get workflow execution result.

        Args:
            workflow_id: Workflow ID from submit_workflow()

        Returns:
            TaskResult with workflow execution status

        Note:
            Simple implementation. For production, use backend-native
            workflow state tracking.
        """
        from .models import TaskResult

        # Simple implementation - in production, backends track workflow state
        return TaskResult(
            task_id=workflow_id,
            task_name="workflow",
            status="completed",
            result="Workflow completed (simple implementation)",
        )
