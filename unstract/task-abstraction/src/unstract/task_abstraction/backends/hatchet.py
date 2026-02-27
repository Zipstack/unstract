"""Hatchet backend implementation for task abstraction."""

import logging
from collections.abc import Callable
from typing import Any

try:
    from hatchet_sdk import Hatchet

    HATCHET_AVAILABLE = True
except ImportError:
    HATCHET_AVAILABLE = False

from ..base import TaskBackend
from ..models import BackendConfig, TaskResult

logger = logging.getLogger(__name__)


class HatchetBackend(TaskBackend):
    """Hatchet workflow engine backend implementation.

    This backend maps the TaskBackend interface to Hatchet operations:
    - register_task() → @hatchet.step decorator
    - submit() → workflow trigger with single step
    - get_result() → workflow run status query
    - run_worker() → hatchet worker polling
    """

    def __init__(self, config: BackendConfig | None = None):
        """Initialize Hatchet backend.

        Args:
            config: Backend configuration with Hatchet connection parameters
        """
        if not HATCHET_AVAILABLE:
            raise ImportError("Missing dependency: hatchet-sdk")

        super().__init__()

        if config:
            self.config = config
        else:
            raise ValueError(
                "Hatchet backend requires configuration with token and server_url"
            )

        if not self.config.validate():
            raise ValueError("Invalid Hatchet configuration")

        # Initialize Hatchet client
        self.hatchet = Hatchet(
            token=self.config.connection_params["token"],
            server_url=self.config.connection_params["server_url"],
        )

        # Track workflow definitions for our tasks
        self._workflows: dict[str, Any] = {}

    def register_task(self, fn: Callable, name: str | None = None) -> Callable:
        """Register a function as a Hatchet step within a workflow.

        Args:
            fn: Python function to register as task
            name: Optional task name (defaults to function name)

        Returns:
            The registered function wrapped for Hatchet

        Example:
            @backend.register_task
            def process_data(data):
                return processed_data
        """
        task_name = name or fn.__name__

        # Create a workflow that contains this single task as a step
        @self.hatchet.workflow(name=f"{task_name}_workflow")
        class TaskWorkflow:
            @self.hatchet.step(name=task_name)
            def execute_task(self, context):
                # Extract args and kwargs from context input
                input_data = context.workflow_input()
                args = input_data.get("args", [])
                kwargs = input_data.get("kwargs", {})

                # Call the original function
                return fn(*args, **kwargs)

        # Store the workflow class and original function
        self._tasks[task_name] = fn
        self._workflows[task_name] = TaskWorkflow

        return fn

    def submit(self, name: str, *args, **kwargs) -> str:
        """Submit a task for execution by triggering its workflow.

        Args:
            name: Name of registered task
            *args: Positional arguments for task
            **kwargs: Keyword arguments for task

        Returns:
            Workflow run ID for tracking execution

        Example:
            task_id = backend.submit("process_data", data=my_data)
        """
        if name not in self._tasks:
            raise ValueError(f"Task '{name}' not registered")

        # Prepare input data for the workflow
        input_data = {"args": args, "kwargs": kwargs}

        # Trigger the workflow
        workflow_name = f"{name}_workflow"
        workflow_run = self.hatchet.admin.trigger_workflow(
            workflow_name=workflow_name, input_data=input_data
        )

        return workflow_run.workflow_run_id

    def get_result(self, task_id: str) -> TaskResult:
        """Retrieve the result of a workflow run (task execution).

        Args:
            task_id: Workflow run ID from submit()

        Returns:
            TaskResult with standardized result format

        Example:
            result = backend.get_result(task_id)
            if result.is_completed:
                print(result.result)
        """
        try:
            # Get workflow run details
            workflow_run = self.hatchet.admin.get_workflow_run(task_id)

            # Map Hatchet states to our standard states
            status_mapping = {
                "PENDING": "pending",
                "RUNNING": "running",
                "SUCCEEDED": "completed",
                "FAILED": "failed",
                "CANCELLED": "failed",
            }

            hatchet_status = workflow_run.status
            status = status_mapping.get(hatchet_status, "pending")

            # Extract task name from workflow name (remove _workflow suffix)
            workflow_name = workflow_run.workflow_version.workflow.name
            task_name = (
                workflow_name.replace("_workflow", "")
                if workflow_name.endswith("_workflow")
                else workflow_name
            )

            task_result = TaskResult(
                task_id=task_id,
                task_name=task_name,
                status=status,
            )

            if status == "completed":
                # Get the result from the step output
                steps = workflow_run.steps or []
                if steps:
                    # Find our task step and get its output
                    for step in steps:
                        if step.step_name == task_name:
                            task_result.result = step.output
                            break
            elif status == "failed":
                # Get error information
                if hasattr(workflow_run, "error") and workflow_run.error:
                    task_result.error = workflow_run.error
                else:
                    task_result.error = "Workflow execution failed"

            # Set timing information
            if hasattr(workflow_run, "created_at") and workflow_run.created_at:
                task_result.started_at = workflow_run.created_at
            if hasattr(workflow_run, "finished_at") and workflow_run.finished_at:
                task_result.completed_at = workflow_run.finished_at

            return task_result

        except Exception as e:
            # Return failed result if we can't get workflow info
            return TaskResult(
                task_id=task_id,
                task_name="unknown",
                status="failed",
                error=f"Failed to get result: {str(e)}",
            )

    def run_worker(self) -> None:
        """Start the Hatchet worker process.

        This method blocks and runs the Hatchet worker that will listen
        for workflow triggers and execute registered steps.

        Example:
            backend.run_worker()  # Blocks until shutdown
        """
        # Get worker configuration
        worker_config = self.config.worker_config or {}
        worker_name = worker_config.get("worker_name", "task-abstraction-worker")

        # Start the worker
        # This will block and listen for workflows to execute
        self.hatchet.worker.start(
            worker_name=worker_name, max_runs=worker_config.get("max_runs", 100)
        )

    @property
    def backend_type(self) -> str:
        """Get the backend type identifier."""
        return "hatchet"

    def is_connected(self) -> bool:
        """Check if backend is connected to Hatchet server."""
        try:
            # Try to get tenant info as a connection test
            self.hatchet.admin.get_tenant()
            return True
        except Exception:
            return False

    def submit_workflow(self, name: str, initial_input: Any) -> str:
        """Submit a workflow using Hatchet DAG pattern.

        Args:
            name: Name of registered workflow
            initial_input: Initial input data for workflow

        Returns:
            Workflow execution ID

        This implementation creates a Hatchet workflow with sequential steps
        using parent dependencies to ensure linear execution.
        """
        if name not in self._workflows:
            raise ValueError(f"Workflow '{name}' not registered")

        workflow_def = self._workflows[name]

        try:
            # Create a composite workflow for this execution
            @self.hatchet.workflow(name=f"{name}_execution")
            class SequentialWorkflow:
                def __init__(self):
                    self.steps = {}

                # Create steps dynamically with dependencies
                def create_steps(self):
                    previous_step = None

                    for i, step in enumerate(workflow_def.steps):
                        step_name = f"{step.task_name}_{i}"

                        if step.task_name not in self._tasks:
                            raise ValueError(
                                f"Task '{step.task_name}' not registered in workflow '{name}'"
                            )

                        # Create step with parent dependency for sequential execution
                        if previous_step:
                            parents = [previous_step]
                        else:
                            parents = []

                        # Capture loop variables in closure by using default arguments
                        def create_workflow_step(step_obj, parent_list):
                            @self.hatchet.step(
                                name=step_obj.task_name, parents=parent_list
                            )
                            def workflow_step(context):
                                # Get the original task function
                                task_fn = self._tasks[step_obj.task_name]

                                # Get input from previous step or initial input
                                if parent_list:
                                    # Get output from previous step
                                    workflow_input = context.step_output(parent_list[0])
                                else:
                                    # Use initial workflow input
                                    workflow_input = context.workflow_input()[
                                        "initial_input"
                                    ]

                                # Execute task with input and step kwargs
                                return task_fn(workflow_input, **step_obj.kwargs)

                            return workflow_step

                        workflow_step = create_workflow_step(step, parents)

                        self.steps[step_name] = workflow_step
                        previous_step = step_name

            # Create workflow instance and register steps
            workflow_instance = SequentialWorkflow()
            workflow_instance.create_steps()

            # Trigger the workflow
            workflow_run = self.hatchet.admin.trigger_workflow(
                workflow_name=f"{name}_execution",
                input_data={"initial_input": initial_input},
            )

            return workflow_run.workflow_run_id

        except Exception:
            # Fallback to default sequential execution
            return super().submit_workflow(name, initial_input)

    def get_workflow_result(self, workflow_id: str):
        """Get workflow result for Hatchet execution."""
        try:
            # Get workflow run details
            workflow_run = self.hatchet.admin.get_workflow_run(workflow_id)

            # Map Hatchet status to workflow status
            status_mapping = {
                "PENDING": "pending",
                "RUNNING": "running",
                "SUCCEEDED": "completed",
                "FAILED": "failed",
                "CANCELLED": "failed",
            }

            hatchet_status = workflow_run.status
            status = status_mapping.get(hatchet_status, "pending")

            from ..workflow import WorkflowResult

            # Count completed steps
            steps = workflow_run.steps or []
            completed_steps = len([step for step in steps if step.status == "SUCCEEDED"])
            total_steps = len(steps)

            workflow_result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="hatchet_workflow",
                status=status,
                steps_completed=completed_steps,
                total_steps=total_steps,
            )

            if status == "completed" and steps:
                # Get result from final step
                final_step = steps[-1]
                workflow_result.final_result = final_step.output
            elif status == "failed":
                workflow_result.error = getattr(
                    workflow_run, "error", "Workflow execution failed"
                )

            return workflow_result

        except Exception:
            # Fallback to default implementation
            return super().get_workflow_result(workflow_id)
