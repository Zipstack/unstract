"""File Processing Worker Tasks

Exact implementation matching Django backend patterns for file processing tasks.
Uses WorkflowExecutionService pattern exactly like the Django backend.
This replaces the heavy Django process_file_batch task with API-based coordination.
"""

import json
import os
import time
from typing import Any

# Import shared worker infrastructure
from shared.api import InternalAPIClient

# Import from shared worker modules
from shared.constants import Account

# Import shared enums and dataclasses
from shared.enums import ErrorType
from shared.enums.task_enums import TaskName
from shared.infrastructure import create_api_client
from shared.infrastructure.context import StateStore
from shared.infrastructure.logging import (
    WorkerLogger,
    WorkerWorkflowLogger,
    log_context,
    monitor_performance,
    with_execution_context,
)
from shared.infrastructure.logging.helpers import (
    log_file_info,
    log_file_processing_error,
    log_file_processing_start,
    log_file_processing_success,
)
from shared.models.execution_models import (
    WorkflowContextData,
    create_organization_context,
)
from shared.processing.files.processor import FileProcessor

# Import manual review service with WorkflowUtil access
from worker import app

from unstract.core.data_models import (
    ExecutionStatus,
    FileBatchData,
    FileBatchResult,
    FileHashData,
    PreCreatedFileData,
    WorkerFileData,
)
from unstract.core.worker_models import FileProcessingResult

logger = WorkerLogger.get_logger(__name__)

# Constants
APPLICATION_OCTET_STREAM = "application/octet-stream"


def _calculate_manual_review_requirements(
    file_batch_data: dict[str, Any], api_client: InternalAPIClient
) -> dict[int, bool]:
    """Calculate manual review requirements for Django compatibility task.

    This function replicates the MRQ logic from @workers/general for files
    coming from the Django backend that lack manual review flags.

    Args:
        file_batch_data: File batch data from Django backend
        api_client: API client for backend communication

    Returns:
        Dictionary mapping file numbers to is_manualreview_required flags
    """
    try:
        # Get basic info from batch data
        files = file_batch_data.get("files", [])
        file_data = file_batch_data.get("file_data", {})

        if not files:
            logger.info("No files found, skipping MRQ calculation")
            return {}

        # Check if Django backend already provides q_file_no_list
        q_file_no_list = file_data.get("q_file_no_list", [])

        if not q_file_no_list:
            logger.info("No q_file_no_list found in file_data, skipping MRQ calculation")
            return {}

        # Use Django backend's pre-calculated q_file_no_list
        logger.info(
            f"Django compatibility: Using provided q_file_no_list with {len(q_file_no_list)} files "
            f"selected from {len(files)} total files for manual review"
        )

        # Create mapping of file numbers to manual review requirements
        mrq_flags = {}
        for file_item in files:
            # Handle different file item formats (tuple, list, dict)
            if len(file_item) < 2:
                continue

            file_number = file_item[1].get("file_number")

            if not file_number:
                continue

            is_manual_review_required = file_number in q_file_no_list
            mrq_flags[file_number] = is_manual_review_required

            logger.debug(
                f"File #{file_number}: is_manualreview_required={is_manual_review_required}"
            )

        return mrq_flags

    except Exception as e:
        logger.error(f"Error calculating manual review requirements: {e}", exc_info=True)
        # Return empty dict so files proceed without manual review flags
        return {}


def _enhance_batch_with_mrq_flags(
    file_batch_data: dict[str, Any], mrq_flags: dict[int, bool]
) -> None:
    """Enhance file batch data with manual review flags.

    Args:
        file_batch_data: File batch data to enhance (modified in place)
        mrq_flags: Dictionary mapping file numbers to is_manualreview_required flags
    """
    try:
        files = file_batch_data.get("files", [])

        if not files:
            logger.warning(
                "Django compatibility: No files found in batch data, skipping MRQ flag enhancement"
            )
            return

        if not mrq_flags:
            logger.info(
                "Django compatibility: No MRQ flags provided, all files will proceed without manual review"
            )
            # Set all files to not require manual review
            for file_item in files:
                if isinstance(file_item, (tuple, list)) and len(file_item) >= 2:
                    file_hash_dict = file_item[1]
                    if isinstance(file_hash_dict, dict):
                        file_hash_dict["is_manualreview_required"] = False
                elif isinstance(file_item, dict):
                    file_item["is_manualreview_required"] = False
            return

        manual_review_count = 0
        total_files = len(files)

        for file_item in files:
            try:
                # Handle different file item formats consistently with calculation function
                if isinstance(file_item, (tuple, list)) and len(file_item) >= 2:
                    # Format: (file_name, file_hash_dict)
                    file_name, file_hash_dict = file_item[0], file_item[1]
                    if isinstance(file_hash_dict, dict):
                        file_number = file_hash_dict.get("file_number", 1)
                        is_manual_review_required = mrq_flags.get(file_number, False)
                        file_hash_dict["is_manualreview_required"] = (
                            is_manual_review_required
                        )

                        if is_manual_review_required:
                            manual_review_count += 1
                            logger.debug(
                                f"Django compatibility: File '{file_name}' #{file_number} marked for manual review"
                            )
                    else:
                        logger.warning(
                            f"Django compatibility: Invalid file hash dict format for file {file_name}"
                        )

                elif isinstance(file_item, dict):
                    # Format: {file_name: "...", file_number: ...}
                    file_number = file_item.get("file_number", 1)
                    is_manual_review_required = mrq_flags.get(file_number, False)
                    file_item["is_manualreview_required"] = is_manual_review_required

                    if is_manual_review_required:
                        manual_review_count += 1
                        file_name = file_item.get("file_name", f"file_{file_number}")
                        logger.debug(
                            f"Django compatibility: File '{file_name}' #{file_number} marked for manual review"
                        )
                else:
                    logger.warning(
                        f"Django compatibility: Unknown file item format: {type(file_item)}, skipping MRQ flag enhancement"
                    )

            except Exception as file_error:
                logger.warning(
                    f"Django compatibility: Failed to enhance MRQ flag for file item {file_item}: {file_error}"
                )
                continue

        logger.info(
            f"Django compatibility: Enhanced {total_files} files with MRQ flags. "
            f"{manual_review_count} files marked for manual review, "
            f"{total_files - manual_review_count} files will proceed directly to destination."
        )

    except Exception as e:
        logger.error(
            f"Django compatibility: Failed to enhance batch with MRQ flags: {e}",
            exc_info=True,
        )


def _process_file_batch_core(
    task_instance, file_batch_data: dict[str, Any]
) -> dict[str, Any]:
    """Core implementation of file batch processing.

    This function contains the actual processing logic that both the new task
    and Django compatibility task will use.

    Args:
        task_instance: The Celery task instance (self)
        file_batch_data: Dictionary that will be converted to FileBatchData dataclass

    Returns:
        Dictionary with successful_files and failed_files counts
    """
    celery_task_id = (
        task_instance.request.id if hasattr(task_instance, "request") else "unknown"
    )

    # Step 1: Validate and parse input data
    batch_data = _validate_and_parse_batch_data(file_batch_data)

    # Step 2: Setup execution context
    context = _setup_execution_context(batch_data, celery_task_id)

    # Step 3: Handle manual review logic
    # context = _handle_manual_review_logic(context)

    # Step 4: Pre-create file executions
    context = _refactored_pre_create_file_executions(context)

    # Step 5: Process individual files
    context = _process_individual_files(context)

    # Step 7: Compile and return final result
    return _compile_batch_result(context)


@app.task(
    bind=True,
    name=TaskName.PROCESS_FILE_BATCH,
    max_retries=0,  # Match Django backend pattern
    ignore_result=False,  # Result is passed to the callback task
    retry_backoff=True,
    retry_backoff_max=500,  # Match Django backend
    retry_jitter=True,
    default_retry_delay=5,  # Match Django backend
    # Timeout inherited from global Celery config (FILE_PROCESSING_TASK_TIME_LIMIT env var)
)
@monitor_performance
def process_file_batch(self, file_batch_data: dict[str, Any]) -> dict[str, Any]:
    """Process a batch of files in parallel using Celery.

    This is the main task entry point for new workers.

    Args:
        file_batch_data: Dictionary that will be converted to FileBatchData dataclass

    Returns:
        Dictionary with successful_files and failed_files counts
    """
    return _process_file_batch_core(self, file_batch_data)


