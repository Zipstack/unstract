"""Workflow patterns for task abstraction.

This module provides simple workflow orchestration patterns across all backends.
Focus is on clean API and delegation to backend-native resilience features.

Example:
    @workflow(backend)
    def data_processing_pipeline():
        return [
            ("extract_data", {"source": "database"}),
            ("transform_data", {}),
            ("load_data", {"target": "warehouse"})
        ]

    workflow_id = backend.submit_workflow("data_processing_pipeline", input_data)
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
        sequential_pattern = Sequential(steps)
        return cls(name=name, patterns=[sequential_pattern], description=description)

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
                ("process_file_1", {}),
                ("process_file_2", {}),
                ("process_file_3", {})
            ])
        """
        parallel_pattern = Parallel(steps)
        return cls(name=name, patterns=[parallel_pattern], description=description)

    @classmethod
    def mixed(
        cls,
        patterns: list[ExecutionPattern],
        name: str = "mixed_workflow",
        description: str | None = None,
    ):
        """Create a mixed workflow with sequential and parallel patterns.

        Args:
            patterns: List of ExecutionPattern objects
            name: Workflow name
            description: Optional description

        Returns:
            WorkflowDefinition with mixed execution patterns

        Example:
            workflow = WorkflowDefinition.mixed([
                Sequential([("validate_input", {})]),
                Parallel([("process_a", {}), ("process_b", {})]),
                Sequential([("aggregate_results", {})])
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
        """Create workflow from list of steps (sequential).

        Args:
            name: Workflow name
            steps: List of workflow steps
            description: Optional description

        Returns:
            WorkflowDefinition with sequential execution
        """
        return cls.sequential(steps, name, description)

    @property
    def steps(self) -> list[WorkflowStep]:
        """Get all workflow steps as a flat list."""
        all_steps = []
        for pattern in self.patterns:
            if hasattr(pattern, "steps"):
                all_steps.extend(pattern.steps)
        return all_steps


class WorkflowExecutor:
    """Executes workflows across different backends using backend-native resilience."""

    def __init__(self, backend):
        self.backend = backend

    def execute_workflow(
        self, workflow_def: WorkflowDefinition, initial_input: Any
    ) -> str:
        """Execute a workflow definition.

        Args:
            workflow_def: WorkflowDefinition to execute
            initial_input: Initial input data for the workflow

        Returns:
            Workflow execution ID

        Note:
            Resilience (retries, DLQ, persistence) is handled by the backend.
            Configure these features in your Celery/Temporal/Hatchet setup.
        """
        return self.backend.submit_workflow(workflow_def.name, initial_input)

    def execute_workflow_patterns(
        self, workflow_def: WorkflowDefinition, initial_input: Any
    ) -> Any:
        """Execute workflow with support for sequential, parallel, and mixed patterns.

        Args:
            workflow_def: WorkflowDefinition containing execution patterns
            initial_input: Initial input data

        Returns:
            Final result after executing all patterns

        Note:
            Backend handles all resilience. Configure retries/DLQ in your
            Celery/Temporal/Hatchet configuration.
        """
        current_input = initial_input

        for pattern in workflow_def.patterns:
            if isinstance(pattern, Sequential):
                current_input = self._execute_sequential_pattern(pattern, current_input)
            elif isinstance(pattern, Parallel):
                current_input = self._execute_parallel_pattern(pattern, current_input)
            else:
                raise ValueError(f"Unknown pattern type: {type(pattern)}")

        return current_input

    def _execute_sequential_pattern(self, pattern: Sequential, input_data: Any) -> Any:
        """Execute a sequential pattern.

        Args:
            pattern: Sequential pattern to execute
            input_data: Input data for the first task

        Returns:
            Result from the last task in the sequence
        """
        current_result = input_data

        for i, step in enumerate(pattern.steps):
            # Submit task to backend
            if i == 0 and step.kwargs:
                # First task with explicit kwargs - don't pass current_result as positional
                task_id = self.backend.submit(step.task_name, **step.kwargs)
            elif step.kwargs:
                # Task with explicit kwargs - pass current_result as first argument
                task_id = self.backend.submit(
                    step.task_name, current_result, **step.kwargs
                )
            else:
                # Task without kwargs - pass current_result as only argument
                task_id = self.backend.submit(step.task_name, current_result)

            # Get result (backend handles retries/timeouts)
            result = self.backend.get_result(task_id)

            if result.status == "completed":
                current_result = result.result
            else:
                # Backend should handle retry logic
                raise Exception(f"Task {step.task_name} failed: {result.error}")

        return current_result

    def _execute_parallel_pattern(self, pattern: Parallel, input_data: Any) -> list[Any]:
        """Execute a parallel pattern.

        Args:
            pattern: Parallel pattern to execute
            input_data: Input data for all parallel tasks

        Returns:
            List of results from all parallel tasks
        """
        # Submit all tasks in parallel
        task_ids = []
        for step in pattern.steps:
            if step.kwargs:
                # Task with explicit kwargs - pass input_data as first argument
                task_id = self.backend.submit(step.task_name, input_data, **step.kwargs)
            else:
                # Task without kwargs - pass input_data as only argument
                task_id = self.backend.submit(step.task_name, input_data)
            task_ids.append(task_id)

        # Collect results
        results = []
        for task_id in task_ids:
            result = self.backend.get_result(task_id)
            if result.status == "completed":
                results.append(result.result)
            else:
                # Backend should handle retry logic
                raise Exception(f"Parallel task {task_id} failed: {result.error}")

        return results


def workflow(backend, name: str | None = None, description: str | None = None):
    """Decorator for defining workflows.

    Args:
        backend: Task backend instance
        name: Optional workflow name (defaults to function name)
        description: Optional workflow description

    Returns:
        Decorated function that registers the workflow

    Example:
        @workflow(backend, name="data_pipeline")
        def process_user_data():
            return [
                ("extract_user_data", {}),
                ("validate_data", {}),
                ("store_results", {})
            ]
    """

    def decorator(fn: Callable) -> Callable:
        workflow_name = name or fn.__name__

        # Execute function to get workflow steps
        steps = fn()

        # Create and register workflow definition
        workflow_def = WorkflowDefinition.from_step_list(
            workflow_name, steps, description
        )
        backend.register_workflow(workflow_def)

        logger.info(f"Registered workflow: {workflow_name}")
        return fn

    return decorator


def register_workflow(
    backend,
    steps: list[str | tuple[str, dict]],
    name: str,
    description: str | None = None,
):
    """Register a workflow from a step list.

    Args:
        backend: TaskBackend instance
        steps: List of workflow steps
        name: Workflow name
        description: Optional description

    Note:
        Resilience features (retries, DLQ, persistence) should be configured
        in your backend (Celery/Temporal/Hatchet) configuration.
    """
    workflow_def = WorkflowDefinition.from_step_list(name, steps, description)
    backend.register_workflow(workflow_def)


# Export key classes for external use
__all__ = [
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowExecutor",
    "Sequential",
    "Parallel",
    "ExecutionPattern",
    "workflow",
    "register_workflow",
]
