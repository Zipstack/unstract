"""Logging and Monitoring Utilities for Workers

Provides structured logging, performance monitoring, and metrics collection for workers.
"""

import functools
import json
import logging
import os
import sys
import time
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import local
from typing import Any

# Thread-local storage for context
_context = local()


@dataclass
class LogContext:
    """Context information for structured logging."""

    worker_name: str | None = None
    task_id: str | None = None
    execution_id: str | None = None
    organization_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None


class WorkerFieldFilter(logging.Filter):
    """Filter to add missing fields for worker logging."""

    def filter(self, record):
        # Add missing fields with default values to match Django backend
        for attr in ["request_id", "otelTraceID", "otelSpanID"]:
            if not hasattr(record, attr):
                setattr(record, attr, "-")
        return True


class DjangoStyleFormatter(logging.Formatter):
    """Custom formatter to match Django backend logging format exactly."""

    def __init__(self, include_context: bool = True):
        """Initialize formatter.

        Args:
            include_context: Whether to include thread-local context in logs
        """
        # Use Django backend's exact format
        format_string = (
            "%(levelname)s : [%(asctime)s]"
            "{module:%(module)s process:%(process)d "
            "thread:%(thread)d request_id:%(request_id)s "
            "trace_id:%(otelTraceID)s span_id:%(otelSpanID)s} :- %(message)s"
        )
        super().__init__(fmt=format_string)
        self.include_context = include_context


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def __init__(self, include_context: bool = True):
        """Initialize formatter.

        Args:
            include_context: Whether to include thread-local context in logs
        """
        super().__init__()
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        # Base log entry
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add extra fields from log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                extra_fields[key] = value

        if extra_fields:
            log_entry["extra"] = extra_fields

        # Add context information if available and enabled
        if self.include_context and hasattr(_context, "log_context"):
            context_dict = asdict(_context.log_context)
            # Only include non-None values
            context_dict = {k: v for k, v in context_dict.items() if v is not None}
            if context_dict:
                log_entry["context"] = context_dict

        return json.dumps(log_entry, default=str)