def _validate_and_parse_batch_data(file_batch_data: dict[str, Any]) -> FileBatchData:
    """Validate and parse input data into typed dataclass.

    Args:
        file_batch_data: Raw input dictionary

    Returns:
        Validated FileBatchData instance

    Raises:
        ValueError: If data structure is invalid
        RuntimeError: If unexpected parsing error occurs
    """
    try:
        batch_data = FileBatchData.from_dict(file_batch_data)
        logger.info(
            f"Successfully parsed FileBatchData with {len(batch_data.files)} files"
        )
        return batch_data
    except (TypeError, ValueError) as e:
        logger.error(f"FileBatchData validation failed: {str(e)}")
        logger.error(
            f"Input data structure: keys={list(file_batch_data.keys()) if isinstance(file_batch_data, dict) else 'not a dict'}"
        )
        raise ValueError(
            f"Invalid file batch data structure: {str(e)}. "
            f"Expected dict with 'files' (list) and 'file_data' (dict) fields."
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error parsing file batch data: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to parse file batch data: {str(e)}") from e


def _setup_execution_context(
    batch_data: FileBatchData, celery_task_id: str
) -> WorkflowContextData:
    """Setup execution context with validation and API client initialization.

    Args:
        batch_data: Validated batch data
        celery_task_id: Celery task ID for tracking

    Returns:
        WorkflowContextData containing type-safe execution context

    Raises:
        ValueError: If required context fields are missing
    """
    # Extract context using dataclass
    file_data = batch_data.file_data
    files = batch_data.files
    execution_id = file_data.execution_id
    workflow_id = file_data.workflow_id
    organization_id = file_data.organization_id

    # Validate required context
    if not execution_id or not workflow_id or not organization_id:
        raise ValueError(
            f"Invalid execution context: execution_id='{execution_id}', "
            f"workflow_id='{workflow_id}', organization_id='{organization_id}'"
        )

    logger.info(
        f"[Celery Task: {celery_task_id}] Processing {len(files)} files for execution {execution_id[:8]}..."
    )

    # Set organization context exactly like Django backend
    StateStore.set(Account.ORGANIZATION_ID, organization_id)

    # Create organization-scoped API client using factory pattern
    api_client = create_api_client(organization_id)

    # Create organization context
    org_context = create_organization_context(organization_id, api_client)

    logger.info(
        f"Initializing file batch processing for execution {execution_id}, organization {organization_id}"
    )

    # Get workflow execution context
    execution_response = api_client.get_workflow_execution(execution_id)
    if not execution_response.success:
        raise Exception(f"Failed to get execution context: {execution_response.error}")
    execution_context = execution_response.data
    workflow_execution = execution_context.get("execution", {})

    # Set LOG_EVENTS_ID in StateStore for WebSocket messaging (critical for UI logs)
    # This enables the WorkerWorkflowLogger to send logs to the UI via WebSocket
    execution_log_id = workflow_execution.get("execution_log_id")
    if execution_log_id:
        # Set LOG_EVENTS_ID like backend Celery workers do
        StateStore.set("LOG_EVENTS_ID", execution_log_id)
        logger.info(f"Set LOG_EVENTS_ID for WebSocket messaging: {execution_log_id}")
    else:
        logger.warning(
            f"No execution_log_id found for execution {execution_id}, WebSocket logs may not be delivered"
        )

    # Update execution status to EXECUTING when processing starts
    # This fixes the missing EXECUTION status in logs
    try:
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.EXECUTING.value,
        )
        logger.info(f"Updated workflow execution {execution_id} status to EXECUTING")
    except Exception as status_error:
        logger.warning(f"Failed to update execution status to EXECUTING: {status_error}")

    # Initialize WebSocket logger for UI logs
    from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger

    workflow_logger = WorkerWorkflowLogger.create_for_file_processing(
        execution_id=execution_id,
        organization_id=organization_id,
        pipeline_id=getattr(file_data, "pipeline_id", None)
        if hasattr(file_data, "pipeline_id")
        else None,
    )

    # Send initial workflow logs to UI
    workflow_logger.publish_initial_workflow_logs(len(files))

    # Set log events ID in StateStore like Django backend
    log_events_id = workflow_execution.get("execution_log_id")
    if log_events_id:
        StateStore.set("LOG_EVENTS_ID", log_events_id)

    # Get workflow name and type from execution context
    workflow_name = workflow_execution.get("workflow_name", f"workflow-{workflow_id}")
    workflow_type = workflow_execution.get("workflow_type", "TASK")

    # Get use_file_history from execution parameters (passed from API request)
    # This is the correct behavior - use_file_history should come from the API request, not workflow config
    # file_data is a WorkerFileData dataclass, so we can access use_file_history directly
    try:
        use_file_history = file_data.use_file_history
        logger.info(
            f"File history from execution parameters for workflow {workflow_id}: use_file_history = {use_file_history}"
        )
    except AttributeError as e:
        logger.warning(
            f"Failed to access use_file_history from dataclass, trying dict access: {e}"
        )
        # Fallback to dict access for backward compatibility
        if hasattr(file_data, "get"):
            use_file_history = file_data.get("use_file_history", True)
        else:
            use_file_history = getattr(file_data, "use_file_history", True)
        logger.info(
            f"File history from fallback access for workflow {workflow_id}: use_file_history = {use_file_history}"
        )

    # Create type-safe workflow context
    context_data = WorkflowContextData(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        workflow_type=workflow_type,
        execution_id=execution_id,
        organization_context=org_context,
        files={
            f"file_{i}": file for i, file in enumerate(files)
        },  # Convert list to dict format
        settings={
            "use_file_history": use_file_history,
            "celery_task_id": celery_task_id,
        },
        metadata={
            "batch_data": batch_data,
            "file_data": file_data,
            "result": FileBatchResult(),
            "successful_files_for_manual_review": [],
            "execution_context": execution_context,
            "workflow_execution": workflow_execution,
            "total_files": len(files),
            "workflow_logger": workflow_logger,
        },
        is_scheduled=False,
    )

    return context_data


def _refactored_pre_create_file_executions(
    context: WorkflowContextData,
) -> WorkflowContextData:
    """Pre-create all WorkflowFileExecution records to prevent duplicates.

    Args:
        context: Workflow context data

    Returns:
        Updated context with pre-created file execution data
    """
    files = list(context.files.values())  # Convert dict back to list
    workflow_id = context.workflow_id
    execution_id = context.execution_id
    api_client = context.organization_context.api_client
    workflow_type = context.workflow_type
    is_api_workflow = context.metadata.get("is_api_workflow", False)
    file_data = context.metadata.get("file_data")

    # CRITICAL: Pre-create all WorkflowFileExecution records to prevent duplicates
    # This matches the backend's _pre_create_file_executions pattern for ALL workflow types
    # Includes double safeguard: database check for active files
    workflow_logger = context.metadata.get("workflow_logger")
    (
        pre_created_file_executions,
        skipped_already_completed,
        skipped_active_duplicate,
    ) = _pre_create_file_executions(
        file_data=file_data,
        files=files,
        workflow_id=workflow_id,
        execution_id=execution_id,
        api_client=api_client,
        workflow_type=workflow_type,
        is_api=is_api_workflow,
        use_file_history=context.get_setting("use_file_history", True),
        workflow_logger=workflow_logger,
    )
    logger.info(
        f"Pre-created {len(pre_created_file_executions)} WorkflowFileExecution records for {workflow_type} workflow "
        f"(skipped {len(skipped_already_completed)} already completed, {len(skipped_active_duplicate)} active duplicates)"
    )

    # Add to metadata
    context.pre_created_file_executions = pre_created_file_executions
    context.metadata["skipped_already_completed"] = skipped_already_completed
    context.metadata["skipped_active_duplicate"] = skipped_active_duplicate

    return context


