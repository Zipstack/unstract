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

import ast
import json
from typing import Any

from shared.models.file_processing import FileProcessingContext

from unstract.core.data_models import ExecutionStatus, FileHashData, WorkerFileData
from unstract.core.worker_models import FileProcessingResult, WorkflowExecutionResult

from ...api.internal_client import InternalAPIClient
from ...enums import FileDestinationType
from ...infrastructure.logging import WorkerLogger
from ...infrastructure.logging.helpers import (
    log_file_error,
    log_file_info,
    log_file_processing_error,
    log_file_processing_success,
)
from ...infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from ...utils.api_result_cache import get_api_cache_manager
from ...workflow.execution.service import WorkerWorkflowExecutionService

logger = WorkerLogger.get_logger(__name__)


class CachedFileHandler:
    """Handles cached file processing logic with file history support."""

    @staticmethod
    def handle_cached_file(context: FileProcessingContext) -> FileProcessingResult | None:
        """Handle files with file history enabled (cached/historical files).

        Args:
            context: File processing context

        Returns:
            FileProcessingResult if found, None otherwise
        """
        if not context.file_hash.use_file_history:
            return None

        logger.info(
            f"Checking file history for {context.file_name} with use_file_history=True"
        )

        try:
            cache_key = context.file_hash.file_hash
            if not cache_key:
                logger.warning(f"No cache key available for file {context.file_name}")
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

            # Handle both legacy format (result field) and new format (file_history field)
            if history_result.get("found") and history_result.get("file_history"):
                # Legacy format - direct result field
                logger.info(f"✓ Retrieved cached result for {context.file_name}")

                file_history_data = history_result.get("file_history")

                if not file_history_data:
                    logger.warning(
                        f"No file history data available for file {context.file_name}"
                    )
                    return FileProcessingResult(
                        file_name=context.file_name,
                        file_execution_id=context.workflow_file_execution_id,
                        success=False,
                        error="No file history result available",
                        result=None,
                        metadata=None,
                        from_cache=True,
                    )

                # Parse cached JSON result
                try:
                    cached_result = json.loads(file_history_data.get("result", "{}"))
                except json.JSONDecodeError:
                    try:
                        cached_result = ast.literal_eval(
                            file_history_data.get("result", "{}")
                        )
                    except (ValueError, SyntaxError) as ast_error:
                        logger.warning(
                            f"Failed to parse result with both JSON and ast: {ast_error}"
                        )
                        cached_result = file_history_data.get("result", "{}")

                try:
                    cached_metadata = json.loads(file_history_data.get("metadata", "{}"))
                except json.JSONDecodeError:
                    try:
                        cached_metadata = ast.literal_eval(
                            file_history_data.get("metadata", "{}")
                        )
                    except (ValueError, SyntaxError) as ast_error:
                        logger.warning(
                            f"Failed to parse metadata with both JSON and ast: {ast_error}"
                        )
                        cached_metadata = file_history_data.get("metadata", "{}")

                logger.info(
                    f"✓ Cached cached_metadata {cached_metadata} for {context.file_name}"
                )
                return FileProcessingResult(
                    file_name=context.file_name,
                    file_execution_id=context.workflow_file_execution_id,
                    success=True,
                    error=None,
                    result=cached_result,
                    metadata=cached_metadata,
                    from_file_history=True,
                )

            return None

        except Exception as history_error:
            logger.error(
                f"Failed to check file history for {context.file_name}: {history_error}"
            )
            return None


