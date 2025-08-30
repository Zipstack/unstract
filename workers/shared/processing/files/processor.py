"""File Processing Helper for Complex File Operations

This module provides a helper class to break down the extremely complex
_process_file method found in file_processing/tasks.py into manageable,
testable, and maintainable components.

UI/WebSocket Log Icons:
- 🚀 File processing started
- 🔍 Checking cache/history
- 📜 Checking processing history
- ✅ Validating execution status
- ⚡ File found in cache or history (fast path)
- 🚀 Starting AI tool execution
- 🔄 File marked for manual review
- 📤 File marked for destination processing
- 📥 Data inserted into database
- 💾 Files copied to filesystem
- 🔌 File processed via API
- ✅ Processing completed successfully
"""

import json
import time
from typing import Any

from unstract.core.data_models import ExecutionStatus, FileHashData

from ...api.facades.legacy_client import InternalAPIClient
from ...enums import FileDestinationType
from ...infrastructure.logging import WorkerLogger
from ...infrastructure.logging.helpers import (
    log_file_info,
    log_file_processing_error,
    log_file_processing_success,
)
from ...infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from ...workflow.execution.service import WorkerWorkflowExecutionService

logger = WorkerLogger.get_logger(__name__)


class FileProcessingContext:
    """Container for file processing context and state."""

    def __init__(
        self,
        file_data: dict[str, Any],
        file_hash: FileHashData,
        api_client: InternalAPIClient,
        workflow_execution: dict[str, Any],
        workflow_file_execution_id: str = None,
        workflow_file_execution_object: Any = None,
        workflow_logger: WorkerWorkflowLogger = None,
        current_file_idx: int = 1,
        total_files: int = 1,
    ):
        self.file_data = file_data
        self.file_hash = file_hash
        self.api_client = api_client
        self.workflow_execution = workflow_execution
        self.workflow_file_execution_id = workflow_file_execution_id
        self.workflow_file_execution_object = workflow_file_execution_object
        self.workflow_logger = workflow_logger
        self.current_file_idx = current_file_idx
        self.total_files = total_files

        # Extract common identifiers
        if hasattr(file_data, "execution_id"):
            self.execution_id = file_data.execution_id
            self.workflow_id = file_data.workflow_id
            self.organization_id = file_data.organization_id
            self.use_file_history = getattr(file_data, "use_file_history", True)
        else:
            self.execution_id = file_data["execution_id"]
            self.workflow_id = file_data["workflow_id"]
            self.organization_id = file_data["organization_id"]
            self.use_file_history = file_data.get("use_file_history", True)

        self.file_name = file_hash.file_name or "unknown"
        self.file_start_time = time.time()

        logger.info(
            f"[Execution {self.execution_id}] Processing file: '{self.file_name}'"
        )

    @property
    def is_api_workflow(self) -> bool:
        """Check if this is an API workflow based on file path."""
        return self.file_hash.file_path and "/api/" in self.file_hash.file_path

    def get_processing_duration(self) -> float:
        """Get the processing duration in seconds."""
        return time.time() - self.file_start_time


class CachedFileHandler:
    """Handles cached file processing logic."""

    @staticmethod
    def handle_cached_file(context: FileProcessingContext) -> dict[str, Any] | None:
        """Handle already executed (cached) files.

        Args:
            context: File processing context

        Returns:
            Cached result dictionary if found, None otherwise
        """
        if not getattr(context.file_hash, "is_executed", False):
            return None

        logger.info(
            f"File {context.file_name} is already executed (cached), fetching from file_history"
        )

        try:
            cache_key = context.file_hash.file_hash
            if not cache_key:
                logger.warning(
                    f"No cache key available for cached file {context.file_name}"
                )
                return None

            history_result = context.api_client.get_file_history_by_cache_key(
                cache_key=cache_key,
                workflow_id=context.workflow_id,
                file_path=context.file_hash.file_path,
            )

            if not (history_result.get("found") and history_result.get("result")):
                return None

            logger.info(f"✓ Retrieved cached result for {context.file_name}")

            # Parse cached JSON result
            cached_result = json.loads(history_result.get("result", "{}"))
            cached_metadata = json.loads(history_result.get("metadata", "{}"))

            # Update workflow file execution with cached result
            context.api_client.update_file_execution_status(
                file_execution_id=context.workflow_file_execution_id,
                status=ExecutionStatus.COMPLETED.value,
                result=cached_result,
                metadata=cached_metadata,
            )

            return {
                "file": context.file_name,
                "file_execution_id": context.workflow_file_execution_id,
                "error": None,
                "result": cached_result,
                "metadata": cached_metadata,
                "from_cache": True,
            }

        except Exception as cache_error:
            logger.error(
                f"Failed to retrieve cached result for {context.file_name}: {cache_error}"
            )
            return None