def _process_individual_files(context: WorkflowContextData) -> WorkflowContextData:
    """Process each file individually through the workflow.

    Args:
        context: Workflow context data

    Returns:
        Updated context with processing results
    """
    files = list(context.files.values())  # Convert dict back to list
    file_data = context.metadata["file_data"]
    # CRITICAL FIX: Use q_file_no_list from context metadata for manual review decisions
    # q_file_no_list = context.metadata.get("q_file_no_list", set())
    use_file_history = context.get_setting("use_file_history", True)
    api_client = context.organization_context.api_client
    workflow_execution = context.metadata["workflow_execution"]
    pre_created_file_executions = context.pre_created_file_executions
    skipped_already_completed = context.metadata.get("skipped_already_completed", [])
    skipped_active_duplicate = context.metadata.get("skipped_active_duplicate", [])
    result = context.metadata["result"]
    successful_files_for_manual_review = context.metadata[
        "successful_files_for_manual_review"
    ]
    celery_task_id = context.get_setting("celery_task_id", "unknown")
    total_files = context.metadata["total_files"]

    # Process each file - handle list, tuple, and dictionary formats
    for file_number, file_item in enumerate(files, 1):
        # Handle Django list format (from asdict serialization), tuple format, and dictionary format
        if isinstance(file_item, list):
            # Django backend format after asdict(): [file_name, file_hash_dict]
            if len(file_item) != 2:
                logger.error(
                    f"Invalid file item list length: expected 2, got {len(file_item)}"
                )
                result.increment_failure()
                continue
            file_name, file_hash_dict = file_item
        elif isinstance(file_item, tuple):
            # Legacy tuple format: (file_name, file_hash_dict)
            file_name, file_hash_dict = file_item
        elif isinstance(file_item, dict):
            # Dictionary format: {"file_name": "...", "file_path": "...", ...}
            file_name = file_item.get("file_name")
            file_hash_dict = file_item  # The entire dict is the file hash data
        else:
            logger.error(f"Unexpected file item format: {type(file_item)}")
            result.increment_failure()
            continue

        pre_created_file_execution = pre_created_file_executions.get(file_name)

        if not pre_created_file_execution:
            # Check if this file was intentionally skipped as a duplicate
            # Construct identifier from file_hash_dict to match skipped_files format
            provider_uuid = file_hash_dict.get("provider_file_uuid")
            file_path = file_hash_dict.get("file_path")
            if provider_uuid and file_path:
                file_identifier = f"{provider_uuid}:{file_path}"
                # Check both skip lists and handle differently
                if file_identifier in skipped_already_completed:
                    # File already COMPLETED in this execution - duplicate prevention worked
                    logger.info(
                        f"File '{file_name}' already completed in this execution - skipping (not a failure)"
                    )
                    # Don't increment failure - file is done, duplicate prevention worked
                    continue
                elif file_identifier in skipped_active_duplicate:
                    # File ACTIVE in different execution - user error (concurrent submission)
                    logger.info(
                        f"File '{file_name}' active in another execution - marked as ERROR (counted as failure)"
                    )
                    # Increment failure - this IS a user error (submitting same file to multiple executions)
                    result.increment_failure()
                    continue

            # Truly missing - this is an error condition
            logger.error(
                f"No pre-created WorkflowFileExecution found for file '{file_name}' - unexpected error"
            )
            result.increment_failure()
            continue

        file_hash: FileHashData = pre_created_file_execution.file_hash
        if not file_hash:
            logger.error(f"File hash not found for file '{file_name}'")
            result.increment_failure()
            continue

        logger.info(
            f"[{celery_task_id}][{file_number}/{total_files}] Processing file '{file_name}'"
        )

        # Track individual file processing time
        import time

        file_start_time = time.time()
        logger.info(
            f"TIMING: File processing START for {file_name} at {file_start_time:.6f}"
        )

        # DEBUG: Log the file hash data being sent to ensure unique identification
        logger.info(
            f"File hash data for {file_name}: provider_file_uuid='{file_hash.provider_file_uuid}', file_path='{file_hash.file_path}'"
        )

        # CRITICAL FIX: Preserve original file_number from source, don't override with batch enumeration
        original_file_number = (
            file_hash_dict.get("file_number") if file_hash_dict else None
        )
        if original_file_number is not None:
            # Use the original file number assigned in source connector (global numbering)
            file_hash.file_number = original_file_number
            logger.info(
                f"Using original global file_number {original_file_number} for '{file_name}' (batch position {file_number})"
            )
        else:
            # Fallback to batch enumeration if original file number not available
            file_hash.file_number = file_number
            logger.warning(
                f"No original file_number found for '{file_name}', using batch position {file_number}"
            )

        # Set use_file_history flag based on workflow determination
        file_hash.use_file_history = use_file_history

        # Don't Remove These Comments
        # CRITICAL FIX: Apply manual review decision using q_file_no_list with correct global file number
        # Get WorkflowUtil via manual review service factory (handles plugin registry automatically)
        # manual_review_service = get_manual_review_service(
        #     api_client=api_client, organization_id=context.organization_context.organization_id
        # )
        # workflow_util = manual_review_service.get_workflow_util()
        # file_hash = workflow_util.add_file_destination_filehash(
        #     file_hash.file_number, q_file_no_list, file_hash
        # )

        # Log manual review decision
        if file_hash.is_manualreview_required:
            logger.info(
                f"👥 File {file_name} (#{file_hash.file_number}) MARKED FOR MANUAL REVIEW - destination: {file_hash.file_destination}"
            )
        else:
            logger.info(
                f"File {file_name} (#{file_hash.file_number}) marked for destination processing - destination: {getattr(file_hash, 'file_destination', 'destination')}"
            )

        logger.debug(f"File hash for file {file_name}: {file_hash}")

        # Get pre-created WorkflowFileExecution data

        workflow_file_execution_id = pre_created_file_execution.id
        workflow_file_execution_object = pre_created_file_execution.object

        # Send file processing start log to UI with file_execution_id
        workflow_logger = context.metadata.get("workflow_logger")
        log_file_processing_start(
            workflow_logger,
            workflow_file_execution_id,
            file_name,
            file_number,
            total_files,
        )

        # Send destination routing UI log now that we have workflow_logger and file_execution_id
        if workflow_logger and workflow_file_execution_id:
            if file_hash.is_manualreview_required:
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"🔄 File '{file_name}' marked for MANUAL REVIEW - sending to review queue",
                )
            else:
                log_file_info(
                    workflow_logger,
                    workflow_file_execution_id,
                    f"📤 File '{file_name}' marked for DESTINATION processing",
                )

        # Process single file using Django-like pattern but with API coordination
        file_execution_result = _process_file(
            current_file_idx=file_number,
            total_files=total_files,
            file_data=file_data,
            file_hash=file_hash,
            api_client=api_client,
            workflow_execution=workflow_execution,
            workflow_file_execution_id=workflow_file_execution_id,  # Pass pre-created ID
            workflow_file_execution_object=workflow_file_execution_object,  # Pass pre-created object
            workflow_logger=workflow_logger,  # Pass workflow logger for UI logging
        )

        # Handle file processing result
        _handle_file_processing_result(
            file_execution_result,
            file_name,
            file_start_time,
            result,
            successful_files_for_manual_review,
            file_hash,
            api_client,
            context.workflow_id,
            context.execution_id,
            workflow_logger,
            workflow_file_execution_id,
            celery_task_id,  # Pass celery task ID to detect API queue
            context.metadata.get(
                "is_api_workflow", False
            ),  # Pass existing API workflow detection
            skipped_already_completed,  # Pass list to track duplicate skips
        )

    # Update metadata with results
    context.metadata["result"] = result
    context.metadata["successful_files_for_manual_review"] = (
        successful_files_for_manual_review
    )

    return context


