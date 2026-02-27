"""Linear workflow implementation for task abstraction.

This module provides sequential task chaining capabilities across all backends.
Workflows define a linear sequence of tasks where the output of one task
becomes the input to the next task.

Example:
    @workflow(backend)
    def data_processing_pipeline():
        return [
            ("extract_data", {"source": "database"}),
            ("transform_data", {}),
            ("validate_data", {}),
            ("load_data", {"target": "warehouse"})
        ]

    workflow_id = backend.submit_workflow("data_processing_pipeline", input_data)
"""

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)
from dataclasses import dataclass

from .dlq import DeadLetterQueue, DLQEntry, create_dlq
from .models import TaskResult


# Custom exceptions for workflow execution
class WorkflowTimeoutError(Exception):
    """Raised when workflow or task exceeds timeout."""

    pass


class WorkflowRetryExhaustedError(Exception):
    """Raised when max retry attempts are exceeded."""

    pass


class BackendCommunicationError(Exception):
    """Raised when backend communication fails."""

    pass


class TaskExecutionError(Exception):
    """Raised when a task execution fails (different from task being lost)."""

    pass


@dataclass
class WorkflowExecutionConfig:
    """Configuration for workflow execution timeouts and retry behavior."""

    task_timeout: int = 300  # 5 minutes per task
    workflow_timeout: int = 1800  # 30 minutes per workflow
    poll_interval_start: float = 1.0  # Start with 1 second polling
    poll_interval_max: float = 30.0  # Max 30 seconds between polls
    max_poll_attempts: int = 1000  # Maximum polling attempts before giving up
    retry_attempts: int = 3  # Retry get_result() calls
    retry_backoff: float = 2.0  # Exponential backoff multiplier

    # Task-level retry configuration
    task_retry_attempts: int = 3  # Retry lost/failed tasks
    task_retry_backoff: float = 5.0  # Wait between task retries
    distinguish_lost_vs_failed: bool = True  # Different handling for lost vs failed tasks

    # Dead Letter Queue configuration
    enable_dlq: bool = True  # Enable Dead Letter Queue for failed tasks
    dlq_type: str = "memory"  # DLQ backend: "memory" or "redis"
    dlq_config: dict[str, Any] | None = None  # DLQ-specific configuration

    def __post_init__(self):
        """Validate configuration values."""
        if self.task_timeout <= 0:
            raise ValueError("task_timeout must be positive")
        if self.workflow_timeout <= 0:
            raise ValueError("workflow_timeout must be positive")
        if self.poll_interval_start <= 0:
            raise ValueError("poll_interval_start must be positive")
        if self.max_poll_attempts <= 0:
            raise ValueError("max_poll_attempts must be positive")
        if self.task_retry_attempts < 0:
            raise ValueError("task_retry_attempts must be non-negative")
        if self.task_retry_backoff <= 0:
            raise ValueError("task_retry_backoff must be positive")


@dataclass
class WorkflowStep:
    """A single step in a workflow."""

    task_name: str
    kwargs: dict[str, Any]

    def __init__(self, task_name: str, kwargs: dict[str, Any] | None = None):
        self.task_name = task_name
        self.kwargs = kwargs or {}


class ExecutionPattern:
    """Base class for workflow execution patterns."""

    pass


class Sequential(ExecutionPattern):
    """Sequential execution pattern - steps run one after another."""

    def __init__(self, steps: list[str | tuple[str, dict]]):
        self.steps = self._normalize_steps(steps)

    def _normalize_steps(self, steps: list[str | tuple[str, dict]]) -> list[WorkflowStep]:
        """Convert step definitions to WorkflowStep objects."""
        workflow_steps = []
        for step in steps:
            if isinstance(step, str):
                workflow_steps.append(WorkflowStep(step))
            elif isinstance(step, tuple) and len(step) == 2:
                task_name, kwargs = step
                workflow_steps.append(WorkflowStep(task_name, kwargs))
            else:
                raise ValueError(f"Invalid step format: {step}")
        return workflow_steps