class WorkerLogger:
    """Enhanced logger for worker processes with structured logging and context management."""

    _loggers: dict[str, logging.Logger] = {}
    _configured = False

    @classmethod
    def configure(
        cls,
        log_level: str = "INFO",
        log_format: str = "structured",
        log_file: str | None = None,
        worker_name: str | None = None,
    ):
        """Configure global logging settings.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_format: Log format ('structured' for JSON, 'simple' for text)
            log_file: Optional log file path
            worker_name: Worker name for context
        """
        if cls._configured:
            return

        # Set root logger level
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))

        # Clear existing handlers
        root_logger.handlers.clear()

        # Choose formatter
        if log_format.lower() == "structured":
            formatter = StructuredFormatter()
        elif log_format.lower() == "django":
            formatter = DjangoStyleFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        # Add filter for Django-style format to ensure required fields are present
        if log_format.lower() == "django":
            console_handler.addFilter(WorkerFieldFilter())

        root_logger.addHandler(console_handler)

        # File handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)

            # Add filter for Django-style format to ensure required fields are present
            if log_format.lower() == "django":
                file_handler.addFilter(WorkerFieldFilter())

            root_logger.addHandler(file_handler)

        # Set worker context if provided
        if worker_name:
            cls.set_context(LogContext(worker_name=worker_name))

        # Suppress only generic HTTP/network libraries that are universally noisy
        # Cloud-specific SDK logging is handled by each connector
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        cls._configured = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger instance.

        Args:
            name: Logger name (typically __name__)

        Returns:
            Logger instance
        """
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger

        return cls._loggers[name]

    @classmethod
    def setup(cls, worker_type) -> logging.Logger:
        """Centralized setup for worker logging using WorkerType enum.

        Args:
            worker_type: WorkerType enum instance

        Returns:
            Configured logger for the worker

        Note:
            This method uses the WorkerRegistry to get logging configuration,
            ensuring consistency across all workers.
        """
        from shared.enums.worker_enums import WorkerType
        from shared.worker_registry import WorkerRegistry

        # Validate worker_type
        if not isinstance(worker_type, WorkerType):
            raise TypeError(f"Expected WorkerType enum, got {type(worker_type)}")

        # Get logging config from registry
        logging_config = WorkerRegistry.get_logging_config(worker_type)

        # Configure logging with registry settings
        cls.configure(
            log_level=os.getenv("LOG_LEVEL", logging_config.get("log_level", "INFO")),
            log_format=os.getenv(
                "LOG_FORMAT", logging_config.get("log_format", "structured")
            ),
            worker_name=worker_type.to_worker_name(),
        )

        # Return logger for the worker
        return cls.get_logger(worker_type.to_worker_name())

    @classmethod
    def set_context(cls, context: LogContext):
        """Set thread-local logging context."""
        _context.log_context = context

    @classmethod
    def update_context(cls, **kwargs):
        """Update thread-local logging context."""
        if not hasattr(_context, "log_context"):
            _context.log_context = LogContext()

        for key, value in kwargs.items():
            if hasattr(_context.log_context, key):
                setattr(_context.log_context, key, value)

    @classmethod
    def clear_context(cls):
        """Clear thread-local logging context."""
        if hasattr(_context, "log_context"):
            delattr(_context, "log_context")

    @classmethod
    def get_context(cls) -> LogContext | None:
        """Get current thread-local logging context."""
        return getattr(_context, "log_context", None)


@dataclass
class PerformanceMetrics:
    """Performance metrics for function execution."""

    function_name: str
    execution_time: float
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    memory_usage: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class PerformanceMonitor:
    """Performance monitoring utilities for tracking function execution metrics."""

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize performance monitor.

        Args:
            logger: Logger instance. Uses default if None.
        """
        self.logger = logger or WorkerLogger.get_logger(__name__)
        self.metrics: dict[str, list] = {}

    def __call__(self, func: Callable) -> Callable:
        """Decorator to monitor function performance."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.monitor_execution(func, *args, **kwargs)

        return wrapper

    def monitor_execution(self, func: Callable, *args, **kwargs) -> Any:
        """Monitor function execution and collect metrics.

        Args:
            func: Function to monitor
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result
        """
        start_time = time.time()
        start_datetime = datetime.now(UTC)
        function_name = f"{func.__module__}.{func.__name__}"

        try:
            # Get memory usage before execution (if psutil available)
            memory_before = self._get_memory_usage()

            self.logger.debug(f"Starting execution of {function_name}")

            # Execute function
            result = func(*args, **kwargs)

            # Calculate metrics
            end_time = time.time()
            end_datetime = datetime.now(UTC)
            execution_time = end_time - start_time
            memory_after = self._get_memory_usage()
            memory_usage = (
                memory_after - memory_before if memory_before and memory_after else None
            )

            # Create metrics record
            metrics = PerformanceMetrics(
                function_name=function_name,
                execution_time=execution_time,
                success=True,
                memory_usage=memory_usage,
                start_time=start_datetime,
                end_time=end_datetime,
            )

            # Log successful execution
            self.logger.info(
                f"Function {function_name} completed successfully",
                extra={
                    "execution_time": execution_time,
                    "memory_usage": memory_usage,
                    "performance_metrics": asdict(metrics),
                },
            )

            # Store metrics
            self._store_metrics(metrics)

            return result

        except Exception as e:
            # Calculate metrics for failed execution
            end_time = time.time()
            end_datetime = datetime.now(UTC)
            execution_time = end_time - start_time

            metrics = PerformanceMetrics(
                function_name=function_name,
                execution_time=execution_time,
                success=False,
                error_type=type(e).__name__,
                error_message=str(e),
                start_time=start_datetime,
                end_time=end_datetime,
            )

            # Log failed execution
            self.logger.error(
                f"Function {function_name} failed after {execution_time:.3f}s",
                extra={
                    "execution_time": execution_time,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "performance_metrics": asdict(metrics),
                },
                exc_info=True,
            )

            # Store metrics
            self._store_metrics(metrics)

            raise

    def _get_memory_usage(self) -> float | None:
        """Get current memory usage in MB."""
        try:
            import psutil

            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except ImportError:
            return None
        except Exception:
            return None

    def _store_metrics(self, metrics: PerformanceMetrics):
        """Store metrics for later analysis."""
        function_name = metrics.function_name
        if function_name not in self.metrics:
            self.metrics[function_name] = []

        self.metrics[function_name].append(metrics)

        # Keep only last 100 metrics per function to prevent memory bloat
        if len(self.metrics[function_name]) > 100:
            self.metrics[function_name] = self.metrics[function_name][-100:]

    def get_metrics(self, function_name: str | None = None) -> dict[str, Any]:
        """Get performance metrics.

        Args:
            function_name: Specific function name. Returns all if None.

        Returns:
            Metrics dictionary
        """
        if function_name:
            function_metrics = self.metrics.get(function_name, [])
        else:
            function_metrics = []
            for metrics_list in self.metrics.values():
                function_metrics.extend(metrics_list)

        if not function_metrics:
            return {}

        # Calculate aggregated metrics
        total_executions = len(function_metrics)
        successful_executions = sum(1 for m in function_metrics if m.success)
        failed_executions = total_executions - successful_executions

        execution_times = [m.execution_time for m in function_metrics]
        avg_execution_time = sum(execution_times) / len(execution_times)
        min_execution_time = min(execution_times)
        max_execution_time = max(execution_times)

        return {
            "function_name": function_name,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": successful_executions / total_executions
            if total_executions > 0
            else 0,
            "avg_execution_time": avg_execution_time,
            "min_execution_time": min_execution_time,
            "max_execution_time": max_execution_time,
            "recent_metrics": [
                asdict(m) for m in function_metrics[-10:]
            ],  # Last 10 executions
        }

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all monitored functions."""
        summary = {}
        for function_name in self.metrics:
            summary[function_name] = self.get_metrics(function_name)

        return summary