def _handle_file_processing_result(
    file_execution_result: FileProcessingResult,
    file_name: str,
    file_start_time: float,
    result: FileBatchResult,
    successful_files_for_manual_review: list,
    file_hash: FileHashData,
    api_client: Any,
    workflow_id: str,
    execution_id: str,
    workflow_logger: WorkerWorkflowLogger,
    file_execution_id: str,
    celery_task_id: str,
    is_api_workflow: bool,
    skipped_already_completed: list,
) -> None:
    """Handle the result of individual file processing.

    Args:
        file_execution_result: Result from file processing
        file_name: Name of the processed file
        file_start_time: Start time for performance tracking
        result: Batch result tracker
        successful_files_for_manual_review: List of successful files
        file_hash: File hash data
        api_client: Internal API client
        workflow_id: Workflow ID
        execution_id: Execution ID
        workflow_logger: Workflow logger instance
        file_execution_id: File execution ID
        celery_task_id: Celery task ID for queue detection
        is_api_workflow: Whether this is an API workflow (from existing detection)
        skipped_already_completed: List to track files skipped as already completed
    """
    # Handle null execution result
    if file_execution_result is None:
        _handle_null_execution_result(
            file_name, result, api_client, workflow_id, execution_id
        )
        return

    # CRITICAL: Handle duplicate skip - no DB updates, silent skip
    # When is_duplicate_skip=True, another worker is already processing this file
    # We should skip ALL processing and not update any database status or counters
    if getattr(file_execution_result, "is_duplicate_skip", False):
        # Enhanced debug log with full context for internal debugging
        logger.info(
            f"DUPLICATE SKIP: File '{file_name}' skipped as duplicate - another worker is processing it. "
            f"execution_id={execution_id}, workflow_id={workflow_id}, "
            f"file_execution_id={file_execution_id}, celery_task_id={celery_task_id}. "
            f"No DB status updates, but counting in skipped_already_completed for accurate total_files. "
            f"First worker will handle all status updates and counter increments."
        )
        # Add to skipped_already_completed so it's counted in total_files
        file_identifier = f"{file_hash.provider_file_uuid}:{file_hash.file_path}"
        if file_identifier not in skipped_already_completed:
            skipped_already_completed.append(file_identifier)
            logger.debug(
                f"Added {file_name} to skipped_already_completed for total_files count"
            )
        # Exit early without any DB updates - the first worker will handle all updates
        return

    # Calculate execution time
    file_execution_time = _calculate_execution_time(file_name, file_start_time)

    # Update file execution status in database
    _update_file_execution_status(
        file_execution_result, file_name, file_execution_time, api_client
    )

    # Update batch execution time
    _update_batch_execution_time(result, file_execution_time)

    # Log cost details for this file (regardless of success/failure, matches backend pattern)
    if workflow_logger:
        # Create file-specific logger for proper log routing to UI
        file_logger = workflow_logger.create_file_logger(file_execution_id)

        # Log cost using file-specific logger (ensures file_execution_id context)
        file_logger.log_total_cost_per_file(
            worker_logger=logger,
            file_execution_id=file_execution_id,
            file_name=file_name,
            api_client=api_client,
        )

    # Handle success or failure based on execution result
    if _has_execution_errors(file_execution_result):
        _handle_failed_execution(
            file_execution_result,
            file_name,
            result,
            workflow_logger,
            file_execution_id,
            api_client,
            workflow_id,
            execution_id,
        )
    else:
        _handle_successful_execution(
            file_execution_result,
            file_name,
            result,
            successful_files_for_manual_review,
            file_hash,
            workflow_logger,
            file_execution_id,
            api_client,
            workflow_id,
        )


def _compile_batch_result(context: WorkflowContextData) -> dict[str, Any]:
    """Compile the final batch processing result.

    Args:
        context: Workflow context data

    Returns:
        Final result dictionary
    """
    result = context.metadata["result"]
    workflow_logger = context.metadata.get("workflow_logger")
    skipped_already_completed = context.metadata.get("skipped_already_completed", [])
    skipped_active_duplicate = context.metadata.get("skipped_active_duplicate", [])
    total_skipped = len(skipped_already_completed) + len(skipped_active_duplicate)

    # Send execution completion summary to UI
    if workflow_logger:
        workflow_logger.publish_execution_complete(
            successful_files=result.successful_files,
            failed_files=result.failed_files,
            total_time=result.execution_time,
        )

    # Log batch completion summary
    # Note: Only active duplicates counted in failed_files; already-completed not counted
    if total_skipped > 0:
        logger.info(
            f"Function tasks.process_file_batch completed. "
            f"Successful: {result.successful_files} files, "
            f"Failed: {result.failed_files} files, "
            f"Already completed: {len(skipped_already_completed)}, "
            f"Active duplicates: {len(skipped_active_duplicate)}. "
            f"Batch execution time: {result.execution_time:.2f}s"
        )
    else:
        logger.info(
            f"Function tasks.process_file_batch completed successfully. "
            f"Batch execution time: {result.execution_time:.2f}s for "
            f"{result.successful_files + result.failed_files} files"
        )

    # CRITICAL: Clean up StateStore to prevent data leaks between tasks
    try:
        StateStore.clear_all()
        logger.debug("🧹 Cleaned up StateStore context to prevent data leaks")
    except Exception as cleanup_error:
        logger.warning(f"Failed to cleanup StateStore context: {cleanup_error}")

    # Return the final result matching Django backend format
    # Note: Only active duplicates count as failures; already-completed do not
    return {
        "successful_files": result.successful_files,
        "failed_files": result.failed_files,  # Includes active duplicates (user error)
        "total_files": result.successful_files
        + result.failed_files
        + len(skipped_already_completed),  # Include all files in batch
        "skipped_already_completed": len(skipped_already_completed),  # Not a failure
        "skipped_active_duplicate": len(
            skipped_active_duplicate
        ),  # IS a failure (counted above)
        "execution_time": result.execution_time,
        "organization_id": context.organization_context.organization_id,
    }


# HELPER FUNCTIONS (originally part of the massive process_file_batch function)
# These functions support the refactored file processing workflow


def _cleanup_file_cache_entry(
    file_hash: FileHashData,
    workflow_id: str,
    file_name: str,
) -> None:
    """Helper to cleanup active file cache entry after DB record creation attempt.

    This should be called after attempting to create WorkflowFileExecution,
    regardless of success or failure, to prevent stale cache entries from
    blocking future executions.

    Args:
        file_hash: File hash data containing provider_file_uuid
        workflow_id: Workflow ID for cache key
        file_name: File name for logging
    """
    if not file_hash.provider_file_uuid:
        return

    try:
        from shared.workflow.execution.active_file_manager import (
            cleanup_active_file_cache,
        )

        cleanup_active_file_cache(
            provider_file_uuids=[file_hash.provider_file_uuid],
            workflow_id=workflow_id,
            logger_instance=logger,
        )
        logger.debug(
            f"Cleaned cache for {file_name} (UUID: {file_hash.provider_file_uuid})"
        )
    except Exception as cleanup_error:
        logger.warning(f"Cache cleanup failed for {file_name}: {cleanup_error}")
        # Don't raise - cache will expire anyway


def _check_file_already_active(
    file_hash: FileHashData,
    workflow_id: str,
    execution_id: str,
    api_client: InternalAPIClient,
    file_name: str,
) -> bool:
    """Check if file is already being processed (Redis-first with DB fallback).

    This provides a secondary check at the file_processing worker level to catch
    any files that slipped through the general worker's filter due to race conditions.

    OPTIMIZATION: Checks Redis cache first (fastest path, highest hit rate since general
    worker just added the file), then falls back to database if Redis check fails or
    returns no result.

    Args:
        file_hash: File hash data containing provider_file_uuid and file_path
        workflow_id: Workflow ID
        execution_id: Current execution ID to exclude
        api_client: Internal API client
        file_name: File name for logging

    Returns:
        True if file is already active in a different execution, False otherwise
    """
    # Only check files with provider_file_uuid (files from external sources)
    if not file_hash.provider_file_uuid:
        return False

    # STEP 1: Check Redis cache first (fastest path, most likely to find duplicates)
    try:
        from shared.cache.cache_backends import RedisCacheBackend
        from shared.workflow.execution.active_file_manager import ActiveFileManager

        cache = RedisCacheBackend()
        if cache.available:
            # Construct cache key using ActiveFileManager method for consistency
            cache_key = ActiveFileManager._create_cache_key(
                workflow_id,
                file_hash.provider_file_uuid,
                file_hash.file_path,
            )
            cached_data = cache.get(cache_key)

            if cached_data and isinstance(cached_data, dict):
                # Extract execution_id from cache wrapper structure
                cached_execution_id = cached_data.get("data", {}).get("execution_id")

                if cached_execution_id and cached_execution_id != execution_id:
                    # Found in Redis - different execution is processing this file
                    logger.warning(
                        f"DUPLICATE DETECTED: File '{file_name}' (UUID: {file_hash.provider_file_uuid}) "
                        f"is already being processed by execution {cached_execution_id} (Redis cache check)"
                    )
                    return True
                elif cached_execution_id == execution_id:
                    # Same execution - not a duplicate
                    logger.debug(
                        f"File '{file_name}' found in Redis cache for same execution {execution_id}"
                    )
                    return False
                # If no execution_id or invalid data, fall through to DB check

            # Cache miss - fall through to DB check
            logger.info(
                f"File '{file_name}' not found in Redis cache, falling back to DB check for execution {execution_id}"
            )

    except Exception as redis_error:
        # Redis check failed, fall back to DB
        logger.exception(
            f"Redis check failed for '{file_name}': {redis_error}. Falling back to DB check"
        )

    # STEP 2: DB fallback (if Redis unavailable, cache miss, or invalid data)
    try:
        response = api_client.check_files_active_processing(
            workflow_id=workflow_id,
            files=[{"uuid": file_hash.provider_file_uuid, "path": file_hash.file_path}],
            current_execution_id=execution_id,
        )
        if response.success and response.data:
            # Check if this specific file is in active_identifiers
            active_identifiers = response.data.get("active_identifiers", [])

            file_identifier = f"{file_hash.provider_file_uuid}:{file_hash.file_path}"

            if file_identifier in active_identifiers:
                logger.warning(
                    f"DUPLICATE DETECTED: File '{file_name}' (UUID: {file_hash.provider_file_uuid}) "
                    f"is already being processed in another execution (DB check)"
                )
                return True

        return False

    except Exception as e:
        logger.warning(
            f"DB check failed for '{file_name}': {e}. "
            f"Proceeding with file processing (fail-safe)"
        )
        # Fail-safe: if both checks fail, allow processing
        return False