class Parallel(ExecutionPattern):
    """Parallel execution pattern - steps run simultaneously."""

    def __init__(self, steps: list[str | tuple[str, dict]]):
        self.steps = self._normalize_steps(steps)

    def _normalize_steps(self, steps: list[str | tuple[str, dict]]) -> list[WorkflowStep]:
        """Convert step definitions to WorkflowStep objects."""
        workflow_steps = []
        for step in steps:
            if isinstance(step, str):
                workflow_steps.append(WorkflowStep(step))
            elif isinstance(step, tuple) and len(step) == 2:
                task_name, kwargs = step
                workflow_steps.append(WorkflowStep(task_name, kwargs))
            else:
                raise ValueError(f"Invalid step format: {step}")
        return workflow_steps


@dataclass
class WorkflowDefinition:
    """Definition of a workflow with support for sequential, parallel, and mixed patterns."""

    name: str
    patterns: list[ExecutionPattern]
    description: str | None = None

    @classmethod
    def sequential(
        cls,
        steps: list[str | tuple[str, dict]],
        name: str = "sequential_workflow",
        description: str | None = None,
    ):
        """Create a purely sequential workflow.

        Args:
            steps: List of task names or (task_name, kwargs) tuples
            name: Workflow name
            description: Optional description

        Returns:
            WorkflowDefinition with sequential execution

        Example:
            workflow = WorkflowDefinition.sequential([
                "extract_data",
                ("transform_data", {"format": "json"}),
                "load_data"
            ])
        """
        return cls(name=name, patterns=[Sequential(steps)], description=description)

    @classmethod
    def parallel(
        cls,
        steps: list[str | tuple[str, dict]],
        name: str = "parallel_workflow",
        description: str | None = None,
    ):
        """Create a purely parallel workflow.

        Args:
            steps: List of task names or (task_name, kwargs) tuples
            name: Workflow name
            description: Optional description

        Returns:
            WorkflowDefinition with parallel execution

        Example:
            workflow = WorkflowDefinition.parallel([
                "process_file_1",
                "process_file_2",
                "process_file_3"
            ])
        """
        return cls(name=name, patterns=[Parallel(steps)], description=description)

    @classmethod
    def mixed(
        cls,
        patterns: list[ExecutionPattern],
        name: str = "mixed_workflow",
        description: str | None = None,
    ):
        """Create a mixed workflow with sequential and parallel patterns.

        Args:
            patterns: List of Sequential/Parallel execution patterns
            name: Workflow name
            description: Optional description

        Returns:
            WorkflowDefinition with mixed execution patterns

        Example:
            workflow = WorkflowDefinition.mixed([
                Sequential(["extract", "validate"]),
                Parallel(["process_a", "process_b", "process_c"]),
                Sequential(["aggregate", "report"])
            ])
        """
        return cls(name=name, patterns=patterns, description=description)

    @classmethod
    def from_step_list(
        cls,
        name: str,
        steps: list[str | tuple[str, dict]],
        description: str | None = None,
    ):
        """Create workflow from list of steps (legacy compatibility).

        Args:
            name: Workflow name
            steps: List of steps, each can be:
                   - String (task name only)
                   - Tuple of (task_name, kwargs)
            description: Optional description

        Returns:
            WorkflowDefinition with sequential execution (for backward compatibility)

        Example:
            workflow = WorkflowDefinition.from_step_list("data_pipeline", [
                "extract_data",
                ("transform_data", {"format": "json"}),
                "load_data"
            ])
        """
        return cls.sequential(steps, name, description)

    @property
    def steps(self) -> list[WorkflowStep]:
        """Get all steps in the workflow (flattened).

        Returns:
            List of all WorkflowStep objects in execution order
        """
        all_steps = []
        for pattern in self.patterns:
            if isinstance(pattern, (Sequential, Parallel)):
                all_steps.extend(pattern.steps)
        return all_steps


@dataclass
class WorkflowResult:
    """Result of workflow execution."""

    workflow_id: str
    workflow_name: str
    status: str  # pending, running, completed, failed
    steps_completed: int
    total_steps: int
    current_step: str | None = None
    final_result: Any = None
    error: str | None = None
    step_results: list[TaskResult] | None = None

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def progress_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.steps_completed / self.total_steps) * 100


