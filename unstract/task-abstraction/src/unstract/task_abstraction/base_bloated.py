"""Core TaskBackend interface - the heart of the abstraction.

This is the "SQLAlchemy for task queues" - a simple, clean interface
that works across Celery, Hatchet, and Temporal backends.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import BackendConfig
    from .workflow import WorkflowDefinition, WorkflowResult


class TaskBackend(ABC):
    """Abstract base class for task queue backends.

    This interface provides the core operations that all backend
    implementations (Celery, Hatchet, Temporal) must provide.

    Usage:
        backend = get_backend("celery")

        @backend.register_task
        def add(x, y):
            return x + y

        task_id = backend.submit("add", 2, 3)
        result = backend.get_result(task_id)

    Workflow Usage:
        from unstract.task_abstraction.workflow import WorkflowDefinition, Sequential, Parallel

        # Sequential workflow
        workflow = WorkflowDefinition.sequential([
            ("add_numbers", {"a": 10, "b": 5}),
            "format_result_message"
        ])
        backend.register_workflow(workflow)
        workflow_id = backend.submit_workflow("my_workflow", initial_data)

        # Parallel workflow
        workflow = WorkflowDefinition.parallel([
            ("task_a", {"param": "value1"}),
            ("task_b", {"param": "value2"}),
            ("task_c", {"param": "value3"})
        ])

        # Mixed workflow
        workflow = WorkflowDefinition.mixed([
            Sequential([("extract_data", {})]),
            Parallel([("process_a", {}), ("process_b", {})]),
            Sequential([("aggregate_results", {})])
        ])
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
            fn: Python function to register as task
            name: Optional task name (defaults to function name)

        Returns:
            The registered task function (for decorator usage)

        Example:
            @backend.register_task
            def process_data(data):
                return processed_data
        """
        pass

    @abstractmethod
    def submit(self, name: str, *args, **kwargs) -> str:
        """Submit a task by name for execution.

        Args:
            name: Name of registered task
            *args: Positional arguments for task
            **kwargs: Keyword arguments for task

        Returns:
            Task ID for tracking execution

        Example:
            task_id = backend.submit("process_data", data=my_data)
        """
        pass

    @abstractmethod
    def get_result(self, task_id: str) -> Any:
        """Retrieve the result of a task execution.

        Args:
            task_id: Task execution ID from submit()

        Returns:
            Task result or raises exception if failed

        Example:
            result = backend.get_result(task_id)
        """
        pass

    @abstractmethod
    def run_worker(self) -> None:
        """Start the worker loop for this backend.

        This method blocks and runs the appropriate worker process:
        - Celery: Starts celery worker
        - Hatchet: Starts hatchet worker polling
        - Temporal: Starts temporal worker listening

        Example:
            backend.run_worker()  # Blocks until shutdown
        """
        pass

    @abstractmethod
    def _get_native_workflow_result(self, workflow_id: str) -> "WorkflowResult":
        """Get workflow result using backend's native persistence mechanism.

        Each backend should implement this using their native storage:
        - Celery: Use Redis/Database result backend
        - Hatchet: Query PostgreSQL workflow tables
        - Temporal: Use Temporal's workflow execution history

        Args:
            workflow_id: Workflow execution ID

        Returns:
            WorkflowResult from backend's native storage

        Raises:
            Exception: If workflow not found or backend error
        """
        pass

    @abstractmethod
    def _store_native_workflow_result(
        self, workflow_id: str, workflow_name: str, result_data: dict
    ) -> None:
        """Store workflow result using backend's native persistence mechanism.

        Args:
            workflow_id: Workflow execution ID
            workflow_name: Name of the workflow
            result_data: Dictionary containing workflow result data
        """
        pass

    def register_workflow(self, workflow_def: "WorkflowDefinition") -> None:
        """Register a workflow definition with this backend.

        Args:
            workflow_def: WorkflowDefinition to register

        Example:
            workflow_def = WorkflowDefinition.from_step_list(
                "data_pipeline",
                ["extract", "transform", "load"]
            )
            backend.register_workflow(workflow_def)
        """
        self._workflows[workflow_def.name] = workflow_def

    def submit_workflow(self, name: str, initial_input: Any) -> str:
        """Submit a workflow for execution.

        Args:
            name: Name of registered workflow
            initial_input: Initial input data for the workflow

        Returns:
            Workflow execution ID

        Example:
            workflow_id = backend.submit_workflow("data_pipeline", raw_data)
        """
        if name not in self._workflows:
            raise ValueError(f"Workflow '{name}' not registered")

        # Default implementation: execute steps sequentially
        return self._execute_linear_workflow(name, initial_input)

    def get_workflow_result(self, workflow_id: str) -> "WorkflowResult":
        """Get the result of a workflow execution using hybrid persistence.

        Args:
            workflow_id: Workflow execution ID

        Returns:
            WorkflowResult with status and results

        Example:
            result = backend.get_workflow_result(workflow_id)
            if result.is_completed:
                print(result.final_result)
        """
        import logging

        from .workflow import WorkflowResult

        logger = logging.getLogger(__name__)

        # Try unified state store first (if configured)
        if self.state_store:
            try:
                result = self.state_store.get_workflow_state(workflow_id)
                if result:
                    logger.debug(
                        f"Retrieved workflow {workflow_id} from unified state store"
                    )
                    return result
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve workflow {workflow_id} from unified store: {e}"
                )

        # Fall back to backend's native persistence
        if self.persistence_config.use_native_persistence:
            try:
                result = self._get_native_workflow_result(workflow_id)
                logger.debug(f"Retrieved workflow {workflow_id} from native persistence")
                return result
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve workflow {workflow_id} from native persistence: {e}"
                )

        # Fallback: Check in-memory storage (current default implementation)
        workflow_results = getattr(self, "_workflow_results", {})
        if workflow_id in workflow_results:
            stored = workflow_results[workflow_id]
            result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name=stored.get("workflow_name", "unknown"),
                status=stored["status"],
                steps_completed=stored.get("steps_completed", 0),
                total_steps=stored.get("total_steps", 0),
            )
            if stored["status"] == "completed":
                result.final_result = stored.get("result")
            elif stored["status"] == "failed":
                result.error = stored.get("error")
            logger.debug(f"Retrieved workflow {workflow_id} from in-memory storage")
            return result

        # Workflow not found anywhere
        logger.warning(f"Workflow {workflow_id} not found in any persistence layer")
        return WorkflowResult(
            workflow_id=workflow_id,
            workflow_name="unknown",
            status="not_found",
            steps_completed=0,
            total_steps=0,
            error="Workflow not found in any persistence layer",
        )

    def _execute_linear_workflow(self, name: str, initial_input: Any) -> str:
        """Execute workflow using new pattern-based execution system.

        This implementation supports sequential, parallel, and mixed patterns
        with fallback to manual execution for backends without native support.
        """
        import uuid

        from .workflow import WorkflowExecutionConfig, WorkflowExecutor

        workflow_def = self._workflows[name]
        workflow_id = f"workflow-{uuid.uuid4()}"

        # Use WorkflowExecutor for pattern-based execution with default timeout config
        config = WorkflowExecutionConfig()
        executor = WorkflowExecutor(self, config)
        try:
            final_result = executor.execute_workflow_patterns(workflow_def, initial_input)

            # Store result using hybrid persistence
            result_data = {
                "status": "completed",
                "result": final_result,
                "workflow_name": workflow_def.name,
                "steps_completed": len(workflow_def.steps),
                "total_steps": len(workflow_def.steps),
            }
            self._store_workflow_result(workflow_id, workflow_def.name, result_data)

            return workflow_id
        except Exception as e:
            # Store error result using hybrid persistence
            error_data = {
                "status": "failed",
                "error": str(e),
                "workflow_name": workflow_def.name,
                "steps_completed": 0,
                "total_steps": len(workflow_def.steps),
            }
            self._store_workflow_result(workflow_id, workflow_def.name, error_data)
            raise

    def _store_workflow_result(
        self, workflow_id: str, workflow_name: str, result_data: dict
    ) -> None:
        """Store workflow result using hybrid persistence approach."""
        import logging

        logger = logging.getLogger(__name__)

        # Store in unified state store (if configured)
        if self.state_store:
            try:
                self.state_store.store_workflow_state(workflow_id, result_data)
                logger.debug(f"Stored workflow {workflow_id} in unified state store")
            except Exception as e:
                logger.error(
                    f"Failed to store workflow {workflow_id} in unified store: {e}"
                )

        # Store in backend's native persistence (if enabled)
        if self.persistence_config.use_native_persistence:
            try:
                self._store_native_workflow_result(
                    workflow_id, workflow_name, result_data
                )
                logger.debug(f"Stored workflow {workflow_id} in native persistence")
            except Exception as e:
                logger.error(
                    f"Failed to store workflow {workflow_id} in native persistence: {e}"
                )

        # Fallback: Store in memory (current default when no persistence configured)
        if not self.state_store and not self.persistence_config.use_native_persistence:
            self._workflow_results = getattr(self, "_workflow_results", {})
            self._workflow_results[workflow_id] = result_data
            logger.debug(f"Stored workflow {workflow_id} in in-memory storage")

    @property
    def backend_type(self) -> str:
        """Get the backend type identifier."""
        return self.__class__.__name__.replace("Backend", "").lower()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type='{self.backend_type}')"


# Decorator function for easier task registration
def task(backend: TaskBackend, name: str | None = None):
    """Decorator for registering tasks with a backend.

    Args:
        backend: TaskBackend instance to register with
        name: Optional task name

    Usage:
        @task(backend)
        def my_task(x, y):
            return x + y
    """

    def decorator(fn: Callable) -> Callable:
        return backend.register_task(fn, name)

    return decorator
