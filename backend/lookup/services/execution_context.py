"""Execution context for Look-up operations.

This module provides a dataclass for managing execution context
across different execution environments (Prompt Studio vs Workflow).
"""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class LookupExecutionContext:
    """Context for Look-up execution supporting both PS and Workflow contexts.

    This dataclass encapsulates all context information needed for Look-up
    execution, including logging configuration for both real-time WebSocket
    logs (Prompt Studio) and file-centric logs (ETL/Workflow/API).

    Attributes:
        organization_id: The tenant organization ID for multi-tenancy
        prompt_studio_project_id: The Prompt Studio project UUID
        workflow_execution_id: Workflow execution UUID (for ETL/Workflow/API)
        file_execution_id: File execution UUID (for file-centric logging)
        session_id: WebSocket session ID (for real-time Prompt Studio logs)
        doc_name: Current document name being processed
        publish_logs: Whether to publish logs (default True)
        execution_id: Unique execution ID for grouping related Look-ups

    Example:
        # Prompt Studio context (real-time WebSocket logs)
        >>> ps_context = LookupExecutionContext(
        ...     organization_id="org-123",
        ...     prompt_studio_project_id=UUID("..."),
        ...     session_id="ws-session-abc",
        ...     doc_name="invoice.pdf",
        ... )
        >>> ps_context.is_prompt_studio_context
        True

        # Workflow context (file-centric logs)
        >>> wf_context = LookupExecutionContext(
        ...     organization_id="org-123",
        ...     prompt_studio_project_id=UUID("..."),
        ...     workflow_execution_id=UUID("..."),
        ...     file_execution_id=UUID("..."),
        ...     doc_name="invoice.pdf",
        ... )
        >>> wf_context.is_workflow_context
        True
    """

    # Required fields
    organization_id: str
    prompt_studio_project_id: UUID

    # Optional - for file-centric logging (ETL/Workflow/API)
    workflow_execution_id: UUID | None = None
    file_execution_id: UUID | None = None

    # Optional - for real-time logging (Prompt Studio)
    session_id: str | None = None
    doc_name: str | None = None

    # Logging control
    publish_logs: bool = True

    # Execution tracking
    execution_id: str | None = field(default=None)

    @property
    def is_workflow_context(self) -> bool:
        """Check if executing within a workflow context (ETL/Workflow/API).

        Returns:
            True if file_execution_id is set, indicating workflow execution.
        """
        return self.file_execution_id is not None

    @property
    def is_prompt_studio_context(self) -> bool:
        """Check if executing within Prompt Studio IDE (real-time logs).

        Returns:
            True if session_id is set and NOT in workflow context.
        """
        return self.session_id is not None and not self.is_workflow_context

    @property
    def should_emit_websocket_logs(self) -> bool:
        """Check if WebSocket logs should be emitted.

        Returns:
            True if in Prompt Studio context and logging is enabled.
        """
        return self.publish_logs and self.is_prompt_studio_context

    @property
    def should_persist_execution_logs(self) -> bool:
        """Check if execution logs should be persisted to database.

        Returns:
            True if in workflow context and logging is enabled.
        """
        return self.publish_logs and self.is_workflow_context
