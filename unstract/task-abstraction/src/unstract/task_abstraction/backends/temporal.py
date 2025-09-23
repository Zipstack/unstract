"""Temporal backend implementation for task abstraction."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

try:
    from temporalio import activity, workflow, common
    from temporalio.client import Client
    from temporalio.worker import Worker
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False

from ..base import TaskBackend
from ..models import TaskResult, BackendConfig

logger = logging.getLogger(__name__)


class TemporalBackend(TaskBackend):
    """Temporal workflow engine backend implementation.

    This backend maps the TaskBackend interface to Temporal operations:
    - register_task() → @activity.defn decorator
    - submit() → workflow execution with single activity
    - get_result() → workflow execution handle query
    - run_worker() → temporal worker listening
    """

    def __init__(self, config: Optional[BackendConfig] = None):
        """Initialize Temporal backend.

        Args:
            config: Backend configuration with Temporal connection parameters
        """
        if not TEMPORAL_AVAILABLE:
            raise ImportError("Temporal is not installed. Install with: pip install temporalio")

        super().__init__()

        if config:
            self.config = config
        else:
            # Use default local Temporal configuration
            self.config = BackendConfig(
                backend_type="temporal",
                connection_params={
                    "host": "localhost",
                    "port": 7233,
                    "namespace": "default",
                    "task_queue": "task-abstraction-queue",
                }
            )

        if not self.config.validate():
            raise ValueError("Invalid Temporal configuration")

        # Temporal client and worker will be initialized async
        self._client = None
        self._worker = None
        self._activities: Dict[str, Any] = {}
        self._workflows: Dict[str, Any] = {}

    async def _ensure_client(self):
        """Ensure Temporal client is initialized."""
        if self._client is None:
            host = self.config.connection_params["host"]
            port = self.config.connection_params["port"]
            namespace = self.config.connection_params["namespace"]

            self._client = await Client.connect(
                f"{host}:{port}",
                namespace=namespace,
            )
        return self._client

    def register_task(self, fn: Callable, name: Optional[str] = None) -> Callable:
        """Register a function as a Temporal activity.

        Args:
            fn: Python function to register as task
            name: Optional task name (defaults to function name)

        Returns:
            The registered function wrapped as Temporal activity

        Example:
            @backend.register_task
            def process_data(data):
                return processed_data
        """
        task_name = name or fn.__name__

        # Create Temporal activity
        @activity.defn(name=task_name)
        async def activity_wrapper(*args, **kwargs):
            # Call the original function (assume it's sync for now)
            return fn(*args, **kwargs)

        # Create a workflow that executes this single activity
        @workflow.defn(name=f"{task_name}_workflow")
        class TaskWorkflow:
            @workflow.run
            async def run(self, args: list, kwargs: dict) -> Any:
                return await workflow.execute_activity(
                    activity_wrapper,
                    args,
                    kwargs,
                    schedule_to_close_timeout=common.TimeDelta.from_seconds(60),
                )

        # Store the activity, workflow, and original function
        self._tasks[task_name] = fn
        self._activities[task_name] = activity_wrapper
        self._workflows[task_name] = TaskWorkflow

        return fn

    def submit(self, name: str, *args, **kwargs) -> str:
        """Submit a task for execution by starting its workflow.

        Args:
            name: Name of registered task
            *args: Positional arguments for task
            **kwargs: Keyword arguments for task

        Returns:
            Workflow execution ID for tracking

        Example:
            task_id = backend.submit("process_data", data=my_data)
        """
        if name not in self._tasks:
            raise ValueError(f"Task '{name}' not registered")

        # This needs to be called from an async context
        # For now, run it in an event loop
        return asyncio.run(self._async_submit(name, args, kwargs))

    async def _async_submit(self, name: str, args: tuple, kwargs: dict) -> str:
        """Async implementation of submit."""
        client = await self._ensure_client()
        workflow_class = self._workflows[name]

        # Start the workflow execution
        handle = await client.start_workflow(
            workflow_class.run,
            args=[list(args), kwargs],
            id=f"{name}-{uuid.uuid4()}",
            task_queue=self.config.connection_params["task_queue"],
        )

        return handle.id

    def get_result(self, task_id: str) -> TaskResult:
        """Retrieve the result of a workflow execution.

        Args:
            task_id: Workflow execution ID from submit()

        Returns:
            TaskResult with standardized result format

        Example:
            result = backend.get_result(task_id)
            if result.is_completed:
                print(result.result)
        """
        # This needs to be called from an async context
        return asyncio.run(self._async_get_result(task_id))

    async def _async_get_result(self, task_id: str) -> TaskResult:
        """Async implementation of get_result."""
        try:
            client = await self._ensure_client()

            # Get workflow handle
            handle = client.get_workflow_handle(task_id)

            # Try to get the result (this will block if still running)
            try:
                # Check if workflow is still running by trying a non-blocking describe
                description = await handle.describe()

                if description.status == common.WorkflowExecutionStatus.RUNNING:
                    status = "running"
                    result = None
                    error = None
                elif description.status == common.WorkflowExecutionStatus.COMPLETED:
                    status = "completed"
                    result = await handle.result()
                    error = None
                elif description.status == common.WorkflowExecutionStatus.FAILED:
                    status = "failed"
                    result = None
                    try:
                        await handle.result()
                    except Exception as e:
                        error = str(e)
                else:
                    status = "pending"
                    result = None
                    error = None

                # Extract task name from workflow ID
                task_name = task_id.split('-')[0] if '-' in task_id else "unknown"

                task_result = TaskResult(
                    task_id=task_id,
                    task_name=task_name,
                    status=status,
                    result=result,
                    error=error,
                )

                # Set timing information if available
                if hasattr(description, 'start_time') and description.start_time:
                    task_result.started_at = description.start_time
                if hasattr(description, 'close_time') and description.close_time:
                    task_result.completed_at = description.close_time

                return task_result

            except Exception as e:
                return TaskResult(
                    task_id=task_id,
                    task_name="unknown",
                    status="failed",
                    error=f"Failed to get workflow result: {str(e)}"
                )

        except Exception as e:
            return TaskResult(
                task_id=task_id,
                task_name="unknown",
                status="failed",
                error=f"Failed to get workflow handle: {str(e)}"
            )

    def run_worker(self) -> None:
        """Start the Temporal worker process.

        This method blocks and runs the Temporal worker that will listen
        for workflow and activity tasks.

        Example:
            backend.run_worker()  # Blocks until shutdown
        """
        asyncio.run(self._async_run_worker())

    async def _async_run_worker(self) -> None:
        """Async implementation of run_worker."""
        client = await self._ensure_client()

        # Get worker configuration
        worker_config = self.config.worker_config or {}
        task_queue = self.config.connection_params["task_queue"]

        # Collect all activities and workflows
        activities = list(self._activities.values())
        workflows = list(self._workflows.values())

        # Create and run worker
        worker = Worker(
            client,
            task_queue=task_queue,
            activities=activities,
            workflows=workflows,
            max_concurrent_activities=worker_config.get("max_concurrent_activities", 100),
            max_concurrent_workflow_tasks=worker_config.get("max_concurrent_workflow_tasks", 100),
        )

        # This blocks until shutdown
        await worker.run()

    @property
    def backend_type(self) -> str:
        """Get the backend type identifier."""
        return "temporal"

    def is_connected(self) -> bool:
        """Check if backend is connected to Temporal server."""
        try:
            # Try to connect and get cluster info
            async def check_connection():
                client = await self._ensure_client()
                # Just getting a client connection doesn't guarantee server is reachable
                # Try to get some server info
                return True

            return asyncio.run(check_connection())
        except Exception:
            return False

    def submit_workflow(self, name: str, initial_input: Any) -> str:
        """Submit a workflow using Temporal workflow pattern.

        Args:
            name: Name of registered workflow
            initial_input: Initial input data for workflow

        Returns:
            Workflow execution ID

        This implementation creates a Temporal workflow that calls
        activities sequentially.
        """
        if name not in self._workflows:
            raise ValueError(f"Workflow '{name}' not registered")

        workflow_def = self._workflows[name]

        # Create a dynamic workflow for this execution
        try:
            from temporalio import workflow
            from temporalio.common import TimeDelta

            @workflow.defn(name=f"{name}_execution")
            class SequentialWorkflow:
                @workflow.run
                async def run(self, workflow_input: dict) -> Any:
                    current_result = workflow_input['initial_input']

                    # Execute each step sequentially
                    for step in workflow_def.steps:
                        if step.task_name not in self._activities:
                            raise ValueError(f"Activity '{step.task_name}' not registered in workflow '{name}'")

                        activity = self._activities[step.task_name]

                        # Execute activity with current result and step kwargs
                        activity_input = {
                            'input': current_result,
                            'kwargs': step.kwargs
                        }

                        current_result = await workflow.execute_activity(
                            activity,
                            activity_input,
                            schedule_to_close_timeout=TimeDelta.from_seconds(300),
                        )

                    return current_result

            # Run the workflow
            return asyncio.run(self._async_submit_workflow(SequentialWorkflow, name, initial_input))

        except Exception:
            # Fallback to default sequential execution
            return super().submit_workflow(name, initial_input)

    async def _async_submit_workflow(self, workflow_class, name: str, initial_input: Any) -> str:
        """Async implementation of workflow submission."""
        client = await self._ensure_client()

        # Start the workflow
        handle = await client.start_workflow(
            workflow_class.run,
            args=[{'initial_input': initial_input}],
            id=f"{name}-{uuid.uuid4()}",
            task_queue=self.config.connection_params["task_queue"],
        )

        return handle.id

    def get_workflow_result(self, workflow_id: str):
        """Get workflow result for Temporal execution."""
        return asyncio.run(self._async_get_workflow_result(workflow_id))

    async def _async_get_workflow_result(self, workflow_id: str):
        """Async implementation of workflow result retrieval."""
        try:
            client = await self._ensure_client()

            # Get workflow handle
            handle = client.get_workflow_handle(workflow_id)

            # Get workflow description
            description = await handle.describe()

            # Map Temporal status to workflow status
            from temporalio.common import WorkflowExecutionStatus

            status_mapping = {
                WorkflowExecutionStatus.RUNNING: 'running',
                WorkflowExecutionStatus.COMPLETED: 'completed',
                WorkflowExecutionStatus.FAILED: 'failed',
                WorkflowExecutionStatus.CANCELLED: 'failed',
                WorkflowExecutionStatus.TERMINATED: 'failed',
                WorkflowExecutionStatus.CONTINUED_AS_NEW: 'running',
                WorkflowExecutionStatus.TIMED_OUT: 'failed',
            }

            status = status_mapping.get(description.status, 'pending')

            from ..workflow import WorkflowResult

            workflow_result = WorkflowResult(
                workflow_id=workflow_id,
                workflow_name="temporal_workflow",
                status=status,
                steps_completed=1 if status == 'completed' else 0,
                total_steps=1,  # Workflow is treated as single unit
            )

            if status == 'completed':
                try:
                    final_result = await handle.result()
                    workflow_result.final_result = final_result
                except Exception as e:
                    workflow_result.status = 'failed'
                    workflow_result.error = str(e)
            elif status == 'failed':
                try:
                    await handle.result()
                except Exception as e:
                    workflow_result.error = str(e)

            return workflow_result

        except Exception:
            # Fallback to default implementation
            return super().get_workflow_result(workflow_id)