def _pre_create_file_executions(
    file_data: WorkerFileData,
    files: list[Any],
    workflow_id: str,
    execution_id: str,
    api_client: InternalAPIClient,
    workflow_type: str,
    is_api: bool = False,
    use_file_history: bool = True,
    workflow_logger: WorkerWorkflowLogger | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Pre-create WorkflowFileExecution records with PENDING status to prevent race conditions.

    This matches the backend's _pre_create_file_executions pattern for ALL workflow types
    and includes file history deduplication for ETL workflows.

    Includes double safeguard: checks database for duplicate active files before creating records.

    Args:
        file_data: File data context
        files: List of file items (can be tuples, lists, or dicts)
        workflow_id: Workflow ID
        execution_id: Workflow execution ID
        api_client: Internal API client
        workflow_type: Workflow type (API/ETL/TASK)
        is_api: Whether this is an API workflow
        use_file_history: Whether to use file history
        workflow_logger: Workflow logger for UI logging (optional)

    Returns:
        Tuple of (pre_created_data dict, skipped_already_completed list, skipped_active_duplicate list)
        - pre_created_data: Dict mapping file names to PreCreatedFileData
        - skipped_already_completed: Files already COMPLETED in this execution (not a failure)
        - skipped_active_duplicate: Files ACTIVE in different execution (IS a failure - user error)
    """
    pre_created_data: dict[str, PreCreatedFileData] = {}
    skipped_already_completed: list[str] = []  # Already done in this execution
    skipped_active_duplicate: list[str] = []  # Active in different execution (user error)

    # Use the file history flag passed from execution parameters
    logger.info(
        f"Using file history parameter for workflow {workflow_id}  execution {execution_id} (type: {workflow_type}): use_file_history = {use_file_history}"
    )

    for file_item in files:
        # Parse file item to get name and hash data
        if isinstance(file_item, list) and len(file_item) == 2:
            file_name, file_hash_dict = file_item
        elif isinstance(file_item, tuple):
            file_name, file_hash_dict = file_item
        elif isinstance(file_item, dict):
            file_name = file_item.get("file_name")
            file_hash_dict = file_item
        else:
            logger.error(f"Skipping invalid file item format: {type(file_item)}")
            continue

        # Create FileHashData from dict
        file_hash = _create_file_hash_from_dict(
            file_name=file_name, file_hash_dict=file_hash_dict, file_data=file_data
        )

        # Set use_file_history flag on the file object for later use
        file_hash.use_file_history = use_file_history

        # NOTE: File history checking moved to individual file processing
        # This ensures WorkflowFileExecution records are created for all files

        # Convert to dict for API
        file_hash_dict_for_api = file_hash.to_dict()

        # DOUBLE SAFEGUARD: Check if file is already being processed (Redis-first with DB fallback)
        # This catches race conditions that slipped through general worker's filter
        is_duplicate = _check_file_already_active(
            file_hash=file_hash,
            workflow_id=workflow_id,
            execution_id=execution_id,
            api_client=api_client,
            file_name=file_name,
        )

        try:
            # Create WorkflowFileExecution record for ALL files (including duplicates for audit trail)
            # Create WorkflowFileExecution record for ALL workflow types
            # CRITICAL FIX: For use_file_history=False, force create fresh records to prevent
            # reusing completed records from previous executions
            workflow_file_execution = api_client.get_or_create_workflow_file_execution(
                execution_id=execution_id,
                file_hash=file_hash_dict_for_api,
                workflow_id=workflow_id,
                force_create=not use_file_history,  # Force create when file history is disabled
            )

            # EARLY EXIT: Skip if file already COMPLETED in this execution
            # This catches race conditions where Worker 1 completes before Worker 2's pre-create runs
            # Only checks current execution_id (respects file_history cleanup for different executions)
            if (
                hasattr(workflow_file_execution, "status")
                and workflow_file_execution.status == ExecutionStatus.COMPLETED.value
            ):
                logger.info(
                    f"File '{file_name}' already COMPLETED in execution {execution_id} "
                    f"(file_execution_id: {workflow_file_execution.id}). Skipping duplicate task creation."
                )
                file_identifier = f"{file_hash.provider_file_uuid}:{file_hash.file_path}"
                skipped_already_completed.append(file_identifier)
                continue  # Skip to next file

            # Handle duplicate files vs normal files differently
            if is_duplicate:
                # DUPLICATE DETECTED: Mark as ERROR with explanation for audit trail
                error_message = (
                    "File skipped - already being processed in another execution "
                    "(duplicate prevention safeguard)"
                )

                try:
                    api_client.file_client.update_file_execution_status(
                        file_execution_id=workflow_file_execution.id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=error_message,
                    )
                    logger.warning(
                        f"DUPLICATE: File '{file_name}' marked as ERROR - {error_message}"
                    )

                    # Log to UI with error context
                    if workflow_logger:
                        from shared.infrastructure.logging.helpers import (
                            log_file_processing_error,
                        )

                        log_file_processing_error(
                            workflow_logger,
                            str(workflow_file_execution.id),
                            file_name,
                            f"⏭️  {error_message}",
                        )

                    # Track as skipped using stable identifier (uuid:path), not just file_name
                    # This prevents misclassification when different files share the same display name
                    file_identifier = (
                        f"{file_hash.provider_file_uuid}:{file_hash.file_path}"
                    )
                    skipped_active_duplicate.append(file_identifier)

                except Exception as status_error:
                    logger.error(
                        f"Failed to mark duplicate file '{file_name}' as ERROR: {status_error}"
                    )

                # Don't add to pre_created_data - file won't be processed
                logger.info(
                    f"Created WorkflowFileExecution {workflow_file_execution.id} for duplicate file '{file_name}' (marked as ERROR)"
                )

            else:
                # NORMAL FILE: Set initial status to PENDING for processing
                try:
                    api_client.file_client.update_file_execution_status(
                        file_execution_id=workflow_file_execution.id,
                        status=ExecutionStatus.PENDING.value,
                    )
                except Exception as status_error:
                    logger.warning(
                        f"Failed to set initial PENDING status for file {file_name}: {status_error}"
                    )
                    # Don't fail the entire creation if status update fails

                # Add to pre_created_data for processing
                pre_created_data[file_name] = PreCreatedFileData(
                    id=str(workflow_file_execution.id),
                    object=workflow_file_execution,
                    file_hash=file_hash,
                )
                logger.info(
                    f"Pre-created WorkflowFileExecution {workflow_file_execution.id} for {workflow_type} file '{file_name}'"
                )

        except Exception as e:
            logger.exception(
                f"Failed to pre-create WorkflowFileExecution for '{file_name}': {str(e)}"
            )
            # Continue with other files even if one fails

        finally:
            # Always cleanup cache (success or failure) to prevent stale entries
            _cleanup_file_cache_entry(file_hash, workflow_id, file_name)

    # File history deduplication now handled during individual file processing

    # Log summary if files were skipped
    total_skipped = len(skipped_already_completed) + len(skipped_active_duplicate)
    if total_skipped > 0:
        logger.warning(
            f"Skipped {total_skipped} duplicate file(s): "
            f"{len(skipped_already_completed)} already completed, "
            f"{len(skipped_active_duplicate)} active in other executions"
        )

        # Server-side log for already completed (internal detail, not shown to user)
        if skipped_already_completed:
            logger.info(
                f"{len(skipped_already_completed)} file(s) already completed in this execution "
                f"(internal duplicate prevention - not shown to user)"
            )

        # UI log for active duplicates (user error, SHOULD be shown to user)
        if workflow_logger and skipped_active_duplicate:
            from shared.infrastructure.logging.helpers import log_file_info

            log_file_info(
                workflow_logger,
                None,
                f"⏭️  {len(skipped_active_duplicate)} duplicate file(s) active in other executions (marked as ERROR)",
            )

    logger.info(
        f"Pre-created {len(pre_created_data)} file execution(s), "
        f"skipped {len(skipped_already_completed)} already completed, "
        f"{len(skipped_active_duplicate)} active duplicates"
    )

    return pre_created_data, skipped_already_completed, skipped_active_duplicate


def _create_file_hash_from_dict(
    file_name: str,
    file_hash_dict: dict[str, Any],
    file_data: WorkerFileData | None = None,
) -> FileHashData:
    """Create FileHashData object from dictionary using shared dataclass.

    This uses the shared FileHashData dataclass for type safety and consistency.
    It preserves the original file_hash from Django backend or leaves it empty for worker computation.

    Args:
        file_hash_dict: Dictionary containing file hash data

    Returns:
        FileHashData instance with type-safe access
    """
    if file_hash_dict is None:
        logger.error("file_hash_dict is None, returning minimal FileHashData")
        return FileHashData(
            file_path="",
            file_name="unknown.txt",
            file_hash="",  # Empty - will be computed during execution
            file_size=0,
            mime_type=APPLICATION_OCTET_STREAM,
            fs_metadata={},
            is_executed=False,
        )

    # Use FileHashData for type safety and validation
    try:
        # Create FileHashData from input dict for validation and type safety
        if isinstance(file_hash_dict, dict):
            file_hash_data = FileHashData.from_dict(file_hash_dict)
            logger.debug(
                f"Successfully created FileHashData for {file_hash_data.file_name}"
            )
        else:
            logger.error(f"Expected dict for file_hash_dict, got {type(file_hash_dict)}")
            raise ValueError(f"Invalid file_hash_dict type: {type(file_hash_dict)}")

        # Return the FileHashData instance directly
        file_hash = file_hash_data
        logger.info(f"File hash for {file_hash.file_name}: {file_hash.file_hash}")
        # Log warning if file_hash is empty to help with debugging
        if not file_hash.file_hash:
            logger.warning(
                f"File hash is empty for '{file_hash.file_name}' - content hash computation may have failed"
            )

    except Exception as e:
        logger.error(f"Failed to create FileHashData from dict: {e}", exc_info=True)
        logger.debug(
            f"Input dict keys: {list(file_hash_dict.keys()) if isinstance(file_hash_dict, dict) else 'not a dict'}"
        )

        # Fallback to manual creation for backward compatibility
        file_name = (
            file_hash_dict.get("file_name") or file_hash_dict.get("name") or "unknown.txt"
        )
        file_path = file_hash_dict.get("file_path") or file_hash_dict.get("path") or ""
        file_hash_value = file_hash_dict.get("file_hash") or ""

        # Create FileHashData manually for fallback case
        file_hash = FileHashData(
            file_path=file_path,
            file_name=file_name,
            source_connection_type=file_hash_dict.get("source_connection_type"),
            file_hash=file_hash_value.strip(),  # Will be populated during execution
            file_size=file_hash_dict.get("file_size") or 0,
            provider_file_uuid=file_hash_dict.get("provider_file_uuid"),
            mime_type=file_hash_dict.get("mime_type") or APPLICATION_OCTET_STREAM,
            fs_metadata=file_hash_dict.get("fs_metadata") or {},
            file_destination=file_hash_dict.get("file_destination"),
            is_executed=file_hash_dict.get("is_executed", False),
            file_number=file_hash_dict.get("file_number"),
            is_manualreview_required=file_hash_dict.get(
                "is_manualreview_required", False
            ),
        )

        # Log warning if file_hash is empty (fallback case)
        if not file_hash_value.strip():
            logger.warning(
                f"File hash is empty for '{file_name}' in fallback processing - content hash computation may have failed"
            )

    # Preserve connector metadata if present (for FILESYSTEM workflows)
    # Store connector metadata in fs_metadata since FileHashData doesn't have dedicated connector fields
    if "connector_metadata" in file_hash_dict or "connector_id" in file_hash_dict:
        if not hasattr(file_hash, "fs_metadata") or file_hash.fs_metadata is None:
            file_hash.fs_metadata = {}

        if "connector_metadata" in file_hash_dict:
            file_hash.fs_metadata["connector_metadata"] = file_hash_dict[
                "connector_metadata"
            ]
        if "connector_id" in file_hash_dict:
            file_hash.fs_metadata["connector_id"] = file_hash_dict["connector_id"]

    # Log actual data state for debugging
    file_name_for_logging = file_hash.file_name or "unknown"
    if not file_hash_dict.get("file_name"):
        logger.debug(f"Missing file_name, using: {file_name_for_logging}")
    if not file_hash_dict.get("file_hash"):
        logger.info(
            f"File hash not provided, will be computed during execution for: {file_name_for_logging}"
        )

    if file_data and file_data.hitl_queue_name:
        file_hash.hitl_queue_name = file_data.hitl_queue_name
        file_hash.is_manualreview_required = True  # Override manual review flag for HITL
        logger.info(
            f"Applied HITL queue name '{file_data.hitl_queue_name}' to file {file_name}"
        )

    return file_hash


def _process_file(
    current_file_idx: int,
    total_files: int,
    file_data: WorkerFileData,
    file_hash: FileHashData,
    api_client: InternalAPIClient,
    workflow_execution: dict[str, Any],
    workflow_file_execution_id: str = None,
    workflow_file_execution_object: Any = None,
    workflow_logger: Any = None,
) -> dict[str, Any]:
    """Process a single file matching Django backend _process_file pattern.

    This uses API-based coordination but follows the exact same logic
    as the Django backend file processing.

    Args:
        current_file_idx: Index of current file
        total_files: Total number of files
        file_data: File data context
        file_hash: FileHashData instance with type-safe access
        api_client: Internal API client
        workflow_execution: Workflow execution context

    Returns:
        File execution result
    """
    # Delegate to the new FileProcessor for better maintainability and testability
    return FileProcessor.process_file(
        current_file_idx=current_file_idx,
        total_files=total_files,
        file_data=file_data,
        file_hash=file_hash,
        api_client=api_client,
        workflow_execution=workflow_execution,
        workflow_file_execution_id=workflow_file_execution_id,
        workflow_file_execution_object=workflow_file_execution_object,
        workflow_logger=workflow_logger,
    )


@app.task(
    bind=True,
    name=TaskName.PROCESS_FILE_BATCH_API,
    max_retries=0,  # Match Django backend
    ignore_result=False,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
    default_retry_delay=5,
    # Timeout inherited from global Celery config (FILE_PROCESSING_TASK_TIME_LIMIT env var)
)
@monitor_performance
def process_file_batch_api(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    batch_id: str,
    created_files: list[dict[str, Any]],
    pipeline_id: str | None = None,
    execution_mode: tuple | None = None,
    use_file_history: bool = False,
) -> dict[str, Any]:
    """API file batch processing task matching Django backend pattern.

    This processes files from a created batch for API executions using the
    exact same pattern as Django backend but with API coordination.

    Args:
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        batch_id: File batch ID
        created_files: List of file execution records
        pipeline_id: Pipeline ID
        execution_mode: Execution mode tuple
        use_file_history: Whether to use file history

    Returns:
        Processing result matching Django backend structure
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
    ):
        logger.info(
            f"Processing API file batch {batch_id} with {len(created_files)} files"
        )

        try:
            # Set organization context exactly like Django backend
            StateStore.set(Account.ORGANIZATION_ID, schema_name)

            # Create organization-scoped API client using factory pattern
            api_client = create_api_client(schema_name)

            # Get workflow execution context
            execution_response = api_client.get_workflow_execution(execution_id)
            if not execution_response.success:
                raise Exception(
                    f"Failed to get execution context: {execution_response.error}"
                )
            execution_context = execution_response.data
            workflow_execution = execution_context.get("execution", {})

            # Set log events ID in StateStore like Django backend
            log_events_id = workflow_execution.get("execution_log_id")
            if log_events_id:
                StateStore.set("LOG_EVENTS_ID", log_events_id)
                logger.info(f"Set LOG_EVENTS_ID for WebSocket messaging: {log_events_id}")

            # Process each file in the batch using Django-like pattern
            file_results = []
            successful_files = 0
            failed_files = 0

            for file_data in created_files:
                file_result = _process_single_file_api(
                    api_client=api_client,
                    file_data=file_data,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    pipeline_id=pipeline_id,
                    use_file_history=use_file_history,
                )
                file_results.append(file_result)

                # CRITICAL FIX: Cache ALL file results (including errors) for API response
                # This ensures the backend can collect all results via get_api_results()
                # INCLUDING error results which are needed for proper API error reporting
                if file_result:  # Cache both successful AND error results
                    try:
                        from shared.workflow.execution.service import (
                            WorkerWorkflowExecutionService,
                        )

                        # Create workflow service for caching
                        workflow_service = WorkerWorkflowExecutionService(
                            api_client=api_client
                        )

                        # Convert file result to FileExecutionResult format for caching
                        api_result = {
                            "file": file_result.get("file_name", "unknown"),
                            "file_execution_id": file_result.get("file_execution_id", ""),
                            "result": file_result.get("result_data"),
                            "error": file_result.get("error"),
                            "metadata": {
                                "processing_time": file_result.get("processing_time", 0)
                            },
                        }

                        # Cache the result for API response aggregation
                        workflow_service.cache_api_result(
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            result=api_result,
                            is_api=True,
                        )

                        # Log differently for success vs error
                        if file_result.get("error"):
                            logger.info(
                                f"Cached API ERROR result for file {file_result.get('file_name')}: {file_result.get('error')}"
                            )
                        else:
                            logger.debug(
                                f"Cached API success result for file {file_result.get('file_name')}"
                            )

                    except Exception as cache_error:
                        logger.warning(
                            f"Failed to cache API result for file {file_result.get('file_name')}: {cache_error}"
                        )

                # Count results like Django backend
                if file_result.get("error"):
                    failed_files += 1
                else:
                    successful_files += 1

            # Return result matching Django FileBatchResult structure
            batch_result = {
                "successful_files": successful_files,
                "failed_files": failed_files,
            }

            logger.info(f"Successfully processed API file batch {batch_id}")
            return batch_result

        except Exception:
            logger.exception(f"API file batch processing failed for {batch_id}")
            raise