class FileHistoryHandler:
    """Handles file history checking and retrieval logic."""

    @staticmethod
    def check_file_history(context: FileProcessingContext) -> dict[str, Any] | None:
        """Check file history for previously processed files.

        Args:
            context: File processing context

        Returns:
            Historical result dictionary if found, None otherwise
        """
        if not context.file_hash.use_file_history:
            return None

        logger.info(
            f"Checking file history for {context.file_name} with use_file_history=True"
        )

        try:
            cache_key = context.file_hash.file_hash
            if not cache_key:
                return None

            # For API workflows, don't pass file_path since execution paths are unique per execution
            lookup_file_path = (
                None if context.is_api_workflow else context.file_hash.file_path
            )

            history_result = context.api_client.get_file_history_by_cache_key(
                cache_key=cache_key,
                workflow_id=context.workflow_id,
                file_path=lookup_file_path,
            )

            if not (history_result.get("found") and history_result.get("file_history")):
                return None

            logger.info(
                f"✓ File {context.file_name} found in history - returning cached result"
            )

            file_history_data = history_result["file_history"]

            # Parse JSON strings from file history
            try:
                result_data = (
                    json.loads(file_history_data.get("result", "{}"))
                    if file_history_data.get("result")
                    else None
                )
                metadata_data = (
                    json.loads(file_history_data.get("metadata", "{}"))
                    if file_history_data.get("metadata")
                    else {"from_cache": True}
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse JSON from file history: {e}")
                result_data = file_history_data.get("result")
                metadata_data = file_history_data.get("metadata", {"from_cache": True})

            cached_file_result = {
                "file": context.file_name,
                "file_execution_id": context.workflow_file_execution_id,
                "error": None,
                "result": result_data,
                "metadata": metadata_data,
                "from_file_history": True,
            }

            # Cache the result for API response if it's an API workflow
            if context.is_api_workflow:
                FileHistoryHandler._cache_api_result(context, cached_file_result)

            return cached_file_result

        except Exception as history_error:
            logger.error(
                f"Failed to check file history for {context.file_name}: {history_error}"
            )
            return None

    @staticmethod
    def _cache_api_result(context: FileProcessingContext, result: dict[str, Any]) -> None:
        """Cache result for API workflows."""
        try:
            workflow_service = WorkerWorkflowExecutionService(
                api_client=context.api_client,
                workflow_id=context.workflow_id,
                organization_id=context.organization_id,
                execution_id=context.execution_id,
                is_api=context.is_api_workflow,
            )
            workflow_id = context.workflow_execution.get("workflow_id")
            execution_id = context.workflow_execution.get("id")

            if workflow_id and execution_id:
                workflow_service.cache_api_result(
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    result=result,
                )
                logger.debug(f"Cached API result for {context.file_name}")

        except Exception as cache_error:
            logger.warning(f"Failed to cache API result: {cache_error}")


class WorkflowFileExecutionHandler:
    """Handles workflow file execution validation and management."""

    @staticmethod
    def validate_workflow_file_execution(
        context: FileProcessingContext,
    ) -> dict[str, Any] | None:
        """Validate and check workflow file execution status.

        Args:
            context: File processing context

        Returns:
            Result if already completed, None if processing should continue

        Raises:
            ValueError: If workflow file execution is not properly configured
        """
        if (
            not context.workflow_file_execution_id
            or not context.workflow_file_execution_object
        ):
            raise ValueError(
                f"No pre-created WorkflowFileExecution provided for file {context.file_hash.file_name}"
            )

        logger.info(
            f"Using pre-created workflow file execution: {context.workflow_file_execution_id}"
        )

        workflow_file_execution = context.workflow_file_execution_object

        if not workflow_file_execution:
            raise Exception("Failed to create workflow file execution")

        # Check if file execution is already completed
        if workflow_file_execution.status == ExecutionStatus.COMPLETED.value:
            logger.info(
                f"File already completed. Skipping execution for execution_id: {context.execution_id}, "
                f"file_execution_id: {workflow_file_execution.id}"
            )

            return {
                "file": context.file_name,
                "file_execution_id": workflow_file_execution.id,
                "error": None,
                "result": getattr(workflow_file_execution, "result", None),
                "metadata": getattr(workflow_file_execution, "metadata", None),
            }

        return None


class ManualReviewHandler:
    """Handles manual review routing logic."""

    @staticmethod
    def check_manual_review_routing(
        context: FileProcessingContext,
    ) -> dict[str, Any] | None:
        """Check if file should be routed to manual review.

        Args:
            context: File processing context

        Returns:
            Manual review result if applicable, None otherwise
        """
        # Check if file is destined for manual review
        if context.file_hash.file_destination == FileDestinationType.MANUALREVIEW.value:
            logger.info(f"File {context.file_name} routed to manual review queue")

            # Log manual review routing to UI
            if context.workflow_logger and context.workflow_file_execution_id:
                log_file_info(
                    context.workflow_logger,
                    context.workflow_file_execution_id,
                    f"🔄 File '{context.file_name}' flagged for MANUAL REVIEW based on destination rules",
                )

            try:
                # Route to manual review queue
                review_result = context.api_client.route_to_manual_review(
                    file_execution_id=context.workflow_file_execution_id,
                    file_data=context.file_hash.to_dict(),
                    workflow_id=context.workflow_id,
                    execution_id=context.execution_id,
                    organization_id=context.organization_id,
                )

                return {
                    "file": context.file_name,
                    "file_execution_id": context.workflow_file_execution_id,
                    "error": None,
                    "result": None,
                    "metadata": {"routed_to_manual_review": True},
                    "manual_review": True,
                    "review_result": review_result,
                }

            except Exception as review_error:
                logger.error(f"Failed to route file to manual review: {review_error}")
                # Fall through to normal processing

        return None

    @staticmethod
    def route_with_results(
        context: FileProcessingContext, workflow_result: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Route file to manual review with tool execution results via plugin.

        Args:
            context: File processing context
            workflow_result: Results from tool execution

        Returns:
            Manual review result with execution data, None if routing failed
        """
        try:
            logger.info(
                f"Routing file {context.file_name} to manual review with execution results via plugin"
            )

            # Delegate to the manual review plugin through the API client facade
            # This will automatically handle plugin availability and fallback to stub
            result = context.api_client.route_to_manual_review_with_results(
                file_execution_id=context.workflow_file_execution_id,
                file_data=context.file_hash.to_dict(),
                workflow_result=workflow_result,
                workflow_id=context.workflow_id,
                execution_id=context.execution_id,
                organization_id=context.organization_id,
                file_name=context.file_name,
            )

            logger.info(
                f"Manual review routing result for {context.file_name}: {result.get('success', False)}"
            )
            return result

        except Exception as review_error:
            logger.error(
                f"Failed to route file to manual review with results: {review_error}"
            )
            return None


class WorkflowExecutionProcessor:
    """Handles the actual workflow execution processing."""

    @staticmethod
    def execute_workflow_processing(context: FileProcessingContext) -> dict[str, Any]:
        """Execute the main workflow processing for the file.

        Args:
            context: File processing context

        Returns:
            Workflow execution result
        """
        try:
            logger.info(f"Starting workflow execution for {context.file_name}")

            # Convert FileHashData to dict for API client
            file_data = context.file_hash.to_dict()
            logger.info("DEBUG: File data converted successfully")

            # CRITICAL FIX: Use the working WorkerWorkflowExecutionService from service.py
            # This service handles all the complex setup needed for tool execution
            logger.info(
                "DEBUG: About to create WorkerWorkflowExecutionService from service.py..."
            )

            working_service = WorkerWorkflowExecutionService(
                api_client=context.api_client
            )
            logger.info("DEBUG: WorkingWorkflowService created successfully")

            # Execute the workflow using the working service implementation
            logger.info(
                f"Starting tool execution for {context.file_name} using working service..."
            )
            execution_result = working_service.execute_workflow_for_file(
                organization_id=context.organization_id,
                workflow_id=context.workflow_id,
                file_data=file_data,
                execution_id=context.execution_id,
                is_api=context.is_api_workflow,
                workflow_file_execution_id=context.workflow_file_execution_id,
                workflow_logger=context.workflow_logger,
            )
            logger.info(
                f"Tool execution completed for {context.file_name}. Result success: {execution_result.get('success')}"
            )

            # CRITICAL FIX: Check if workflow execution actually succeeded
            # WorkflowService returns {"success": False, "error": "..."} for failures
            execution_success = execution_result.get(
                "success", True
            )  # Default True for backward compatibility
            execution_error = execution_result.get("error")

            if not execution_success or execution_error:
                # Workflow execution failed - update file status and return error
                error_message = execution_error or "Workflow execution failed"
                logger.error(
                    f"Workflow execution failed for {context.file_name}: {error_message}"
                )

                # Update file execution status to ERROR
                try:
                    context.api_client.update_file_execution_status(
                        file_execution_id=context.workflow_file_execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=error_message,
                    )
                    logger.info(
                        f"Updated file execution {context.workflow_file_execution_id} status to ERROR"
                    )
                except Exception as status_error:
                    logger.error(
                        f"Failed to update file execution status: {status_error}"
                    )

                return {
                    "file": context.file_name,
                    "file_execution_id": context.workflow_file_execution_id,
                    "error": error_message,
                    "result": None,
                    "metadata": {
                        "error_occurred": True,
                        "workflow_execution_failed": True,
                    },
                    "execution_time": context.get_processing_duration(),
                }

            logger.info(
                f"✓ Workflow execution completed successfully for {context.file_name}"
            )

            return {
                "file": context.file_name,
                "file_execution_id": context.workflow_file_execution_id,
                "error": None,
                "result": execution_result.get("result"),
                "metadata": execution_result.get("metadata", {}),
                "execution_time": context.get_processing_duration(),
            }

        except Exception as execution_error:
            logger.error(
                f"Workflow execution failed for {context.file_name}: {execution_error}"
            )

            # Update file execution status to ERROR
            try:
                context.api_client.update_file_execution_status(
                    file_execution_id=context.workflow_file_execution_id,
                    status=ExecutionStatus.ERROR.value,
                    error_message=str(execution_error),
                )
            except Exception as status_error:
                logger.error(f"Failed to update file execution status: {status_error}")

            return {
                "file": context.file_name,
                "file_execution_id": context.workflow_file_execution_id,
                "error": str(execution_error),
                "result": None,
                "metadata": {"error_occurred": True},
                "execution_time": context.get_processing_duration(),
            }


class FileProcessor:
    """Main file processor orchestrator that coordinates all processing steps."""

    @staticmethod
    def process_file(
        current_file_idx: int,
        total_files: int,
        file_data: dict[str, Any],
        file_hash: FileHashData,
        api_client: InternalAPIClient,
        workflow_execution: dict[str, Any],
        workflow_file_execution_id: str = None,
        workflow_file_execution_object: Any = None,
        workflow_logger: WorkerWorkflowLogger = None,
    ) -> dict[str, Any]:
        """Main orchestrator method that replaces the complex _process_file method.

        This method coordinates the file processing workflow by:
        1. Setting up processing context
        2. Checking for cached results
        3. Checking file history
        4. Validating workflow file execution
        5. Checking manual review routing
        6. Executing workflow processing

        Args:
            current_file_idx: Index of current file
            total_files: Total number of files
            file_data: File data context
            file_hash: FileHashData instance with type-safe access
            api_client: Internal API client
            workflow_execution: Workflow execution context
            workflow_file_execution_id: Pre-created workflow file execution ID
            workflow_file_execution_object: Pre-created workflow file execution object

        Returns:
            File execution result dictionary
        """
        # Create processing context
        context = FileProcessingContext(
            file_data=file_data,
            file_hash=file_hash,
            api_client=api_client,
            workflow_execution=workflow_execution,
            workflow_file_execution_id=workflow_file_execution_id,
            workflow_file_execution_object=workflow_file_execution_object,
            workflow_logger=workflow_logger,
            current_file_idx=current_file_idx,
            total_files=total_files,
        )

        logger.debug(
            f"File processing context created for {context.file_name} "
            f"({current_file_idx + 1}/{total_files})"
        )

        # Send file processing start log to UI
        log_file_info(
            workflow_logger,
            workflow_file_execution_id,
            f"🚀 Starting processing for file '{context.file_name}' ({current_file_idx + 1}/{total_files})",
        )

        # Update file execution status to EXECUTING when processing starts (using common method)
        context.api_client.update_file_status_to_executing(
            context.workflow_file_execution_id, context.file_name
        )

        try:
            # Step 1: Check if file is already executed (cached)
            logger.info(f"DEBUG: Step 1 - Checking cached file for {context.file_name}")
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"🔍 Checking if '{context.file_name}' has been processed before",
            )

            cached_result = CachedFileHandler.handle_cached_file(context)
            if cached_result:
                logger.info(f"Returning cached result for {context.file_name}")
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"⚡ File '{context.file_name}' already processed - using cached results",
                )
                return cached_result

            # Step 2: Validate workflow file execution
            logger.info(
                f"DEBUG: Step 2 - Validating workflow file execution for {context.file_name}"
            )
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"✅ Validating execution status for '{context.file_name}'",
            )

            completed_result = (
                WorkflowFileExecutionHandler.validate_workflow_file_execution(context)
            )
            if completed_result:
                logger.info(f"File already completed: {context.file_name}")
                log_file_processing_success(
                    workflow_logger, workflow_file_execution_id, context.file_name
                )
                return completed_result

            # Step 3: Check file history (if enabled)
            logger.info(f"DEBUG: Step 3 - Checking file history for {context.file_name}")
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"📜 Checking processing history for '{context.file_name}'",
            )

            history_result = FileHistoryHandler.check_file_history(context)
            if history_result:
                logger.info(f"Returning historical result for {context.file_name}")
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"⚡ File '{context.file_name}' found in history cache - using cached results",
                )
                log_file_processing_success(
                    workflow_logger, workflow_file_execution_id, context.file_name
                )
                return history_result

            # Step 4: Execute workflow processing (always run tools first)
            logger.info(
                f"DEBUG: Step 4 - Executing workflow processing for {context.file_name}"
            )
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"🚀 Starting AI tool execution for '{context.file_name}'",
            )

            workflow_result = WorkflowExecutionProcessor.execute_workflow_processing(
                context
            )

            # Step 5: Tool execution completed - destination processing will handle routing
            logger.info(
                f"DEBUG: Step 5 - Tool execution completed for {context.file_name}, destination will handle routing"
            )

            # Send appropriate completion log based on workflow result
            if workflow_result.get("error"):
                log_file_processing_error(
                    workflow_logger,
                    workflow_file_execution_id,
                    context.file_name,
                    workflow_result["error"],
                )
            else:
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"✅ File '{context.file_name}' processing completed, preparing for destination routing",
                )

            # Return workflow results - destination processing will handle manual review routing
            return workflow_result

        except Exception as e:
            logger.error(f"File processing failed for {context.file_name}: {e}")

            # Send file processing error log to UI
            log_file_processing_error(
                workflow_logger, workflow_file_execution_id, context.file_name, str(e)
            )

            # Return error result
            return {
                "file": context.file_name,
                "file_execution_id": context.workflow_file_execution_id,
                "error": str(e),
                "result": None,
                "metadata": {"processing_failed": True},
                "execution_time": context.get_processing_duration(),
            }
