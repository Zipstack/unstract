"""Worker Base Classes and Decorators

This module provides base classes and decorators to reduce code duplication
across worker implementations and standardize common patterns.
"""

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from .worker_models import (
    ExecutionStatus,
    QueueName,
    TaskError,
    TaskExecutionContext,
    TaskName,
    TaskPerformanceMetrics,
    TaskRetryConfig,
    TaskTimeoutConfig,
)

logger = logging.getLogger(__name__)

# Type variables for generic base classes
T = TypeVar("T")
TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Any])


class WorkerTaskBase(ABC):
    """Abstract base class for all worker task implementations.

    Provides common functionality for:
    - API client management
    - Organization context handling
    - Error handling patterns
    - Performance monitoring
    - Logging context
    """

    def __init__(self, config=None):
        """Initialize base worker task.

        Args:
            config: Worker configuration instance (optional)
        """
        self.config = config
        self._api_client = None
        self._current_context: TaskExecutionContext | None = None
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def api_client(self):
        """Get API client instance (lazy initialization)."""
        if self._api_client is None and self.config:
            from shared.api_client import InternalAPIClient

            self._api_client = InternalAPIClient(self.config)
        return self._api_client

    def set_organization_context(self, organization_id: str):
        """Set organization context for API operations."""
        if self.api_client:
            self.api_client.set_organization_context(organization_id)

    @contextmanager
    def task_context(self, context: TaskExecutionContext):
        """Context manager for task execution with automatic cleanup."""
        self._current_context = context
        self.set_organization_context(context.organization_id)

        # Set up structured logging context
        old_extra = getattr(self.logger, "_extra", {})
        self.logger._extra = context.get_log_context()

        try:
            self.logger.info(f"Starting task {context.task_name.value}")
            yield context
        except Exception as e:
            self.logger.error(
                f"Task {context.task_name.value} failed: {e}",
                extra={"error_type": type(e).__name__, "error_message": str(e)},
            )
            raise
        finally:
            self.logger._extra = old_extra
            self._current_context = None

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """Execute the main task logic.

        This method must be implemented by all task classes.
        """
        pass

    def handle_error(
        self, error: Exception, context: TaskExecutionContext | None = None
    ) -> TaskError:
        """Handle task errors with structured error information."""
        task_context = context or self._current_context
        if not task_context:
            raise ValueError("No task context available for error handling")

        task_error = TaskError.from_exception(
            task_id=task_context.task_id,
            task_name=task_context.task_name,
            exception=error,
            retry_count=task_context.retry_count,
        )

        self.logger.error(
            f"Task error: {task_error.error_message}", extra=task_error.to_dict()
        )

        return task_error

    def update_execution_status(
        self, execution_id: str, status: ExecutionStatus, error_message: str | None = None
    ) -> bool:
        """Update workflow execution status via API."""
        if not self.api_client:
            self.logger.warning("No API client available for status update")
            return False

        try:
            from .worker_models import WorkflowExecutionUpdateRequest

            update_request = WorkflowExecutionUpdateRequest(
                status=status, error_message=error_message
            )

            response = self.api_client.update_workflow_execution_status(
                execution_id=execution_id, **update_request.to_dict()
            )

            return response.get("updated", False)

        except Exception as e:
            self.logger.error(f"Failed to update execution status: {e}")
            return False


class FileProcessingTaskBase(WorkerTaskBase):
    """Base class for file processing tasks.

    Provides specialized functionality for:
    - File handling operations
    - Batch processing patterns
    - File execution status updates
    - File history management
    """

    def __init__(self, config=None):
        """Initialize file processing task base."""
        super().__init__(config)
        self._file_history_manager = None

    @property
    def file_history_manager(self):
        """Get file history manager instance (lazy initialization)."""
        if self._file_history_manager is None and self.api_client:
            from shared.file_history_manager import WorkerFileHistoryManager

            self._file_history_manager = WorkerFileHistoryManager(self.api_client)
        return self._file_history_manager

    def update_file_execution_status(
        self,
        file_execution_id: str,
        status: ExecutionStatus,
        error_message: str | None = None,
        result: Any | None = None,
    ) -> bool:
        """Update file execution status via API."""
        if not self.api_client:
            self.logger.warning("No API client available for file status update")
            return False

        try:
            from .worker_models import FileExecutionStatusUpdateRequest

            update_request = FileExecutionStatusUpdateRequest(
                status=status.value, error_message=error_message, result=result
            )

            response = self.api_client.update_file_execution_status(
                file_execution_id=file_execution_id, **update_request.to_dict()
            )

            return response.get("updated", False)

        except Exception as e:
            self.logger.error(f"Failed to update file execution status: {e}")
            return False

    def process_file_batch(self, files: list[Any], file_data: Any) -> Any:
        """Process a batch of files with error handling.

        This method provides a template for batch processing with
        individual file error handling and status updates.
        """
        from .worker_models import BatchExecutionResult, FileExecutionResult

        batch_result = BatchExecutionResult(
            total_files=len(files), successful_files=0, failed_files=0, execution_time=0.0
        )

        start_time = time.time()

        for file_item in files:
            file_start_time = time.time()

            try:
                # Process individual file (implemented by subclass)
                result = self.process_single_file(file_item, file_data)

                file_result = FileExecutionResult(
                    file=file_item.get("file_name", "unknown"),
                    file_execution_id=result.get("file_execution_id"),
                    status=ExecutionStatus.COMPLETED,
                    result=result,
                    processing_time=time.time() - file_start_time,
                )

                batch_result.add_file_result(file_result)

            except Exception as e:
                file_result = FileExecutionResult(
                    file=file_item.get("file_name", "unknown"),
                    file_execution_id=None,
                    status=ExecutionStatus.ERROR,
                    error=str(e),
                    processing_time=time.time() - file_start_time,
                )

                batch_result.add_file_result(file_result)
                self.logger.error(f"Failed to process file {file_item}: {e}")

        batch_result.execution_time = time.time() - start_time
        return batch_result

    @abstractmethod
    def process_single_file(self, file_item: Any, file_data: Any) -> Any:
        """Process a single file.

        Must be implemented by concrete file processing tasks.
        """
        pass