def workflow(backend, name: str | None = None, description: str | None = None):
    """Decorator for defining linear workflows.

    The decorated function should return a list of workflow steps.
    Each step can be either:
    - A string (task name)
    - A tuple of (task_name, kwargs)

    Args:
        backend: TaskBackend instance to register workflow with
        name: Optional workflow name (defaults to function name)
        description: Optional workflow description

    Example:
        @workflow(backend, description="Data processing pipeline")
        def process_user_data():
            return [
                ("validate_input", {"strict": True}),
                "normalize_data",
                ("enrich_data", {"source": "external_api"}),
                "save_results"
            ]
    """

    def decorator(fn: Callable) -> Callable:
        workflow_name = name or fn.__name__

        # Execute the function to get the step list
        steps = fn()

        # Create workflow definition
        workflow_def = WorkflowDefinition.from_step_list(
            name=workflow_name, steps=steps, description=description
        )

        # Register workflow with backend
        backend.register_workflow(workflow_def)

        # Return original function for potential direct calls
        return fn

    return decorator


class WorkflowExecutor:
    """Executes workflows across different backends with proper timeout and retry handling."""

    def __init__(self, backend, config: WorkflowExecutionConfig | None = None):
        self.backend = backend
        self.config = config or WorkflowExecutionConfig()

        # Initialize Dead Letter Queue if enabled
        self.dlq: DeadLetterQueue | None = None
        if self.config.enable_dlq:
            try:
                self.dlq = create_dlq(self.config.dlq_type, self.config.dlq_config)
                logger.info(f"Dead Letter Queue initialized: {self.config.dlq_type}")
            except Exception as e:
                logger.error(f"Failed to initialize DLQ: {e}")
                self.dlq = None

    def execute_workflow(
        self, workflow_def: WorkflowDefinition, initial_input: Any
    ) -> str:
        """Execute a workflow definition.

        Args:
            workflow_def: WorkflowDefinition to execute
            initial_input: Initial input data for the workflow

        Returns:
            Workflow execution ID
        """
        # Delegate to backend-specific workflow execution
        return self.backend.submit_workflow(workflow_def.name, initial_input)

    def get_workflow_result(self, workflow_id: str) -> WorkflowResult:
        """Get workflow execution result.

        Args:
            workflow_id: Workflow execution ID

        Returns:
            WorkflowResult with current status and results
        """
        return self.backend.get_workflow_result(workflow_id)

    def _get_result_with_retry(self, task_id: str) -> "TaskResult":
        """Get task result with retry logic and exponential backoff.

        Args:
            task_id: Task ID to get result for

        Returns:
            TaskResult from backend

        Raises:
            WorkflowRetryExhaustedError: If all retry attempts fail
            BackendCommunicationError: If backend is unreachable
        """
        last_exception = None

        for attempt in range(self.config.retry_attempts):
            try:
                result = self.backend.get_result(task_id)
                return result
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"get_result attempt {attempt + 1}/{self.config.retry_attempts} failed for task {task_id}: {e}"
                )

                if attempt < self.config.retry_attempts - 1:
                    # Wait before retry with exponential backoff
                    wait_time = self.config.poll_interval_start * (
                        self.config.retry_backoff**attempt
                    )
                    time.sleep(min(wait_time, self.config.poll_interval_max))

        # All retries exhausted
        raise WorkflowRetryExhaustedError(
            f"Failed to get result for task {task_id} after {self.config.retry_attempts} attempts: {last_exception}"
        )

    def _poll_for_completion(self, task_id: str, timeout: int) -> "TaskResult":
        """Poll for task completion with timeout and exponential backoff.

        Args:
            task_id: Task ID to poll
            timeout: Maximum time to wait in seconds

        Returns:
            TaskResult when task completes

        Raises:
            WorkflowTimeoutError: If task exceeds timeout or max polling attempts
        """
        start_time = time.time()
        poll_interval = self.config.poll_interval_start
        attempts = 0

        logger.info(f"Polling for task {task_id} completion (timeout: {timeout}s)")

        while attempts < self.config.max_poll_attempts:
            # Check overall timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise WorkflowTimeoutError(
                    f"Task {task_id} timed out after {elapsed:.1f}s (limit: {timeout}s)"
                )

            # Get result with retry logic
            try:
                result = self._get_result_with_retry(task_id)

                if result.status == "completed":
                    logger.info(
                        f"Task {task_id} completed successfully after {elapsed:.1f}s"
                    )
                    return result
                elif result.status == "failed":
                    logger.error(
                        f"Task {task_id} failed after {elapsed:.1f}s: {result.error}"
                    )
                    return result

                # Task still running, continue polling
                logger.debug(
                    f"Task {task_id} still running (attempt {attempts + 1}, elapsed: {elapsed:.1f}s)"
                )

            except WorkflowRetryExhaustedError as e:
                # Backend communication failed completely
                raise BackendCommunicationError(
                    f"Cannot communicate with backend for task {task_id}: {e}"
                ) from e

            # Wait before next poll with exponential backoff
            time.sleep(poll_interval)
            poll_interval = min(
                poll_interval * self.config.retry_backoff, self.config.poll_interval_max
            )
            attempts += 1

        # Max attempts reached
        elapsed = time.time() - start_time
        raise WorkflowTimeoutError(
            f"Task {task_id} exceeded max polling attempts ({attempts}) after {elapsed:.1f}s"
        )

    def _execute_task_with_retry(self, task_name: str, *args, **kwargs) -> Any:
        """Execute a task with retry logic for lost/failed tasks.

        Args:
            task_name: Name of the task to execute
            *args: Positional arguments for the task
            **kwargs: Keyword arguments for the task

        Returns:
            Task result if successful

        Raises:
            TaskExecutionError: If task execution fails (non-retryable)
            WorkflowTimeoutError: If task is lost after all retry attempts
        """
        last_exception = None

        for attempt in range(
            self.config.task_retry_attempts + 1
        ):  # +1 for initial attempt
            try:
                logger.info(
                    f"Executing task '{task_name}' (attempt {attempt + 1}/{self.config.task_retry_attempts + 1})"
                )

                # Submit the task
                task_id = self.backend.submit(task_name, *args, **kwargs)
                logger.debug(f"Task '{task_name}' submitted with ID: {task_id}")

                # Poll for completion with timeout
                result = self._poll_for_completion(task_id, self.config.task_timeout)

                if result.status == "completed":
                    if attempt > 0:
                        logger.info(
                            f"Task '{task_name}' succeeded on retry attempt {attempt + 1}"
                        )
                    return result.result

                elif result.status == "failed":
                    # Task executed but failed - decide whether to retry based on configuration
                    if self.config.distinguish_lost_vs_failed:
                        # Don't retry failed executions, only lost tasks
                        error_msg = f"Task '{task_name}' failed: {result.error}"
                        logger.error(error_msg)

                        # Add failed task to DLQ
                        if self.dlq:
                            try:
                                dlq_entry = DLQEntry.create(
                                    task_name=task_name,
                                    task_args=list(args),
                                    task_kwargs=kwargs,
                                    failure_reason=result.error or error_msg,
                                    failure_type="execution_error",
                                    attempts_made=attempt + 1,
                                    backend_type=type(self.backend).__name__,
                                    original_task_id=task_id,
                                )
                                self.dlq.add_failed_task(dlq_entry)
                                logger.error(
                                    f"Failed task '{task_name}' added to DLQ: {dlq_entry.dlq_id}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to add task '{task_name}' to DLQ: {e}"
                                )

                        raise TaskExecutionError(error_msg)
                    else:
                        # Treat failed tasks as retryable
                        last_exception = TaskExecutionError(
                            f"Task '{task_name}' failed: {result.error}"
                        )
                        logger.warning(
                            f"Task '{task_name}' failed on attempt {attempt + 1}, will retry if attempts remain"
                        )

            except (WorkflowTimeoutError, BackendCommunicationError) as e:
                # Task was likely lost or backend communication failed - retry
                last_exception = e
                logger.warning(
                    f"Task '{task_name}' lost/unreachable on attempt {attempt + 1}: {e}"
                )

            except TaskExecutionError:
                # Task execution error - don't retry unless configured to
                raise

            # Wait before retry (if not the last attempt)
            if attempt < self.config.task_retry_attempts:
                wait_time = self.config.task_retry_backoff * (attempt + 1)
                logger.info(f"Waiting {wait_time}s before retrying task '{task_name}'...")
                time.sleep(wait_time)

        # All retry attempts exhausted - add to DLQ before raising
        failure_type = (
            "execution_error"
            if isinstance(last_exception, TaskExecutionError)
            else "timeout"
        )
        failure_reason = str(last_exception)

        if self.dlq:
            try:
                dlq_entry = DLQEntry.create(
                    task_name=task_name,
                    task_args=list(args),
                    task_kwargs=kwargs,
                    failure_reason=failure_reason,
                    failure_type=failure_type,
                    attempts_made=self.config.task_retry_attempts + 1,
                    backend_type=type(self.backend).__name__,
                )
                self.dlq.add_failed_task(dlq_entry)
                logger.error(
                    f"Task '{task_name}' added to DLQ after {self.config.task_retry_attempts + 1} attempts: {dlq_entry.dlq_id}"
                )
            except Exception as e:
                logger.error(f"Failed to add task '{task_name}' to DLQ: {e}")

        if isinstance(last_exception, TaskExecutionError):
            raise last_exception
        else:
            raise WorkflowTimeoutError(
                f"Task '{task_name}' lost after {self.config.task_retry_attempts + 1} attempts: {last_exception}"
            )

    def execute_workflow_patterns(
        self, workflow_def: WorkflowDefinition, initial_input: Any
    ) -> Any:
        """Execute workflow with support for sequential, parallel, and mixed patterns.

        Args:
            workflow_def: WorkflowDefinition containing execution patterns
            initial_input: Initial input data

        Returns:
            Final result after executing all patterns

        Raises:
            WorkflowTimeoutError: If workflow exceeds timeout
            Exception: If any step fails
        """
        workflow_start_time = time.time()
        logger.info(
            f"Executing workflow '{workflow_def.name}' with {len(workflow_def.patterns)} pattern(s) (timeout: {self.config.workflow_timeout}s)"
        )
        current_input = initial_input

        for i, pattern in enumerate(workflow_def.patterns):
            # Check workflow-level timeout
            elapsed = time.time() - workflow_start_time
            if elapsed > self.config.workflow_timeout:
                raise WorkflowTimeoutError(
                    f"Workflow '{workflow_def.name}' exceeded timeout ({self.config.workflow_timeout}s) at pattern {i+1}"
                )

            logger.info(
                f"Pattern {i+1}/{len(workflow_def.patterns)}: Executing {type(pattern).__name__}"
            )

            if isinstance(pattern, Sequential):
                current_input = self._execute_sequential_pattern(pattern, current_input)
            elif isinstance(pattern, Parallel):
                current_input = self._execute_parallel_pattern(pattern, current_input)
            else:
                raise ValueError(f"Unsupported execution pattern: {type(pattern)}")

        elapsed = time.time() - workflow_start_time
        logger.info(
            f"Workflow '{workflow_def.name}' execution completed successfully in {elapsed:.1f}s"
        )
        return current_input

    def _execute_sequential_pattern(self, pattern: Sequential, input_data: Any) -> Any:
        """Execute sequential pattern - steps run one after another."""
        logger.info(f"Executing sequential pattern with {len(pattern.steps)} steps")
        current_input = input_data

        for i, step in enumerate(pattern.steps):
            logger.info(
                f"Sequential step {i+1}/{len(pattern.steps)}: Executing task '{step.task_name}'"
            )

            # Execute task with retry logic
            try:
                # Handle task arguments based on whether we have kwargs and input
                if step.kwargs and current_input is None:
                    # First task with kwargs - use kwargs directly
                    current_input = self._execute_task_with_retry(
                        step.task_name, **step.kwargs
                    )
                elif step.kwargs:
                    # Subsequent task with kwargs - merge current_input and kwargs
                    current_input = self._execute_task_with_retry(
                        step.task_name, current_input, **step.kwargs
                    )
                else:
                    # Task without kwargs - pass current_input as positional arg
                    current_input = self._execute_task_with_retry(
                        step.task_name, current_input
                    )

                logger.info(
                    f"Sequential step {i+1}/{len(pattern.steps)}: Task '{step.task_name}' completed successfully"
                )

            except (TaskExecutionError, WorkflowTimeoutError) as e:
                error_msg = f"Sequential step {i+1}/{len(pattern.steps)}: Task '{step.task_name}' failed: {e}"
                logger.error(error_msg)
                raise Exception(error_msg) from e

        logger.info("Sequential pattern execution completed successfully")
        return current_input

    def _execute_parallel_pattern(self, pattern: Parallel, input_data: Any) -> list[Any]:
        """Execute parallel pattern - steps run simultaneously.

        Note: This is the fallback implementation. Backends with native
        parallel support should override this method.
        """
        logger.info(
            f"Executing parallel pattern with {len(pattern.steps)} steps (fallback implementation)"
        )

        # Submit all tasks simultaneously
        task_submissions = []
        for i, step in enumerate(pattern.steps):
            logger.info(
                f"Parallel step {i+1}/{len(pattern.steps)}: Submitting task '{step.task_name}'"
            )

            # Handle task arguments based on whether we have kwargs and input
            if step.kwargs and input_data is None:
                # Task with kwargs and no input - use kwargs directly
                task_id = self.backend.submit(step.task_name, **step.kwargs)
            elif step.kwargs:
                # Task with kwargs and input - merge input_data and kwargs
                task_id = self.backend.submit(step.task_name, input_data, **step.kwargs)
            else:
                # Task without kwargs - pass input_data as positional arg
                task_id = self.backend.submit(step.task_name, input_data)

            task_submissions.append((task_id, step.task_name))
            logger.debug(f"Task '{step.task_name}' submitted with ID: {task_id}")

        # Execute all tasks with retry logic in parallel
        logger.info(
            f"Executing {len(pattern.steps)} parallel tasks with retry support..."
        )

        results = []
        for i, step in enumerate(pattern.steps):
            try:
                logger.info(
                    f"Parallel step {i+1}/{len(pattern.steps)}: Executing task '{step.task_name}'"
                )

                # Execute task with retry logic
                if step.kwargs and input_data is None:
                    # Task with kwargs and no input - use kwargs directly
                    result = self._execute_task_with_retry(step.task_name, **step.kwargs)
                elif step.kwargs:
                    # Task with kwargs and input - merge input_data and kwargs
                    result = self._execute_task_with_retry(
                        step.task_name, input_data, **step.kwargs
                    )
                else:
                    # Task without kwargs - pass input_data as positional arg
                    result = self._execute_task_with_retry(step.task_name, input_data)

                results.append(result)
                logger.info(f"Parallel task '{step.task_name}' completed successfully")

            except (TaskExecutionError, WorkflowTimeoutError) as e:
                error_msg = f"Parallel task '{step.task_name}' failed: {e}"
                logger.error(error_msg)
                raise Exception(error_msg) from e

        logger.info("Parallel pattern execution completed successfully")
        return results

    def execute_linear_sequence(
        self, steps: list[WorkflowStep], initial_input: Any
    ) -> Any:
        """Execute workflow steps sequentially (legacy compatibility).

        Args:
            steps: List of WorkflowStep objects to execute in sequence
            initial_input: Initial input data for the first step

        Returns:
            Final result from the last step

        Raises:
            Exception: If any step fails
        """
        # Convert to new pattern-based execution
        sequential_pattern = Sequential([])
        sequential_pattern.steps = steps
        return self._execute_sequential_pattern(sequential_pattern, initial_input)

    # Dead Letter Queue Methods

    def get_dlq_stats(self) -> dict[str, Any]:
        """Get Dead Letter Queue statistics.

        Returns:
            Dictionary with DLQ statistics including total entries, failure types, etc.
        """
        if not self.dlq:
            return {"error": "DLQ not enabled"}
        return self.dlq.get_stats()

    def list_dlq_entries(
        self,
        limit: int | None = None,
        failure_type: str | None = None,
        workflow_id: str | None = None,
    ) -> list[DLQEntry]:
        """List entries in the Dead Letter Queue.

        Args:
            limit: Maximum number of entries to return
            failure_type: Filter by failure type ('execution_error', 'timeout', 'communication_error')
            workflow_id: Filter by workflow ID

        Returns:
            List of DLQ entries matching the criteria
        """
        if not self.dlq:
            return []
        return self.dlq.list_entries(limit, failure_type, workflow_id)

    def get_dlq_entry(self, dlq_id: str) -> DLQEntry | None:
        """Get a specific DLQ entry by ID.

        Args:
            dlq_id: DLQ entry ID

        Returns:
            DLQ entry if found, None otherwise
        """
        if not self.dlq:
            return None
        return self.dlq.get_entry(dlq_id)

    def retry_from_dlq(self, dlq_id: str) -> Any:
        """Retry a task from the Dead Letter Queue.

        Args:
            dlq_id: DLQ entry ID to retry

        Returns:
            Task result if successful

        Raises:
            ValueError: If DLQ entry not found or not retryable
            TaskExecutionError: If retry fails
        """
        if not self.dlq:
            raise ValueError("DLQ not enabled")

        dlq_entry = self.dlq.get_entry(dlq_id)
        if not dlq_entry:
            raise ValueError(f"DLQ entry not found: {dlq_id}")

        if not dlq_entry.is_retryable:
            raise ValueError(
                f"DLQ entry {dlq_id} is not retryable (failure_type: {dlq_entry.failure_type})"
            )

        logger.info(f"Retrying task '{dlq_entry.task_name}' from DLQ: {dlq_id}")

        try:
            # Execute the task with retry logic
            result = self._execute_task_with_retry(
                dlq_entry.task_name, *dlq_entry.task_args, **dlq_entry.task_kwargs
            )

            # Remove from DLQ on success
            self.dlq.remove_entry(dlq_id)
            logger.info(
                f"Task '{dlq_entry.task_name}' successfully retried from DLQ: {dlq_id}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to retry task '{dlq_entry.task_name}' from DLQ {dlq_id}: {e}"
            )
            raise

    def remove_dlq_entry(self, dlq_id: str) -> bool:
        """Remove an entry from the Dead Letter Queue.

        Args:
            dlq_id: DLQ entry ID to remove

        Returns:
            True if removed, False if not found
        """
        if not self.dlq:
            return False
        return self.dlq.remove_entry(dlq_id)

    def cleanup_old_dlq_entries(self, max_age_seconds: int = 86400) -> int:
        """Clean up old DLQ entries.

        Args:
            max_age_seconds: Maximum age in seconds (default: 24 hours)

        Returns:
            Number of entries removed
        """
        if not self.dlq:
            return 0
        return self.dlq.cleanup_old_entries(max_age_seconds)


# Convenience function for workflow registration
def register_workflow(
    backend,
    steps: list[str | tuple[str, dict]],
    name: str,
    description: str | None = None,
):
    """Register a workflow from a step list.

    This is a convenience function for registering workflows without using the decorator.

    Args:
        backend: TaskBackend instance
        steps: List of workflow steps
        name: Workflow name
        description: Optional description
    """
    workflow_def = WorkflowDefinition.from_step_list(name, steps, description)
    backend.register_workflow(workflow_def)


# Export key classes and exceptions for external use
__all__ = [
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowResult",
    "WorkflowExecutor",
    "WorkflowExecutionConfig",
    "Sequential",
    "Parallel",
    "ExecutionPattern",
    "WorkflowTimeoutError",
    "WorkflowRetryExhaustedError",
    "BackendCommunicationError",
    "TaskExecutionError",
    "workflow",
    "register_workflow",
]
