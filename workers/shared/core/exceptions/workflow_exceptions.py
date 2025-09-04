"""Workflow execution related exceptions.

These exceptions handle workflow-specific error scenarios following
the Single Responsibility Principle.
"""

from .base_exceptions import WorkerBaseError


class WorkflowExecutionError(WorkerBaseError):
    """Base exception for workflow execution errors."""

    def __init__(
        self, message: str, workflow_id: str = None, execution_id: str = None, **kwargs
    ):
        super().__init__(message, **kwargs)
        self.workflow_id = workflow_id
        self.execution_id = execution_id


class WorkflowConfigurationError(WorkflowExecutionError):
    """Raised when workflow configuration is invalid."""

    pass


class WorkflowValidationError(WorkflowExecutionError):
    """Raised when workflow validation fails."""

    pass


class WorkflowTimeoutError(WorkflowExecutionError):
    """Raised when workflow execution times out."""

    def __init__(self, message: str, timeout_duration: float = None, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout_duration = timeout_duration


class WorkflowFileProcessingError(WorkflowExecutionError):
    """Raised when file processing within workflow fails."""

    def __init__(self, message: str, file_name: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.file_name = file_name