class WorkflowFileExecutionHandler:
    """Handles workflow file execution validation and management."""

    @staticmethod
    def validate_workflow_file_execution(
        context: FileProcessingContext,
    ) -> FileProcessingResult | None:
        """Validate and check workflow file execution status.

        Args:
            context: File processing context

        Returns:
            FileProcessingResult if already completed, None if processing should continue

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

        # workflow_file_execution_object is guaranteed to be truthy (validated above)
        workflow_file_execution = context.workflow_file_execution_object

        # Check if file execution is already completed
        if workflow_file_execution.status == ExecutionStatus.COMPLETED.value:
            logger.info(
                f"File already completed. Skipping execution for execution_id: {context.execution_id}, "
                f"file_execution_id: {workflow_file_execution.id}"
            )

            return FileProcessingResult(
                file_name=context.file_name,
                file_execution_id=workflow_file_execution.id,
                success=True,
                error=None,
                result=getattr(workflow_file_execution, "result", None),
                metadata=getattr(workflow_file_execution, "metadata", None) or {},
            )

        return None


class ManualReviewHandler:
    """Handles manual review routing logic."""

    @staticmethod
    def check_manual_review_routing(
        context: FileProcessingContext,
    ) -> FileProcessingResult | None:
        """Check if file should be routed to manual review.

        Args:
            context: File processing context

        Returns:
            FileProcessingResult if applicable, None otherwise
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

                return FileProcessingResult(
                    file_name=context.file_name,
                    file_execution_id=context.workflow_file_execution_id,
                    success=True,
                    error=None,
                    result=None,
                    metadata={"routed_to_manual_review": True},
                    manual_review=True,
                    review_result=review_result,
                )

            except Exception as review_error:
                logger.error(f"Failed to route file to manual review: {review_error}")
                # Fall through to normal processing

        return None

    @staticmethod
    def route_with_results(
        context: FileProcessingContext, workflow_result: FileProcessingResult
    ) -> FileProcessingResult | None:
        """Route file to manual review with tool execution results via plugin.

        Args:
            context: File processing context
            workflow_result: FileProcessingResult from tool execution

        Returns:
            FileProcessingResult with execution data, None if routing failed
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
                workflow_result=workflow_result.to_dict(),
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
    def execute_workflow_processing(
        context: FileProcessingContext,
    ) -> FileProcessingResult:
        """Execute the main workflow processing for the file.

        Args:
            context: File processing context

        Returns:
            Workflow execution result
        """
        try:
            logger.info(f"Starting workflow execution for {context.file_name}")

            working_service = WorkerWorkflowExecutionService(
                api_client=context.api_client
            )

            # Execute the workflow using the working service implementation
            logger.info(
                f"Starting tool execution for {context.file_name} using working service..."
            )
            execution_result: WorkflowExecutionResult = (
                working_service.execute_workflow_for_file(
                    file_processing_context=context,
                    organization_id=context.organization_id,
                    workflow_id=context.workflow_id,
                    execution_id=context.execution_id,
                    is_api=context.is_api_workflow,
                    use_file_history=context.use_file_history,
                    workflow_file_execution_id=context.workflow_file_execution_id,
                    workflow_logger=context.workflow_logger,
                )
            )
            logger.info(
                f"Tool execution completed for {context.file_name}. Result success: {execution_result.success}"
            )

            if not execution_result.success or execution_result.error:
                # Workflow execution failed - update file status and return error
                error_message = execution_result.error or "Workflow execution failed"
                logger.error(
                    f"Tool processing failed for {context.file_name}: {error_message}"
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

                return FileProcessingResult(
                    file_name=context.file_name,
                    file_execution_id=context.workflow_file_execution_id,
                    success=False,
                    error=error_message,
                    result=None,
                    metadata={
                        "error_occurred": True,
                        "workflow_execution_failed": True,
                    },
                    execution_time=context.get_processing_duration(),
                )

            logger.info(
                f"✓ Workflow execution completed successfully for {context.file_name}"
            )

            # Check if this was a duplicate skip (destination not processed due to duplicate detection)
            destination_processed = (
                execution_result.metadata.destination_processed
                if execution_result.metadata
                else False
            )
            destination_error = (
                execution_result.metadata.destination_error
                if execution_result.metadata
                else None
            )

            # Duplicate detection: destination not processed AND no error
            is_duplicate = not destination_processed and not destination_error

            return FileProcessingResult(
                file_name=context.file_name,
                file_execution_id=context.workflow_file_execution_id,
                success=True,
                error=None,
                result=execution_result.result,
                metadata=execution_result.metadata.to_dict()
                if execution_result.metadata
                else {},
                execution_time=context.get_processing_duration(),
                destination_processed=destination_processed,
                destination_error=destination_error,
                is_duplicate_skip=is_duplicate,
            )

        except Exception as execution_error:
            logger.error(
                f"File processing failed for {context.file_name}: {execution_error}",
                exc_info=True,
            )

            # Update file execution status to ERROR
            try:
                context.api_client.update_file_execution_status(
                    file_execution_id=context.workflow_file_execution_id,
                    status=ExecutionStatus.ERROR.value,
                    error_message=str(execution_error),
                )
            except Exception as status_error:
                logger.error(
                    f"Failed to update file execution status: {status_error}",
                    exc_info=True,
                )

            return FileProcessingResult(
                file_name=context.file_name,
                file_execution_id=context.workflow_file_execution_id,
                success=False,
                error=str(execution_error),
                result=None,
                metadata={"error_occurred": True},
                execution_time=context.get_processing_duration(),
            )


class FileProcessor:
    """Main file processor orchestrator that coordinates all processing steps."""

    @staticmethod
    def process_file(
        current_file_idx: int,
        total_files: int,
        file_data: WorkerFileData,
        file_hash: FileHashData,
        api_client: InternalAPIClient,
        workflow_execution: dict[str, Any],
        workflow_file_execution_id: str = None,
        workflow_file_execution_object: Any = None,
        workflow_logger: WorkerWorkflowLogger = None,
    ) -> FileProcessingResult:
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
            FileProcessingResult dataclass
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
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"🔍 Checking if '{context.file_name}' has been processed before",
            )

            cached_result = CachedFileHandler.handle_cached_file(context)
            if cached_result and not context.is_api_workflow:
                logger.info(f"Returning cached result for {context.file_name}")
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"⚡ File '{context.file_name}' already processed - Skipping processing",
                )
                return cached_result

            if cached_result and context.is_api_workflow and context.use_file_history:
                logger.info(f"Returning cached result for {context.file_name}")
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"⚡ File '{context.file_name}' already processed - using cached results",
                )

                # Cache the file history result as API result with clean metadata format
                try:
                    api_cache_manager = get_api_cache_manager()
                    api_cache_manager.cache_file_history_result_for_api(
                        file_processing_result=cached_result,
                        workflow_id=context.workflow_id,
                        execution_id=context.execution_id,
                        organization_id=context.organization_id,
                        file_hash=context.file_hash,
                    )
                    logger.info(
                        f"Successfully cached API result for file history file {context.file_name}"
                    )
                except Exception as cache_error:
                    logger.warning(
                        f"Failed to cache API result for file history file {context.file_name}: {cache_error}"
                    )
                    # Continue execution - caching failure shouldn't stop processing

                return cached_result

            # Step 2: Validate workflow file execution
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
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"📜 Checking processing history for '{context.file_name}'",
            )

            # Step 4: Execute workflow processing (always run tools first)
            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"🚀 Starting tool execution for '{context.file_name}'",
            )

            workflow_result = WorkflowExecutionProcessor.execute_workflow_processing(
                context
            )

            log_file_info(
                workflow_logger,
                workflow_file_execution_id,
                f"✅ Tool execution completed for '{context.file_name}'",
            )

            # Step 5: Tool execution completed - destination processing will handle routing
            # Send appropriate completion log based on workflow result
            if workflow_result.error:
                log_file_processing_error(
                    workflow_logger,
                    workflow_file_execution_id,
                    context.file_name,
                    workflow_result.error,
                )
            else:
                # Check if destination processing failed
                destination_error = workflow_result.destination_error
                destination_processed = workflow_result.destination_processed
                is_duplicate_skip = getattr(workflow_result, "is_duplicate_skip", False)

                if destination_error or not destination_processed:
                    # Skip UI error log and DB updates for duplicates (internal race condition, not user error)
                    if not is_duplicate_skip:
                        # Log destination failure to UI
                        error_msg = destination_error or "Destination processing failed"
                        log_file_error(
                            workflow_logger,
                            workflow_file_execution_id,
                            f"❌ File '{context.file_name}' destination processing failed: {error_msg}",
                        )

                        # Update file execution status to ERROR
                        logger.info(
                            f"Updating file execution status to ERROR for {context.workflow_file_execution_id} due to destination failure"
                        )
                        try:
                            context.api_client.update_file_execution_status(
                                file_execution_id=context.workflow_file_execution_id,
                                status=ExecutionStatus.ERROR.value,
                                error_message=error_msg,
                            )
                            logger.info(
                                f"Updated file execution {context.workflow_file_execution_id} status to ERROR"
                            )
                        except Exception as status_error:
                            logger.error(
                                f"Failed to update file execution status: {status_error}"
                            )

                        # Update workflow result since destination failed
                        workflow_result.success = False
                        workflow_result.error = error_msg
                    else:
                        # Debug log for duplicate detection (internal use only)
                        logger.info(
                            f"DUPLICATE SKIP: File '{context.file_name}' identified as duplicate in processor. "
                            f"destination_processed=False, destination_error=None, "
                            f"file_execution_id={context.workflow_file_execution_id}. "
                            f"Skipping UI error log and status updates - this is an internal race condition, not a user-facing error. "
                            f"First worker will handle all status updates."
                        )
                else:
                    log_file_info(
                        workflow_logger,
                        workflow_file_execution_id,
                        f"✅ File '{context.file_name}' processing completed, preparing for destination routing",
                    )

            # Return workflow results - destination processing will handle API caching and manual review routing
            return workflow_result

        except Exception as e:
            logger.error(f"File processing failed for {context.file_name}: {e}")

            # Send file processing error log to UI
            log_file_processing_error(
                workflow_logger, workflow_file_execution_id, context.file_name, str(e)
            )

            # Return error result
            error_result = FileProcessingResult(
                file_name=context.file_name,
                file_execution_id=context.workflow_file_execution_id,
                success=False,
                error=str(e),
                result=None,
                metadata={"processing_failed": True},
                execution_time=context.get_processing_duration(),
            )

            # Cache API error result for API workflows with clean metadata format
            if context.is_api_workflow:
                try:
                    api_cache_manager = get_api_cache_manager()
                    api_cache_manager.cache_error_result_for_api(
                        file_processing_result=error_result,
                        workflow_id=context.workflow_id,
                        execution_id=context.execution_id,
                        organization_id=context.organization_id,
                        file_hash=context.file_hash,
                    )
                    logger.info(
                        f"Successfully cached API error result for file {context.file_name}"
                    )
                except Exception as cache_error:
                    logger.warning(
                        f"Failed to cache API error result for file {context.file_name}: {cache_error}"
                    )
                    # Continue execution - caching failure shouldn't stop processing

            return error_result