def _process_single_file_api(
    api_client: InternalAPIClient,
    file_data: dict[str, Any],
    workflow_id: str,
    execution_id: str,
    pipeline_id: str | None,
    use_file_history: bool,
) -> dict[str, Any]:
    """Process a single file for API execution using runner service.

    Args:
        api_client: Internal API client
        file_data: File execution data
        workflow_id: Workflow ID
        execution_id: Execution ID
        pipeline_id: Pipeline ID
        use_file_history: Whether to use file history

    Returns:
        File processing result
    """
    file_execution_id = file_data.get("id")
    file_name = file_data.get("file_name", "unknown")

    logger.info(f"Processing file: {file_name} (execution: {file_execution_id})")

    # Update file execution status to EXECUTING when processing starts (using common method)
    api_client.update_file_status_to_executing(file_execution_id, file_name)

    start_time = time.time()

    try:
        # 1. Check file history if enabled
        if use_file_history:
            history_result = _check_file_history(api_client, file_data, workflow_id)
            if history_result.get("found"):
                logger.info(f"File {file_name} found in history, using cached result")
                return history_result["result"]

        # 2. Get workflow definition from API
        workflow_definition = api_client.get_workflow_definition(workflow_id)
        if not workflow_definition:
            raise ValueError(f"Workflow definition not found for workflow {workflow_id}")

        # 3. Get file content from storage
        file_content = api_client.get_file_content(file_execution_id)
        if not file_content:
            raise ValueError(
                f"File content not found for file execution {file_execution_id}"
            )

        # 3.1. Compute and update file hash and mime_type (FIXED: was missing)
        import hashlib
        import mimetypes

        if isinstance(file_content, bytes):
            file_hash_value = hashlib.sha256(file_content).hexdigest()
            file_size = len(file_content)
        else:
            # Handle string content
            file_bytes = (
                file_content.encode("utf-8")
                if isinstance(file_content, str)
                else file_content
            )
            file_hash_value = hashlib.sha256(file_bytes).hexdigest()
            file_size = len(file_bytes)

        # Determine mime type from file name
        mime_type, _ = mimetypes.guess_type(file_name)
        if not mime_type:
            mime_type = APPLICATION_OCTET_STREAM

        # Update file execution with computed hash, mime_type, and metadata
        try:
            api_client.update_workflow_file_execution_hash(
                file_execution_id=file_execution_id,
                file_hash=file_hash_value,
                mime_type=mime_type,  # Now properly passed as separate parameter
                fs_metadata={"computed_during_processing": True, "file_size": file_size},
            )
        except Exception as hash_error:
            logger.warning(f"Failed to update file hash for {file_name}: {hash_error}")

        # 4. Process file through runner service
        runner_result = _call_runner_service(
            file_content=file_content,
            file_name=file_name,
            workflow_definition=workflow_definition,
            execution_id=execution_id,
            pipeline_id=pipeline_id,
        )

        # 5. Store results via API
        storage_result = api_client.store_file_execution_result(
            file_execution_id=file_execution_id, result_data=runner_result
        )

        processing_time = time.time() - start_time

        result = {
            "file_execution_id": file_execution_id,
            "file_name": file_name,
            "status": "completed",
            "processing_time": processing_time,
            "result_data": runner_result,
            "storage_result": storage_result,
        }

        logger.info(f"Successfully processed file: {file_name} in {processing_time:.2f}s")
        return result

    except Exception as e:
        processing_time = time.time() - start_time
        logger.exception(
            f"Failed to process file {file_name} after {processing_time:.2f}s: {e}"
        )

        # Try to update file execution status to failed
        try:
            api_client.update_file_execution_status(
                file_execution_id=file_execution_id,
                status=ExecutionStatus.ERROR.value,
                error_message=str(e),
            )
        except Exception:
            logger.exception("Failed to update file execution status")

        return {
            "file_execution_id": file_execution_id,
            "file_name": file_name,
            "status": "failed",
            "processing_time": processing_time,
            "error": str(e),
        }


