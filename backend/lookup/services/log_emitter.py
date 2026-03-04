"""Look-up Log Emitter for WebSocket and file-centric logging.

This module provides functionality to emit Look-up execution logs
via WebSocket for real-time display in Prompt Studio and to persist
logs for file-centric logging in ETL/Workflow/API executions.
"""

import logging
import time
from typing import Any
from uuid import UUID

from unstract.core.pubsub_helper import LogPublisher
from unstract.workflow_execution.enums import LogLevel, LogStage

logger = logging.getLogger(__name__)


class LookupLogEmitter:
    """Emits Lookup enrichment logs via WebSocket and persists to execution logs.

    This class provides methods to emit logs at different stages of Look-up
    execution, with support for both real-time WebSocket logs (Prompt Studio)
    and file-centric execution logs (ETL/Workflow/API).

    The logs use a purple color scheme (#722ed1) in the frontend for
    visual distinction from other log stages.

    Example:
        >>> emitter = LookupLogEmitter(
        ...     session_id="ws-session-123",
        ...     execution_id="exec-456",
        ...     organization_id="org-789",
        ... )
        >>> emitter.emit_enrichment_start("Vendor Lookup", ["vendor_name"])
        >>> emitter.emit_enrichment_success("Vendor Lookup", 3, False, 150)
    """

    LOG_STAGE = LogStage.LOOKUP.value
    LOG_TYPE = "LOOKUP_ENRICHMENT"

    def __init__(
        self,
        session_id: str | None = None,
        execution_id: str | None = None,
        file_execution_id: str | UUID | None = None,
        organization_id: str | None = None,
        doc_name: str | None = None,
    ):
        """Initialize the log emitter.

        Args:
            session_id: WebSocket session ID for real-time logs
            execution_id: Workflow execution ID for file-centric logs
            file_execution_id: File execution ID for file-centric logs
            organization_id: Organization ID for multi-tenancy
            doc_name: Current document name being processed
        """
        self.session_id = session_id
        self.execution_id = str(execution_id) if execution_id else None
        self.file_execution_id = str(file_execution_id) if file_execution_id else None
        self.organization_id = organization_id
        self.doc_name = doc_name

    def _build_component(
        self,
        lookup_project_name: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build the component metadata for the log entry.

        Args:
            lookup_project_name: Name of the Look-up project
            **extra: Additional metadata to include

        Returns:
            Dictionary with component metadata
        """
        component = {
            "type": self.LOG_TYPE,
            "lookup_project": lookup_project_name,
        }
        if self.doc_name:
            component["doc_name"] = self.doc_name
        component.update(extra)
        return component

    def emit_log(
        self,
        level: str,
        message: str,
        lookup_project_name: str = "",
        state: str = "INFO",
        **extra: Any,
    ) -> None:
        """Emit a lookup log event via WebSocket and/or ExecutionLog.

        For Prompt Studio (session_id set): Emits to WebSocket for real-time display
        For Workflow/API (file_execution_id set): Persists to ExecutionLog for Nav bar

        Args:
            level: Log level (INFO, ERROR, WARN, DEBUG)
            message: Log message
            lookup_project_name: Name of the Look-up project
            state: Log state (STARTED, COMPLETED, FAILED, SKIPPED)
            **extra: Additional metadata for the component
        """
        log_details = LogPublisher.log_workflow(
            stage=self.LOG_STAGE,
            message=message,
            level=level,
            execution_id=self.execution_id,
            file_execution_id=self.file_execution_id,
            organization_id=self.organization_id,
        )

        # Add component metadata for frontend rendering
        log_details["component"] = self._build_component(
            lookup_project_name=lookup_project_name,
            state=state,
            **extra,
        )

        # Emit to WebSocket if session_id is available (Prompt Studio)
        if self.session_id:
            LogPublisher.publish(self.session_id, log_details)
            logger.debug(f"Emitted lookup log to WebSocket: {message}")

        # Persist to ExecutionLog if in workflow context (Nav bar logs)
        if self.file_execution_id and self.execution_id:
            self._persist_to_execution_log(log_details, level, message)

    def _persist_to_execution_log(
        self,
        log_details: dict[str, Any],
        level: str,
        message: str,
    ) -> None:
        """Persist log entry to ExecutionLog via Redis queue for Nav bar display.

        Uses the same Redis queue mechanism as other workflow logs to ensure
        proper ordering of logs when displayed in the Nav bar.

        Args:
            log_details: The log details dictionary
            level: Log level
            message: Log message
        """
        try:
            import redis
            from django.conf import settings

            from unstract.core.log_utils import store_execution_log

            # Build log data matching the expected format for the queue
            log_data = {
                "timestamp": time.time(),  # Unix timestamp for queue processing
                "type": "LOG",
                "level": level,
                "stage": self.LOG_STAGE,
                "log": message,
                "execution_id": self.execution_id,
                "file_execution_id": self.file_execution_id,
                "organization_id": self.organization_id,
                **log_details,
            }

            # Use the same Redis queue as other workflow logs
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=int(settings.REDIS_PORT),
                username=settings.REDIS_USER,
                password=settings.REDIS_PASSWORD,
            )

            from utils.constants import ExecutionLogConstants

            store_execution_log(
                data=log_data,
                redis_client=redis_client,
                log_queue_name=ExecutionLogConstants.LOG_QUEUE_NAME,
                is_enabled=ExecutionLogConstants.IS_ENABLED,
            )
            logger.debug(f"Queued lookup log for ExecutionLog: {message}")

        except Exception as e:
            logger.warning(f"Failed to queue lookup log for ExecutionLog: {e}")

    def emit_enrichment_start(
        self,
        lookup_project_name: str,
        input_fields: list[str] | None = None,
    ) -> None:
        """Emit log when Look-up enrichment starts.

        Args:
            lookup_project_name: Name of the Look-up project
            input_fields: List of input field names being used
        """
        input_fields = input_fields or []
        fields_str = ", ".join(input_fields[:3])
        if len(input_fields) > 3:
            fields_str += f" (+{len(input_fields) - 3} more)"

        message = f"Starting enrichment with Look-Up '{lookup_project_name}'"
        if fields_str:
            message += f" for: {fields_str}"

        self.emit_log(
            level=LogLevel.INFO.value,
            state="STARTED",
            message=message,
            lookup_project_name=lookup_project_name,
            input_fields=input_fields,
        )

    def emit_enrichment_success(
        self,
        lookup_project_name: str,
        enriched_count: int,
        cached: bool,
        execution_time_ms: int,
        confidence: float | None = None,
        context_type: str = "full",
    ) -> None:
        """Emit log when Look-up enrichment succeeds.

        Args:
            lookup_project_name: Name of the Look-up project
            enriched_count: Number of fields enriched
            cached: Whether the response was from cache
            execution_time_ms: Execution time in milliseconds
            confidence: Optional confidence score (0.0-1.0)
            context_type: Type of context used - "rag" or "full"
        """
        cache_msg = " (cached)" if cached else ""
        # Display context type clearly: RAG-based or Full context
        context_display = "RAG" if context_type == "rag" else "Full context"
        message = (
            f"Look-Up '{lookup_project_name}' [{context_display}] enriched "
            f"{enriched_count} field(s){cache_msg} in {execution_time_ms}ms"
        )

        if confidence is not None:
            message += f" (confidence: {confidence:.0%})"

        self.emit_log(
            level=LogLevel.INFO.value,
            state="COMPLETED",
            message=message,
            lookup_project_name=lookup_project_name,
            cached=cached,
            execution_time_ms=execution_time_ms,
            enriched_count=enriched_count,
            confidence=confidence,
            context_type=context_type,
        )

    def emit_enrichment_failure(
        self,
        lookup_project_name: str,
        error_message: str,
    ) -> None:
        """Emit log when Look-up enrichment fails.

        Args:
            lookup_project_name: Name of the Look-up project
            error_message: Error message describing the failure
        """
        message = f"Look-Up '{lookup_project_name}' failed: {error_message}"

        self.emit_log(
            level=LogLevel.ERROR.value,
            state="FAILED",
            message=message,
            lookup_project_name=lookup_project_name,
            error_message=error_message,
        )

    def emit_context_overflow_error(
        self,
        lookup_project_name: str,
        token_count: int,
        context_limit: int,
        model: str,
    ) -> None:
        """Emit log when context window is exceeded.

        This provides a clear, actionable error message when the prompt
        (reference data + template + extracted data) exceeds the LLM's
        context window limit.

        Args:
            lookup_project_name: Name of the Look-up project
            token_count: Number of tokens in the prompt
            context_limit: Maximum tokens allowed by the model
            model: Name of the LLM model
        """
        message = (
            f"Look-Up '{lookup_project_name}' failed: Context window exceeded - "
            f"prompt requires {token_count:,} tokens but {model} limit is "
            f"{context_limit:,} tokens. Reduce reference data size or use a "
            f"model with larger context window."
        )

        self.emit_log(
            level=LogLevel.ERROR.value,
            state="FAILED",
            message=message,
            lookup_project_name=lookup_project_name,
            error_type="context_window_exceeded",
            token_count=token_count,
            context_limit=context_limit,
            model=model,
            suggestion="Reduce reference data or use larger context model",
        )

    def emit_enrichment_partial(
        self,
        lookup_project_name: str,
        enriched_count: int,
        execution_time_ms: int,
        warning_message: str,
        confidence: float | None = None,
        context_type: str = "full",
    ) -> None:
        """Emit log when Look-up enrichment partially succeeds.

        Args:
            lookup_project_name: Name of the Look-up project
            enriched_count: Number of fields enriched
            execution_time_ms: Execution time in milliseconds
            warning_message: Warning message about partial success
            confidence: Optional confidence score (0.0-1.0)
            context_type: Type of context used - "rag" or "full"
        """
        # Display context type clearly: RAG-based or Full context
        context_display = "RAG" if context_type == "rag" else "Full context"
        message = (
            f"Look-Up '{lookup_project_name}' [{context_display}] partial success: "
            f"enriched {enriched_count} field(s) in {execution_time_ms}ms - "
            f"{warning_message}"
        )

        self.emit_log(
            level=LogLevel.WARN.value,
            state="PARTIAL",
            message=message,
            lookup_project_name=lookup_project_name,
            enriched_count=enriched_count,
            execution_time_ms=execution_time_ms,
            warning_message=warning_message,
            confidence=confidence,
            context_type=context_type,
        )

    def emit_no_linked_lookups(self) -> None:
        """Emit debug log when no Look-Ups are linked."""
        self.emit_log(
            level=LogLevel.INFO.value,
            state="SKIPPED",
            message="No linked Look-Up projects found",
            lookup_project_name="",
        )

    def emit_orchestration_start(
        self,
        lookup_count: int,
        lookup_names: list[str],
    ) -> None:
        """Emit log when Look-up orchestration starts.

        Args:
            lookup_count: Number of Look-ups to execute
            lookup_names: Names of the Look-up projects
        """
        names_str = ", ".join(lookup_names[:3])
        if len(lookup_names) > 3:
            names_str += f" (+{len(lookup_names) - 3} more)"

        message = f"Starting Look-Up enrichment: {lookup_count} project(s) [{names_str}]"

        self.emit_log(
            level=LogLevel.INFO.value,
            state="STARTED",
            message=message,
            lookup_project_name="",
            lookup_count=lookup_count,
            lookup_names=lookup_names,
        )

    def emit_orchestration_complete(
        self,
        total_lookups: int,
        successful: int,
        failed: int,
        total_time_ms: int,
        total_enriched_fields: int,
    ) -> None:
        """Emit log when Look-up orchestration completes.

        Args:
            total_lookups: Total number of Look-ups executed
            successful: Number of successful Look-ups
            failed: Number of failed Look-ups
            total_time_ms: Total execution time in milliseconds
            total_enriched_fields: Total number of fields enriched
        """
        status = "completed" if failed == 0 else "completed with errors"
        message = (
            f"Look-Up enrichment {status}: {successful}/{total_lookups} succeeded, "
            f"{total_enriched_fields} field(s) enriched in {total_time_ms}ms"
        )

        level = LogLevel.INFO.value if failed == 0 else LogLevel.WARN.value

        self.emit_log(
            level=level,
            state="COMPLETED" if failed == 0 else "PARTIAL",
            message=message,
            lookup_project_name="",
            total_lookups=total_lookups,
            successful=successful,
            failed=failed,
            total_time_ms=total_time_ms,
            total_enriched_fields=total_enriched_fields,
        )