class CallbackTaskBase(WorkerTaskBase):
    """Base class for callback tasks.

    Provides specialized functionality for:
    - Batch result aggregation
    - Status updates and notifications
    - Pipeline status mapping
    - Callback execution context
    """

    def __init__(self, config=None):
        """Initialize callback task base."""
        super().__init__(config)
        self._cache_manager = None

    @property
    def cache_manager(self):
        """Get cache manager instance (lazy initialization)."""
        if self._cache_manager is None and self.config:
            from shared.cache_utils import WorkerCacheManager

            self._cache_manager = WorkerCacheManager(self.config)
        return self._cache_manager

    def update_pipeline_status(
        self,
        pipeline_id: str,
        status: Any,  # PipelineStatus from worker_models
        execution_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Update pipeline status via API."""
        if not self.api_client:
            self.logger.warning("No API client available for pipeline status update")
            return False

        try:
            from .worker_models import PipelineStatusUpdateRequest

            update_request = PipelineStatusUpdateRequest(
                status=status, execution_summary=execution_summary
            )

            response = self.api_client.update_pipeline_status(
                pipeline_id=pipeline_id, **update_request.to_dict()
            )

            return response.get("updated", False)

        except Exception as e:
            self.logger.error(f"Failed to update pipeline status: {e}")
            return False

    def aggregate_batch_results(self, results: list[Any]) -> Any:
        """Aggregate results from multiple batch executions."""
        from .worker_models import BatchExecutionResult, CallbackExecutionData

        if not results:
            return CallbackExecutionData(
                execution_id="",
                pipeline_id="",
                organization_id="",
                workflow_id="",
                total_batches=0,
                completed_batches=0,
            )

        # Convert results to BatchExecutionResult if needed
        batch_results = []
        for result in results:
            if isinstance(result, dict):
                batch_results.append(BatchExecutionResult.from_dict(result))
            elif hasattr(result, "to_dict"):
                batch_results.append(result)
            else:
                self.logger.warning(f"Unknown result type: {type(result)}")

        # Extract common context from first result
        first_result = batch_results[0] if batch_results else None

        return CallbackExecutionData(
            execution_id=getattr(first_result, "execution_id", ""),
            pipeline_id=getattr(first_result, "pipeline_id", ""),
            organization_id=getattr(first_result, "organization_id", ""),
            workflow_id=getattr(first_result, "workflow_id", ""),
            batch_results=batch_results,
            total_batches=len(results),
            completed_batches=len([r for r in batch_results if r.total_files > 0]),
        )


# Task Decorators and Helpers
def create_task_decorator(
    task_name: TaskName,
    queue_name: QueueName,
    retry_config: TaskRetryConfig | None = None,
    timeout_config: TaskTimeoutConfig | None = None,
):
    """Create a standardized Celery task decorator.

    Args:
        task_name: Standardized task name enum
        queue_name: Target queue for task execution
        retry_config: Retry configuration (uses defaults if None)
        timeout_config: Timeout configuration (uses defaults if None)

    Returns:
        Configured Celery task decorator
    """
    retry_config = retry_config or TaskRetryConfig()
    timeout_config = timeout_config or TaskTimeoutConfig()

    def decorator(celery_app):
        """Return the actual decorator that takes the Celery app."""

        def task_decorator(func: TaskFunc) -> TaskFunc:
            """Decorate the task function."""
            # Combine all configuration
            task_kwargs = {
                "bind": True,
                "name": task_name.value,
                "queue": queue_name.value,
                **retry_config.to_celery_kwargs(),
                **timeout_config.to_celery_kwargs(),
            }

            return celery_app.task(**task_kwargs)(func)

        return task_decorator

    return decorator


def monitor_performance(func: TaskFunc) -> TaskFunc:
    """Decorator to monitor task performance metrics.

    Automatically tracks execution time, memory usage, and errors.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        start_memory = None

        try:
            import psutil

            process = psutil.Process()
            start_memory = process.memory_info().rss / 1024 / 1024  # MB
        except ImportError:
            pass

        task_name = getattr(self.request, "task", func.__name__)
        retry_count = getattr(self.request, "retries", 0)

        try:
            result = func(self, *args, **kwargs)

            # Record successful execution metrics
            execution_time = time.time() - start_time
            memory_usage = None

            if start_memory is not None:
                try:
                    end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                    memory_usage = end_memory - start_memory
                except ImportError:
                    pass

            metrics = TaskPerformanceMetrics(
                task_name=task_name,
                execution_time=execution_time,
                memory_usage=memory_usage,
                retry_count=retry_count,
            )

            logger.info(
                f"Task {task_name} completed successfully", extra=metrics.to_dict()
            )

            return result

        except Exception as e:
            # Record error metrics
            execution_time = time.time() - start_time

            metrics = TaskPerformanceMetrics(
                task_name=task_name,
                execution_time=execution_time,
                error_count=1,
                retry_count=retry_count,
            )

            logger.error(f"Task {task_name} failed: {e}", extra=metrics.to_dict())

            raise

    return wrapper


def with_task_context(context_factory: Callable[..., TaskExecutionContext]):
    """Decorator to automatically create and manage task execution context.

    Args:
        context_factory: Function that creates TaskExecutionContext from task args
    """

    def decorator(func: TaskFunc) -> TaskFunc:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Create context from task arguments
            context = context_factory(self, *args, **kwargs)

            # Execute task with context
            if hasattr(self, "task_context"):
                with self.task_context(context):
                    return func(self, *args, **kwargs)
            else:
                return func(self, *args, **kwargs)

        return wrapper

    return decorator


def circuit_breaker(failure_threshold: int = 5, recovery_timeout: float = 120.0):
    """Decorator to implement circuit breaker pattern for external service calls.

    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Time to wait before trying to close circuit
    """

    def decorator(func: TaskFunc) -> TaskFunc:
        func._circuit_state = "closed"  # closed, open, half_open
        func._failure_count = 0
        func._last_failure_time = 0

        @wraps(func)
        def wrapper(*args, **kwargs):
            current_time = time.time()

            # Check if circuit should transition from open to half_open
            if (
                func._circuit_state == "open"
                and current_time - func._last_failure_time > recovery_timeout
            ):
                func._circuit_state = "half_open"
                logger.info(
                    f"Circuit breaker for {func.__name__} transitioned to half-open"
                )

            # Reject calls if circuit is open
            if func._circuit_state == "open":
                raise Exception(f"Circuit breaker open for {func.__name__}")

            try:
                result = func(*args, **kwargs)

                # Reset failure count on success
                if func._circuit_state == "half_open":
                    func._circuit_state = "closed"
                    func._failure_count = 0
                    logger.info(f"Circuit breaker for {func.__name__} closed")

                return result

            except Exception:
                func._failure_count += 1
                func._last_failure_time = current_time

                # Open circuit if failure threshold reached
                if func._failure_count >= failure_threshold:
                    func._circuit_state = "open"
                    logger.warning(
                        f"Circuit breaker for {func.__name__} opened after {func._failure_count} failures"
                    )

                raise

        return wrapper

    return decorator


# Task Factory Functions
def create_file_processing_task(
    task_name: TaskName,
    queue_name: QueueName = QueueName.FILE_PROCESSING,
    retry_config: TaskRetryConfig | None = None,
) -> Callable:
    """Factory function to create file processing tasks with standard configuration."""

    class FileProcessingTask(FileProcessingTaskBase):
        """Generated file processing task class."""

        def execute(self, *args, **kwargs):
            """Execute file processing logic."""
            return self.process_file_batch(*args, **kwargs)

        def process_single_file(self, file_item: Any, file_data: Any) -> Any:
            """Default single file processing (override in specific implementations)."""
            raise NotImplementedError("process_single_file must be implemented")

    return FileProcessingTask


def create_callback_task(
    task_name: TaskName,
    queue_name: QueueName = QueueName.CALLBACK,
    retry_config: TaskRetryConfig | None = None,
) -> Callable:
    """Factory function to create callback tasks with standard configuration."""

    class CallbackTask(CallbackTaskBase):
        """Generated callback task class."""

        def execute(self, results, *args, **kwargs):
            """Execute callback logic with result aggregation."""
            callback_data = self.aggregate_batch_results(results)
            return self.process_callback(callback_data, *args, **kwargs)

        def process_callback(self, callback_data: Any, *args, **kwargs) -> Any:
            """Default callback processing (override in specific implementations)."""
            raise NotImplementedError("process_callback must be implemented")

    return CallbackTask
