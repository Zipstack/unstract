"""Workflow logger helper for safe logging operations.

This module provides a helper class to handle workflow logging operations
safely, eliminating the need for repetitive conditional checks throughout
the codebase.
"""

import logging

from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger


class WorkflowLoggerHelper:
    """Helper class for safe workflow logging operations.

    This class encapsulates the logic for safely logging messages when a
    workflow_log instance is available, eliminating repetitive conditional
    checks throughout the connector classes.
    """

    def __init__(self, workflow_log: WorkerWorkflowLogger | None = None) -> None:
        """Initialize the logger helper.

        Args:
            workflow_log: Optional workflow log instance that provides
                         log_info and log_error methods.
        """
        self.workflow_log = workflow_log

    def log_info(self, logger: logging.Logger, message: str) -> None:
        """Safely log info message if workflow_log is available.

        Args:
            logger: The standard Python logger instance
            message: The message to log
        """
        if self.workflow_log:
            self.workflow_log.log_info(logger, message)

    def log_error(self, logger: logging.Logger, message: str) -> None:
        """Safely log error message if workflow_log is available.

        Args:
            logger: The standard Python logger instance
            message: The error message to log
        """
        if self.workflow_log:
            self.workflow_log.log_error(logger, message)