@contextmanager
def log_context(**kwargs):
    """Context manager for temporary logging context.

    Usage:
        with log_context(task_id='123', execution_id='456'):
            logger.info("This will include context")
    """
    # Save current context
    original_context = WorkerLogger.get_context()

    try:
        # Update context
        WorkerLogger.update_context(**kwargs)
        yield
    finally:
        # Restore original context
        if original_context:
            WorkerLogger.set_context(original_context)
        else:
            WorkerLogger.clear_context()


def with_execution_context(func: Callable) -> Callable:
    """Decorator to automatically set up logging context for execution functions.

    This decorator extracts common execution context parameters from function arguments
    and sets up logging context automatically, eliminating the need for repetitive
    log_context() usage in task functions.

    Expected function signature patterns:
    - func(self, schema_name, workflow_id, execution_id, pipeline_id=None, ...)
    - func(self, schema_name, execution_id, workflow_id, organization_id=None, ...)

    Args:
        func: The function to wrap with execution context

    Returns:
        Wrapped function with automatic logging context setup

    Usage:
        @with_execution_context
        def my_task(self, schema_name: str, workflow_id: str, execution_id: str, ...):
            # Function body - logging context is automatically available
            logger.info("This will include task_id, execution_id, etc.")
    """
    from functools import wraps

    @wraps(func)
    def wrapper(task_instance, *args, **kwargs) -> Any:
        # Extract task_id from Celery task instance
        task_id = (
            getattr(task_instance.request, "id", None)
            if hasattr(task_instance, "request")
            else None
        )

        # Extract common context parameters from arguments
        # Handle different argument patterns used across tasks
        context = {"task_id": task_id}

        if args:
            # Most common pattern: (schema_name, workflow_id, execution_id, ...)
            if len(args) >= 1:
                schema_name = args[0]
                context["organization_id"] = schema_name

            if len(args) >= 2:
                # Could be workflow_id or execution_id depending on task
                if len(args) >= 3:
                    # Pattern: (schema_name, workflow_id, execution_id, ...)
                    context["workflow_id"] = args[1]
                    context["execution_id"] = args[2]
                else:
                    # Pattern: (schema_name, execution_id, ...)
                    context["execution_id"] = args[1]

            if len(args) >= 4:
                # Check if 4th argument is pipeline_id or another param
                pipeline_id = (
                    args[3] if args[3] is not None else kwargs.get("pipeline_id")
                )
                if pipeline_id:
                    context["pipeline_id"] = pipeline_id

        # Extract additional context from kwargs
        for key in ["workflow_id", "execution_id", "pipeline_id", "organization_id"]:
            if key in kwargs and kwargs[key] is not None:
                context[key] = kwargs[key]

        # Remove None values from context
        context = {k: v for k, v in context.items() if v is not None}

        # Execute function with logging context
        with log_context(**context):
            return func(task_instance, *args, **kwargs)

    return wrapper