def _check_file_history(
    api_client: InternalAPIClient, file_data: dict[str, Any], workflow_id: str
) -> dict[str, Any]:
    """Check if file has been processed before and return cached result.

    Args:
        api_client: Internal API client
        file_data: File execution data
        workflow_id: Workflow ID

    Returns:
        History check result
    """
    try:
        file_hash = file_data.get("file_hash")
        cache_key = file_data.get("cache_key", file_hash)

        if not cache_key:
            return {"found": False}

        history_result = api_client.get_file_history(
            workflow_id=workflow_id,
            file_hash=cache_key,  # Use cache_key as file_hash
            file_path=file_data.get("file_path"),
        )

        return history_result

    except Exception as e:
        logger.warning(f"Failed to check file history: {e}")
        return {"found": False}


def _call_runner_service(
    file_content: bytes,
    file_name: str,
    workflow_definition: dict[str, Any],
    execution_id: str,
    pipeline_id: str | None,
) -> dict[str, Any]:
    """Call the runner service to process file through workflow tools.

    Args:
        file_content: File content bytes
        file_name: Name of the file
        workflow_definition: Workflow configuration
        execution_id: Execution ID
        pipeline_id: Pipeline ID

    Returns:
        Processing result from runner service
    """
    import requests

    # Build runner service URL
    runner_host = os.getenv("UNSTRACT_RUNNER_HOST", "http://localhost")
    runner_port = os.getenv("UNSTRACT_RUNNER_PORT", "5002")
    runner_url = f"{runner_host}:{runner_port}/api/v1/tool/execute"

    # Prepare request payload
    payload = {
        "workflow_definition": workflow_definition,
        "execution_id": execution_id,
        "pipeline_id": pipeline_id,
        "file_metadata": {
            "file_name": file_name,
            "mime_type": _detect_mime_type(file_name),
            "size": len(file_content),
        },
    }

    # Prepare files for multipart upload
    files = {
        "file": (file_name, file_content, _detect_mime_type(file_name)),
        "payload": (None, _safe_json_dumps(payload), "application/json"),
    }

    # Request configuration
    timeout = int(os.getenv("UNSTRACT_RUNNER_API_TIMEOUT", "120"))
    retry_count = int(os.getenv("UNSTRACT_RUNNER_API_RETRY_COUNT", "5"))
    backoff_factor = float(os.getenv("UNSTRACT_RUNNER_API_BACKOFF_FACTOR", "3"))

    logger.info(f"Calling runner service at {runner_url} for file {file_name}")

    for attempt in range(retry_count):
        try:
            response = requests.post(
                runner_url,
                files=files,
                timeout=timeout,
                headers={
                    "X-Execution-ID": execution_id,
                    "X-Pipeline-ID": pipeline_id or "",
                },
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Runner service processed file {file_name} successfully")
            return result

        except requests.exceptions.RequestException as e:
            if attempt < retry_count - 1:
                wait_time = backoff_factor**attempt
                logger.warning(
                    f"Runner service call failed (attempt {attempt + 1}/{retry_count}), retrying in {wait_time}s: {e}"
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    f"Runner service call failed after {retry_count} attempts: {e}"
                )
                raise
        except Exception:
            logger.exception("Unexpected error calling runner service")
            raise

    raise Exception(f"Failed to call runner service after {retry_count} attempts")


def _detect_mime_type(file_name: str) -> str:
    """Detect MIME type from file extension.

    Args:
        file_name: Name of the file

    Returns:
        MIME type string
    """
    import mimetypes

    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or APPLICATION_OCTET_STREAM


def _safe_json_dumps(data: Any) -> str:
    """Safely encode data to JSON string with fallback error handling.

    Args:
        data: Data to be JSON encoded

    Returns:
        JSON string or fallback string representation
    """
    try:
        return json.dumps(data)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to JSON encode data, falling back to str(): {e}")
        try:
            return str(data)
        except Exception as str_error:
            logger.error(f"Failed to convert data to string: {str_error}")
            return "{}"


# Simple resilient executor decorator (placeholder)
def resilient_executor(func):
    """Simple resilient executor decorator."""
    return func


# Resilient file processor
@app.task(bind=True)
@resilient_executor
@with_execution_context
def process_file_batch_resilient(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    """Resilient file batch processing with advanced error handling."""
    logger.info(
        f"Starting resilient file batch processing for {len(hash_values_of_files)} files"
    )

    try:
        # Use the main processing function
        result = process_file_batch(
            schema_name=schema_name,
            workflow_id=workflow_id,
            execution_id=execution_id,
            hash_values_of_files=hash_values_of_files,
            **kwargs,
        )

        return result

    except Exception as e:
        logger.error(f"Resilient file batch processing failed: {e}")
        raise


# Backward compatibility aliases for Django backend during transition
# Register the same task function with the old Django task names for compatibility


@app.task(
    bind=True,
    name="workflow_manager.workflow_v2.file_execution_tasks.process_file_batch",
    max_retries=0,
    ignore_result=False,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
    default_retry_delay=5,
)
def process_file_batch_django_compat(
    self, file_batch_data: dict[str, Any]
) -> dict[str, Any]:
    """Backward compatibility wrapper for Django backend task name.

    This allows new workers to handle tasks sent from the old Django backend
    during the transition period when both systems are running.

    Args:
        file_batch_data: File batch data from Django backend

    Returns:
        Same result as process_file_batch
    """
    logger.info(
        "Processing file batch via Django compatibility task name: "
        "workflow_manager.workflow_v2.file_execution_tasks.process_file_batch"
    )

    # Django compatibility: Calculate and apply manual review requirements
    # This replicates the MRQ logic that was originally in Django backend
    try:
        # Extract organization_id from Django backend data structure
        # Django sends: {files: [...], file_data: {organization_id: "...", ...}}
        file_data = file_batch_data.get("file_data", {})
        organization_id = file_data.get("organization_id")

        if not organization_id:
            logger.warning(
                "Django compatibility: No organization_id found in file_data, skipping MRQ calculation"
            )
        else:
            # Create organization-scoped API client
            api_client = create_api_client(organization_id)

            # Calculate manual review requirements
            mrq_flags = _calculate_manual_review_requirements(file_batch_data, api_client)

            # Enhance batch data with MRQ flags
            _enhance_batch_with_mrq_flags(file_batch_data, mrq_flags)

            logger.info(
                f"Django compatibility: Applied manual review flags to file batch for org {organization_id}"
            )

    except Exception as e:
        logger.warning(f"Django compatibility: Failed to calculate MRQ flags: {e}")
        raise
        # Continue processing without MRQ flags rather than failing

    # Delegate to the core implementation (same as main task)
    return _process_file_batch_core(self, file_batch_data)


# Helper functions for refactored _handle_file_processing_result


def _handle_null_execution_result(
    file_name: str,
    result: FileBatchResult,
    api_client: Any,
    workflow_id: str,
    execution_id: str,
) -> None:
    """Handle case where file execution result is None."""
    result.increment_failure()
    logger.error(
        f"File execution for file {file_name} returned None - treating as failed"
    )

    try:
        api_client.increment_failed_files(
            workflow_id=workflow_id, execution_id=execution_id
        )
    except Exception as increment_error:
        logger.warning(f"Failed to increment failed files count: {increment_error}")


def _calculate_execution_time(file_name: str, file_start_time: float) -> float:
    """Calculate and log file execution time."""
    import time

    file_end_time = time.time()
    file_execution_time = file_end_time - file_start_time

    logger.info(f"TIMING: File processing END for {file_name} at {file_end_time:.6f}")
    logger.info(f"TIMING: File processing TOTAL time: {file_execution_time:.3f}s")
    logger.info(
        f"File {file_name} processing completed in {file_execution_time:.2f} seconds"
    )
    return file_execution_time


def _update_file_execution_status(
    file_execution_result: FileProcessingResult,
    file_name: str,
    file_execution_time: float,
    api_client: Any,
) -> None:
    """Update file execution status in database."""
    file_execution_id = file_execution_result.file_execution_id
    if not file_execution_id:
        logger.warning(
            f"No file_execution_id found for {file_name}, cannot update execution time"
        )
        return

    try:
        # Check for both workflow errors and destination errors
        workflow_error = file_execution_result.error
        destination_error = file_execution_result.destination_error
        destination_processed = file_execution_result.destination_processed

        # File should be marked as ERROR if there's any error or destination processing failed
        has_error = workflow_error or destination_error or not destination_processed
        final_status = (
            ExecutionStatus.ERROR.value if has_error else ExecutionStatus.COMPLETED.value
        )

        # Combine error messages for better reporting
        error_messages = []
        if workflow_error:
            error_messages.append(f"{ErrorType.WORKFLOW_ERROR}: {workflow_error}")
        if destination_error:
            error_messages.append(f"{ErrorType.DESTINATION_ERROR}: {destination_error}")
        if not destination_processed and not destination_error:
            error_messages.append("Destination processing failed")

        combined_error = "; ".join(error_messages) if error_messages else None

        # Update database
        api_client.update_file_execution_status(
            file_execution_id=file_execution_id,
            status=final_status,
            execution_time=file_execution_time,
            error_message=combined_error,
        )
        logger.info(
            f"Updated file execution {file_execution_id} with status {final_status} and time {file_execution_time:.2f}s"
        )
    except Exception as update_error:
        logger.warning(
            f"Failed to update file execution status for {file_name}: {update_error}"
        )


def _update_batch_execution_time(
    result: FileBatchResult, file_execution_time: float
) -> None:
    """Update batch execution time."""
    result.add_execution_time(file_execution_time)
    logger.info(
        f"Added {file_execution_time:.2f}s to batch execution time. "
        f"Total batch time: {result.execution_time:.2f}s"
    )


def _has_execution_errors(file_execution_result: FileProcessingResult) -> bool:
    """Check if file execution has any errors."""
    workflow_error = file_execution_result.error
    destination_error = file_execution_result.destination_error
    destination_processed = file_execution_result.destination_processed

    return bool(workflow_error or destination_error or not destination_processed)


def _handle_failed_execution(
    file_execution_result: FileProcessingResult,
    file_name: str,
    result: FileBatchResult,
    workflow_logger: Any,
    file_execution_id: str,
    api_client: Any,
    workflow_id: str,
    execution_id: str,
) -> None:
    """Handle failed file execution."""
    result.increment_failure()

    # Determine error type and message
    workflow_error = file_execution_result.error
    destination_error = file_execution_result.destination_error

    if workflow_error:
        error_msg = workflow_error
        error_type = ErrorType.WORKFLOW_ERROR
    elif destination_error:
        error_msg = destination_error
        error_type = ErrorType.DESTINATION_ERROR
    else:
        error_msg = "Destination processing failed"
        error_type = ErrorType.DESTINATION_ERROR

    logger.info(
        f"File execution for file {file_name} marked as failed with {error_type.lower()}: {error_msg}"
    )

    # Send failed processing log to UI
    log_file_processing_error(
        workflow_logger, file_execution_id, file_name, f"{error_type}: {error_msg}"
    )

    # Update failed file count in cache
    try:
        api_client.increment_failed_files(
            workflow_id=workflow_id, execution_id=execution_id
        )
    except Exception as increment_error:
        logger.warning(f"Failed to increment failed files count: {increment_error}")


def _handle_successful_execution(
    file_execution_result: FileProcessingResult,
    file_name: str,
    result: FileBatchResult,
    successful_files_for_manual_review: list,
    file_hash: FileHashData,
    workflow_logger: Any,
    file_execution_id: str,
    api_client: Any,
    workflow_id: str,
) -> None:
    """Handle successful file execution."""
    result.increment_success()
    logger.info(f"File execution for file {file_name} marked as successful")

    # Add to successful files for manual review evaluation
    successful_files_for_manual_review.append((file_name, file_hash))

    # Send successful processing log to UI
    log_file_processing_success(workflow_logger, file_execution_id, file_name)
