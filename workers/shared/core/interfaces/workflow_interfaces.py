"""Workflow execution interfaces following Interface Segregation Principle.

These interfaces define contracts for workflow execution components,
ensuring modular and testable workflow implementations.
"""

from abc import ABC, abstractmethod
from typing import Any


class WorkflowExecutorInterface(ABC):
    """Interface for workflow executors."""

    @abstractmethod
    def execute(self, workflow_context: dict[str, Any]) -> dict[str, Any]:
        """Execute workflow with given context."""
        pass

    @abstractmethod
    def validate_context(self, workflow_context: dict[str, Any]) -> bool:
        """Validate workflow context before execution."""
        pass

    @abstractmethod
    def get_execution_status(self, execution_id: str) -> str:
        """Get current execution status."""
        pass


class WorkflowValidatorInterface(ABC):
    """Interface for workflow validators."""

    @abstractmethod
    def validate_workflow_definition(self, definition: dict[str, Any]) -> list[str]:
        """Validate workflow definition and return errors."""
        pass

    @abstractmethod
    def validate_input_data(self, data: dict[str, Any]) -> list[str]:
        """Validate input data and return errors."""
        pass


class WorkflowOrchestratorInterface(ABC):
    """Interface for workflow orchestrators."""

    @abstractmethod
    def orchestrate_execution(
        self, workflow_id: str, execution_context: dict[str, Any]
    ) -> str:
        """Orchestrate workflow execution and return execution ID."""
        pass

    @abstractmethod
    def monitor_execution(self, execution_id: str) -> dict[str, Any]:
        """Monitor workflow execution progress."""
        pass

    @abstractmethod
    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel ongoing workflow execution."""
        pass


class FileProcessorInterface(ABC):
    """Interface for file processors."""

    @abstractmethod
    def process_file(self, file_data: dict[str, Any]) -> dict[str, Any]:
        """Process individual file."""
        pass

    @abstractmethod
    def process_batch(self, file_batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process batch of files."""
        pass

    @abstractmethod
    def validate_file_format(self, file_data: dict[str, Any]) -> bool:
        """Validate file format for processing."""
        pass