def logged_execution(logger: logging.Logger | None = None):
    """Decorator for automatic logging of function execution.

    Args:
        logger: Logger instance. Uses default if None.

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        actual_logger = logger or WorkerLogger.get_logger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            function_name = f"{func.__module__}.{func.__name__}"
            actual_logger.debug(f"Starting execution of {function_name}")

            try:
                result = func(*args, **kwargs)
                actual_logger.debug(f"Successfully completed {function_name}")
                return result
            except Exception as e:
                actual_logger.error(
                    f"Function {function_name} failed: {e}", exc_info=True
                )
                raise

        return wrapper

    return decorator


# Create global performance monitor instance
performance_monitor = PerformanceMonitor()


# Convenience decorators
def monitor_performance(func: Callable) -> Callable:
    """Decorator for performance monitoring."""
    return performance_monitor(func)


def log_execution(func: Callable) -> Callable:
    """Decorator for execution logging."""
    return logged_execution()(func)


# Dataclass/Dictionary Access Utilities


def safe_get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Safely get value from object using both attribute and dictionary access patterns.

    This utility handles the common pattern where objects may be either dataclass instances
    or dictionaries, providing consistent access regardless of the actual type.

    Args:
        obj: Object to get value from (dataclass instance or dictionary)
        key: Key/attribute name to access
        default: Default value if key/attribute not found

    Returns:
        Value from object or default if not found

    Examples:
        >>> safe_get_attr(WorkerFileData(execution_id="123"), "execution_id")
        "123"
        >>> safe_get_attr({"execution_id": "456"}, "execution_id")
        "456"
        >>> safe_get_attr({}, "missing_key", "default")
        "default"
    """
    # First try attribute access (for dataclass objects)
    if hasattr(obj, key):
        return getattr(obj, key, default)
    # Then try dictionary access
    elif isinstance(obj, dict):
        return obj.get(key, default)
    # Fallback to default
    else:
        return default


def ensure_dict_access(obj: Any, keys: list, default: Any = None) -> dict[str, Any]:
    """Extract multiple values from object using safe access patterns.

    Args:
        obj: Object to extract values from
        keys: List of keys/attributes to extract
        default: Default value for missing keys

    Returns:
        Dictionary with extracted values

    Example:
        >>> ensure_dict_access(file_data, ["execution_id", "workflow_id", "organization_id"])
        {'execution_id': '123', 'workflow_id': '456', 'organization_id': 'org_789'}
    """
    return {key: safe_get_attr(obj, key, default) for key in keys}
