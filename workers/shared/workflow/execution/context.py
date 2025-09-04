"""Execution Context Management for Worker Tasks

This module provides standardized execution context setup, error handling,
and resource management patterns used across all worker task implementations.
"""

import logging
from contextlib import contextmanager
from typing import Any

from unstract.core.data_models import ExecutionStatus

from ...api.facades.legacy_client import InternalAPIClient
from ...constants.account import Account
from ...core.exceptions import WorkflowExecutionError as WorkerExecutionError
from ...infrastructure.config import WorkerConfig
from ...infrastructure.logging import WorkerLogger
from ...legacy.local_context import StateStore

logger = WorkerLogger.get_logger(__name__)


class WorkerExecutionContext:
    """Manages common worker execution setup and teardown patterns."""

    @staticmethod
    def setup_execution_context(
        organization_id: str, execution_id: str, workflow_id: str
    ) -> tuple[WorkerConfig, InternalAPIClient]:
        """Set up common execution context for worker tasks.

        Args:
            organization_id: Organization context ID
            execution_id: Workflow execution ID
            workflow_id: Workflow ID

        Returns:
            Tuple of (WorkerConfig, InternalAPIClient) configured for the context

        Raises:
            WorkerExecutionError: If context setup fails
        """
        try:
            # Set up organization context in state store
            StateStore.set(Account.ORGANIZATION_ID, organization_id)

            # Initialize API client with configuration
            config = WorkerConfig()
            api_client = InternalAPIClient(config)
            api_client.set_organization_context(organization_id)

            logger.info(
                f"Execution context setup complete - "
                f"org_id={organization_id}, exec_id={execution_id}, workflow_id={workflow_id}"
            )

            return config, api_client

        except Exception as e:
            logger.error(f"Failed to setup execution context: {e}")
            raise WorkerExecutionError(f"Context setup failed: {e}") from e

    @staticmethod
    def handle_execution_error(
        api_client: InternalAPIClient,
        execution_id: str,
        error: Exception,
        logger: logging.Logger,
        context: str = "execution",
    ) -> None:
        """Standardized error handling for execution failures.

        Args:
            api_client: API client for status updates
            execution_id: Execution ID to update
            error: The error that occurred
            logger: Logger instance for error reporting
            context: Context description for logging
        """
        error_message = str(error)
        logger.error(f"Error in {context}: {error_message}")

        try:
            api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=ExecutionStatus.ERROR.value,
                error_message=error_message,
            )
            logger.info(
                f"Execution status updated to ERROR for execution_id={execution_id}"
            )

        except Exception as update_error:
            logger.error(
                f"Failed to update execution status to ERROR: {update_error}. "
                f"Original error: {error_message}"
            )

    @staticmethod
    @contextmanager
    def managed_execution_context(
        organization_id: str, execution_id: str, workflow_id: str
    ):
        """Context manager for automatic execution context setup and cleanup.

        Args:
            organization_id: Organization context ID
            execution_id: Workflow execution ID
            workflow_id: Workflow ID

        Yields:
            Tuple of (WorkerConfig, InternalAPIClient)

        Usage:
            with WorkerExecutionContext.managed_execution_context(
                org_id, exec_id, workflow_id
            ) as (config, api_client):
                # Worker task logic here
                pass
        """
        config = None
        api_client = None

        try:
            config, api_client = WorkerExecutionContext.setup_execution_context(
                organization_id, execution_id, workflow_id
            )
            yield config, api_client

        except Exception as e:
            if api_client:
                WorkerExecutionContext.handle_execution_error(
                    api_client, execution_id, e, logger, "managed_context"
                )
            raise

        finally:
            # Cleanup resources if needed
            try:
                if api_client:
                    api_client.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during context cleanup: {cleanup_error}")

    @staticmethod
    def log_task_start(
        task_name: str,
        execution_id: str,
        workflow_id: str,
        additional_params: dict[str, Any] | None = None,
    ) -> None:
        """Standardized task start logging.

        Args:
            task_name: Name of the task being executed
            execution_id: Workflow execution ID
            workflow_id: Workflow ID
            additional_params: Optional additional parameters to log
        """
        log_parts = [
            f"Starting {task_name}",
            f"execution_id={execution_id}",
            f"workflow_id={workflow_id}",
        ]

        if additional_params:
            for key, value in additional_params.items():
                # Sanitize sensitive information
                if (
                    "password" in key.lower()
                    or "secret" in key.lower()
                    or "token" in key.lower()
                ):
                    value = "***REDACTED***"
                log_parts.append(f"{key}={value}")

        logger.info(" - ".join(log_parts))

    @staticmethod
    def log_task_completion(
        task_name: str,
        execution_id: str,
        success: bool,
        result_summary: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Standardized task completion logging.

        Args:
            task_name: Name of the task that completed
            execution_id: Workflow execution ID
            success: Whether the task completed successfully
            result_summary: Optional summary of results
            duration_seconds: Optional task duration
        """
        status = "SUCCESS" if success else "FAILED"
        log_parts = [f"{task_name} {status}", f"execution_id={execution_id}"]

        if duration_seconds is not None:
            log_parts.append(f"duration={duration_seconds:.2f}s")

        if result_summary:
            log_parts.append(f"result={result_summary}")

        if success:
            logger.info(" - ".join(log_parts))
        else:
            logger.error(" - ".join(log_parts))


class WorkerTaskMixin:
    """Mixin class to add common execution context methods to worker tasks."""

    def setup_context(self, organization_id: str, execution_id: str, workflow_id: str):
        """Set up execution context for this task."""
        return WorkerExecutionContext.setup_execution_context(
            organization_id, execution_id, workflow_id
        )

    def handle_error(
        self, api_client: InternalAPIClient, execution_id: str, error: Exception
    ):
        """Handle execution error for this task."""
        # Get logger from the task instance if available
        task_logger = getattr(self, "logger", logger)
        WorkerExecutionContext.handle_execution_error(
            api_client, execution_id, error, task_logger, self.__class__.__name__
        )

    def log_start(self, execution_id: str, workflow_id: str, **params):
        """Log task start with standard format."""
        WorkerExecutionContext.log_task_start(
            self.__class__.__name__, execution_id, workflow_id, params
        )

    def log_completion(self, execution_id: str, success: bool, **kwargs):
        """Log task completion with standard format."""
        WorkerExecutionContext.log_task_completion(
            self.__class__.__name__, execution_id, success, **kwargs
        )
