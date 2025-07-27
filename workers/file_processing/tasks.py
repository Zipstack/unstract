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
from shared.api_client import InternalAPIClient
from shared.config import WorkerConfig

# Import from shared worker modules
from shared.constants import Account
from shared.local_context import StateStore
from shared.logging_utils import WorkerLogger, log_context, monitor_performance
from shared.source_operations_backend_compatible import WorkerFileHistoryManager

# Import WorkflowExecutionService direct integration
from shared.workflow_service import WorkerWorkflowExecutionService
from worker import app

# Import shared enums and dataclasses
# Import shared dataclasses for type safety
from unstract.core.data_models import (
    ConnectionType,
    ExecutionStatus,
    FileBatchData,
    FileBatchResult,
    FileHashData,
    WorkerFileData,
)

logger = WorkerLogger.get_logger(__name__)


@app.task(
    bind=True,
    name="process_file_batch",
    max_retries=0,  # Match Django backend pattern
    ignore_result=False,  # Result is passed to the callback task
    retry_backoff=True,
    retry_backoff_max=500,  # Match Django backend
    retry_jitter=True,
    default_retry_delay=5,  # Match Django backend
)
@monitor_performance
def process_file_batch(self, file_batch_data: dict[str, Any]) -> dict[str, Any]:
    """Process a batch of files in parallel using Celery.

    This exactly matches the Django backend process_file_batch task but uses
    API-based coordination instead of direct Django ORM access.

    Args:
        file_batch_data: Dictionary that will be converted to FileBatchData dataclass
            - files: List of file dictionaries with name, path, metadata, etc.
            - file_data: WorkerFileData with workflow_id, source_config, destination_config, etc.

    Returns:
        Dictionary with successful_files and failed_files counts
    """
    celery_task_id = self.request.id

    # Convert dictionary to dataclass for type safety with enhanced error handling
    try:
        batch_data = FileBatchData.from_dict(file_batch_data)
        logger.info(
            f"Successfully parsed FileBatchData with {len(batch_data.files)} files"
        )
    except (TypeError, ValueError) as e:
        logger.error(f"FileBatchData validation failed: {str(e)}")
        logger.error(
            f"Input data structure: keys={list(file_batch_data.keys()) if isinstance(file_batch_data, dict) else 'not a dict'}"
        )
        # Provide actionable error message
        raise ValueError(
            f"Invalid file batch data structure: {str(e)}. "
            f"Expected dict with 'files' (list) and 'file_data' (dict) fields."
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error parsing file batch data: {str(e)}", exc_info=True)
        # Don't fallback for unexpected errors - better to fail fast
        raise RuntimeError(f"Failed to parse file batch data: {str(e)}") from e

    # Extract context using dataclass (no fallback since we validate above)
    file_data = batch_data.file_data
    files = batch_data.files
    execution_id = file_data.execution_id
    workflow_id = file_data.workflow_id
    organization_id = file_data.organization_id

    # Additional context validation
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

    # Initialize result tracker using dataclass
    result = FileBatchResult()

    logger.info(
        f"Initializing file batch processing for execution {execution_id}, organization {organization_id}"
    )

    # Get workflow execution via API (instead of Django ORM)
    config = WorkerConfig()
    with InternalAPIClient(config) as api_client:
        api_client.set_organization_context(organization_id)

        # Get workflow execution context
        execution_context = api_client.get_workflow_execution(execution_id)
        workflow_execution = execution_context.get("execution", {})

        # Set log events ID in StateStore like Django backend
        log_events_id = workflow_execution.get("execution_log_id")
        if log_events_id:
            StateStore.set("LOG_EVENTS_ID", log_events_id)

        total_files = len(files)
        q_file_no_list = set(
            file_data.q_file_no_list
            if isinstance(file_data, WorkerFileData)
            else file_data.get("q_file_no_list", [])
        )

        logger.info(f"Processing {total_files} files of execution {execution_id}")

        # Update total_files in the WorkflowExecution so UI can show proper progress
        try:
            api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=ExecutionStatus.EXECUTING.value,
                total_files=total_files,
            )
            logger.info(
                f"Updated WorkflowExecution {execution_id} with total_files={total_files}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to update total_files for execution {execution_id}: {e}"
            )
            # Continue processing even if status update fails

        # Enhanced workflow type detection (API/ETL/TASK) by examining endpoints
        workflow_type, is_api_workflow = _detect_comprehensive_workflow_type(
            api_client, workflow_id
        )
        logger.info(
            f"Workflow {workflow_id} detected as type: {workflow_type} (is_api: {is_api_workflow})"
        )

        # CRITICAL: Pre-create all WorkflowFileExecution records to prevent duplicates
        # This matches the backend's _pre_create_file_executions pattern for ALL workflow types
        pre_created_file_executions = _pre_create_file_executions(
            files=files,
            workflow_id=workflow_id,
            execution_id=execution_id,
            api_client=api_client,
            workflow_type=workflow_type,
            is_api=is_api_workflow,
        )
        logger.info(
            f"Pre-created {len(pre_created_file_executions)} WorkflowFileExecution records for {workflow_type} workflow"
        )

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
            logger.info(
                f"[{celery_task_id}][{file_number}/{total_files}] Processing file '{file_name}'"
            )

            # Track individual file processing time
            file_start_time = time.time()

            # DEBUG: Log the file hash data being sent to ensure unique identification
            logger.info(
                f"File hash data for {file_name}: provider_file_uuid='{file_hash_dict.get('provider_file_uuid') if file_hash_dict else 'N/A'}', file_path='{file_hash_dict.get('file_path') if file_hash_dict else 'N/A'}'"
            )

            # Create file hash object matching Django FileHash structure
            file_hash: FileHashData = _create_file_hash_from_dict(file_hash_dict)

            # Add file destination using same logic as Django backend
            file_hash = _add_file_destination_filehash(
                file_hash.file_number, q_file_no_list, file_hash
            )

            logger.info(f"File hash for file {file_name}: {file_hash}")

            # Get pre-created WorkflowFileExecution data
            pre_created_data = pre_created_file_executions.get(file_name)
            if not pre_created_data:
                logger.error(
                    f"No pre-created WorkflowFileExecution found for file '{file_name}' - skipping"
                )
                result.increment_failure()
                continue

            workflow_file_execution_id = pre_created_data["id"]
            workflow_file_execution_object = pre_created_data["object"]

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
            )

            # NULL CHECK: Ensure file_execution_result is not None
            if file_execution_result is None:
                result.increment_failure()
                logger.error(
                    f"File execution for file {file_name} returned None - treating as failed"
                )

                # Update failed file count in cache
                try:
                    api_client.increment_failed_files(
                        workflow_id=workflow_id, execution_id=execution_id
                    )
                except Exception as increment_error:
                    logger.warning(
                        f"Failed to increment failed files count: {increment_error}"
                    )
                continue

            # Calculate file execution time
            file_execution_time = time.time() - file_start_time
            logger.info(
                f"File {file_name} processing completed in {file_execution_time:.2f} seconds"
            )

            # Update WorkflowFileExecution with execution time (fixes execution_time not being updated)
            file_execution_id = file_execution_result.get("file_execution_id")
            if file_execution_id:
                try:
                    final_status = (
                        "ERROR" if file_execution_result.get("error") else "COMPLETED"
                    )
                    api_client.update_file_execution_status(
                        file_execution_id=file_execution_id,
                        status=final_status,
                        execution_time=file_execution_time,
                        error_message=file_execution_result.get("error"),
                    )
                    logger.debug(
                        f"Updated file execution {file_execution_id} with status {final_status} and time {file_execution_time:.2f}s"
                    )
                except Exception as update_error:
                    logger.warning(
                        f"Failed to update file execution status for {file_name}: {update_error}"
                    )
            else:
                logger.warning(
                    f"No file_execution_id found for {file_name}, cannot update execution time"
                )

            # DJANGO PATTERN: Check error field to determine success/failure
            if file_execution_result.get("error"):
                result.increment_failure()
                logger.info(
                    f"File execution for file {file_name} marked as failed with error: {file_execution_result['error']}"
                )

                # Update failed file count in cache (like Django backend)
                try:
                    api_client.increment_failed_files(
                        workflow_id=workflow_id, execution_id=execution_id
                    )
                except Exception as increment_error:
                    logger.warning(
                        f"Failed to increment failed files count: {increment_error}"
                    )
            else:
                result.increment_success()
                logger.info(f"File execution for file {file_name} marked as successful")

                # Update completed file count in cache (like Django backend)
                try:
                    api_client.increment_completed_files(
                        workflow_id=workflow_id, execution_id=execution_id
                    )
                except Exception as increment_error:
                    logger.warning(
                        f"Failed to increment completed files count: {increment_error}"
                    )

                # Create file history entry for successful execution (CRITICAL FIX for deduplication)
                if file_data.use_file_history:
                    try:
                        file_history_manager = WorkerFileHistoryManager(api_client)
                        history_created = file_history_manager.create_file_history_entry(
                            workflow_id=workflow_id,
                            file_data=file_hash,
                            execution_result=file_execution_result,
                            organization_id=organization_id,
                        )
                        if history_created:
                            logger.info(
                                f"Created file history entry for successful file: {file_name}"
                            )
                        else:
                            logger.warning(
                                f"Failed to create file history entry for: {file_name}"
                            )
                    except Exception as history_error:
                        logger.error(
                            f"File history creation failed for {file_name}: {history_error}"
                        )
                        # Don't fail the entire execution if file history creation fails
                else:
                    logger.debug(
                        f"File history disabled for workflow {workflow_id}, skipping history entry for {file_name}"
                    )

            # Store execution time in result for aggregation
            result.add_execution_time(file_execution_time)

    # Return result using dataclass
    logger.info("Function tasks.process_file_batch completed successfully")
    return result.to_dict()


def _detect_comprehensive_workflow_type(
    api_client: InternalAPIClient, workflow_id: str
) -> tuple[str, bool]:
    """Detect workflow type (API/ETL/TASK) by examining source and destination endpoints.

    This matches the backend pattern in workflow_helper.py and source.py:
    - API workflows: Source=API -> Destination=API
    - ETL workflows: Source=FILESYSTEM -> Destination=DATABASE
    - TASK workflows: Source=FILESYSTEM -> Destination=FILESYSTEM/other

    Args:
        api_client: Internal API client
        workflow_id: Workflow ID

    Returns:
        tuple: (workflow_type: str, is_api: bool)
    """
    try:
        # Get workflow endpoints to determine types
        workflow_endpoints = api_client.get_workflow_endpoints(workflow_id)

        if isinstance(workflow_endpoints, dict):
            endpoints = workflow_endpoints.get("endpoints", [])

            # Find source and destination endpoints
            source_connection_type = None
            dest_connection_type = None

            for endpoint in endpoints:
                if endpoint.get("endpoint_type") == "SOURCE":
                    source_connection_type = endpoint.get("connection_type")
                elif endpoint.get("endpoint_type") == "DESTINATION":
                    dest_connection_type = endpoint.get("connection_type")

            # Determine workflow type based on endpoint combinations
            if source_connection_type == "API":
                return "API", True
            elif dest_connection_type == "DATABASE":
                return "ETL", False
            elif source_connection_type == "FILESYSTEM":
                return "TASK", False
            else:
                logger.warning(
                    f"Unknown endpoint combination: source={source_connection_type}, dest={dest_connection_type}"
                )
                return "TASK", False

        # Fallback: use legacy API detection
        elif isinstance(workflow_endpoints, dict) and workflow_endpoints.get(
            "has_api_endpoints", False
        ):
            return "API", True
        else:
            return "TASK", False

    except Exception as e:
        logger.warning(
            f"Failed to detect comprehensive workflow type for {workflow_id}: {e} - defaulting to TASK"
        )
        return "TASK", False


def _pre_create_file_executions(
    files: list[Any],
    workflow_id: str,
    execution_id: str,
    api_client: InternalAPIClient,
    workflow_type: str,
    is_api: bool = False,
) -> dict[str, Any]:
    """Pre-create WorkflowFileExecution records with PENDING status to prevent race conditions.

    This matches the backend's _pre_create_file_executions pattern for ALL workflow types
    and includes file history deduplication for ETL workflows.

    Args:
        files: List of file items (can be tuples, lists, or dicts)
        workflow_id: Workflow ID
        execution_id: Workflow execution ID
        api_client: Internal API client
        workflow_type: Workflow type (API/ETL/TASK)
        is_api: Whether this is an API workflow

    Returns:
        Dict mapping file names to {'id': str, 'object': WorkflowFileExecutionData}
    """
    pre_created_data = {}
    skipped_files = []

    # Get destination config for file history checking
    use_file_history = _should_use_file_history(api_client, workflow_id, workflow_type)

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
        file_hash = _create_file_hash_from_dict(file_hash_dict)

        # CRITICAL: File History Deduplication for ETL/TASK workflows
        if use_file_history and workflow_type in ["ETL", "TASK"]:
            if _is_file_already_processed(api_client, workflow_id, file_hash):
                logger.info(
                    f"Skipping already processed file '{file_name}' (hash: {file_hash.file_hash[:16]}...)"
                )
                skipped_files.append(file_name)
                continue

        # Convert to dict for API
        file_hash_dict_for_api = file_hash.to_dict()

        try:
            # Create WorkflowFileExecution record for ALL workflow types
            workflow_file_execution = api_client.get_or_create_workflow_file_execution(
                execution_id=execution_id,
                file_hash=file_hash_dict_for_api,
                workflow_id=workflow_id,
            )

            pre_created_data[file_name] = {
                "id": str(workflow_file_execution.id),
                "object": workflow_file_execution,
            }
            logger.info(
                f"Pre-created WorkflowFileExecution {workflow_file_execution.id} for {workflow_type} file '{file_name}'"
            )

        except Exception as e:
            logger.error(
                f"Failed to pre-create WorkflowFileExecution for '{file_name}': {str(e)}"
            )
            # Continue with other files even if one fails

    if skipped_files:
        logger.info(
            f"Skipped {len(skipped_files)} already processed files: {skipped_files}"
        )

    return pre_created_data


def _should_use_file_history(
    api_client: InternalAPIClient, workflow_id: str, workflow_type: str
) -> bool:
    """Determine if file history should be used for deduplication.

    Matches backend logic in destination.py where use_file_history is checked.
    """
    try:
        # Get workflow destination configuration
        workflow_endpoints = api_client.get_workflow_endpoints(workflow_id)
        if isinstance(workflow_endpoints, dict):
            endpoints = workflow_endpoints.get("endpoints", [])

            for endpoint in endpoints:
                if endpoint.get("endpoint_type") == "DESTINATION":
                    # Check if destination supports file history
                    destination_config = endpoint.get("configuration", {})
                    use_file_history = destination_config.get("use_file_history", True)

                    # ETL workflows typically use file history by default
                    if workflow_type == "ETL":
                        return use_file_history
                    # TASK workflows may or may not use history depending on destination
                    elif workflow_type == "TASK":
                        return use_file_history
                    # API workflows handle their own deduplication
                    else:
                        return False

        # Default: use file history for ETL/TASK workflows
        return workflow_type in ["ETL", "TASK"]

    except Exception as e:
        logger.warning(f"Failed to determine file history usage for {workflow_id}: {e}")
        # Conservative default: use file history for ETL/TASK
        return workflow_type in ["ETL", "TASK"]


def _is_file_already_processed(
    api_client: InternalAPIClient, workflow_id: str, file_hash: FileHashData
) -> bool:
    """Check if file is already processed using file history.

    Matches backend deduplication logic in source.py _is_new_file method.
    """
    try:
        # Check file history using the internal API
        # This should call an endpoint that checks FileHistory table
        params = {
            "workflow_id": workflow_id,
        }

        # Use file_hash as primary identifier
        if file_hash.file_hash:
            params["file_hash"] = file_hash.file_hash

        # Fallback to provider_file_uuid if no file_hash
        elif file_hash.provider_file_uuid:
            params["provider_file_uuid"] = file_hash.provider_file_uuid

        # Additional path-based check
        if file_hash.file_path:
            params["file_path"] = file_hash.file_path

        # Call internal API to check file history using the correct endpoint
        try:
            # Use POST request to send parameters in request body as expected by backend
            file_history_response = api_client.post(
                "v1/file-history/get/",
                {
                    "workflow_id": str(workflow_id),
                    "provider_file_uuid": file_hash.provider_file_uuid,
                    "file_path": str(file_hash.file_path),
                    "organization_id": api_client.organization_id,
                    "source_connection_type": file_hash.source_connection_type,  # Include source connection type for backend compatibility
                    "file_hash": file_hash.file_hash,  # Include file hash for better matching
                },
                organization_id=api_client.organization_id,
            )

            # Extract file history from response
            file_history = (
                file_history_response.get("file_history")
                if file_history_response
                else None
            )

            # File is already processed if history exists and is completed
            if file_history and isinstance(file_history, dict):
                is_completed = file_history.get("is_completed", False)
                status = file_history.get("status", "")

                return is_completed or status == "COMPLETED"
            elif (
                file_history and isinstance(file_history, list) and len(file_history) > 0
            ):
                # If multiple history records, check if any is completed
                for history_record in file_history:
                    if (
                        history_record.get("is_completed", False)
                        or history_record.get("status") == "COMPLETED"
                    ):
                        return True
                return False
            else:
                return False

        except Exception as api_error:
            # If file history API is not available, fallback to conservative approach
            logger.warning(
                f"File history API not available for {workflow_id}: {api_error}"
            )
            return False

    except Exception as e:
        logger.warning(f"Failed to check file history for {file_hash.file_name}: {e}")
        return False


def _parse_file_batch_data(file_batch_data) -> dict[str, Any]:
    """Parse file batch data exactly matching Django FileBatchData.from_dict() pattern.

    Args:
        file_batch_data: Raw batch data from chord task

    Returns:
        Parsed file batch data
    """
    if isinstance(file_batch_data, dict):
        return file_batch_data
    else:
        # Handle serialized data
        return file_batch_data


def _create_file_hash_from_dict(file_hash_dict: dict[str, Any]) -> FileHashData:
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
            mime_type="application/octet-stream",
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
            mime_type=file_hash_dict.get("mime_type") or "application/octet-stream",
            fs_metadata=file_hash_dict.get("fs_metadata") or {},
            file_destination=file_hash_dict.get("file_destination"),
            is_executed=file_hash_dict.get("is_executed", False),
            file_number=file_hash_dict.get("file_number"),
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

    return file_hash


def _add_file_destination_filehash(file_number, q_file_no_list, file_hash):
    """Add file destination using the same logic as Django WorkflowUtil.add_file_destination_filehash().

    Args:
        file_number: File number
        q_file_no_list: Set of file numbers
        file_hash: FileHashData instance

    Returns:
        Updated FileHashData instance
    """
    # This matches the Django backend logic for file destination
    # Update the dataclass field directly
    if file_number and file_number in q_file_no_list:
        file_hash.file_destination = "queue"
    else:
        file_hash.file_destination = "destination"

    return file_hash


def _process_file(
    current_file_idx: int,
    total_files: int,
    file_data: dict[str, Any],
    file_hash: FileHashData,
    api_client: InternalAPIClient,
    workflow_execution: dict[str, Any],
    workflow_file_execution_id: str = None,
    workflow_file_execution_object: Any = None,
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
    # Handle both WorkerFileData object and dictionary access for backward compatibility
    if hasattr(file_data, "execution_id"):
        execution_id = file_data.execution_id
        workflow_id = file_data.workflow_id
        organization_id = file_data.organization_id
    else:
        # Fallback for dictionary access
        execution_id = file_data["execution_id"]
        workflow_id = file_data["workflow_id"]
        organization_id = file_data["organization_id"]

    try:
        # Use dataclass attribute access for type-safe access
        file_name = file_hash.file_name or "unknown"
        logger.info(f"[Execution {execution_id}] Processing file: '{file_name}'")

        # Debug: Log the file hash data being sent to ensure unique identification
        logger.info(
            f"File hash data for {file_name}: provider_file_uuid='{file_hash.provider_file_uuid}', file_path='{file_hash.file_path}'"
        )

        # Convert FileHashData to dict for API client (which expects dict format)
        file_hash_dict = file_hash.to_dict()

        # CRITICAL: Always use pre-created workflow file execution to prevent duplicates
        if not workflow_file_execution_id or not workflow_file_execution_object:
            raise ValueError(
                f"No pre-created WorkflowFileExecution provided for file {file_hash.file_name}"
            )

        logger.info(
            f"Using pre-created workflow file execution: {workflow_file_execution_id}"
        )
        # Use the pre-created object directly (no need for additional API call)
        workflow_file_execution = workflow_file_execution_object

        logger.debug(
            f"Using pre-created workflow file execution: {workflow_file_execution}"
        )

        if not workflow_file_execution:
            raise Exception("Failed to create workflow file execution")

        # Check if file execution is already completed
        if workflow_file_execution.status == "COMPLETED":
            logger.info(
                f"File already completed. Skipping execution for execution_id: {execution_id}, file_execution_id: {workflow_file_execution.id}"
            )
            return {
                "file": file_name,
                "file_execution_id": workflow_file_execution.id,
                "error": None,
                "result": getattr(workflow_file_execution, "result", None),
                "metadata": getattr(workflow_file_execution, "metadata", None),
            }

        # Determine if this is an API workflow for result caching
        # Use the same comprehensive detection logic as workflow_service.detect_connection_type()
        is_api_workflow = _is_api_workflow(api_client, workflow_id, file_hash)
        logger.info(
            f"API workflow detection result: {is_api_workflow} for workflow {workflow_id}"
        )

        # Core execution phase - use WorkflowExecutionService directly
        workflow_service = WorkerWorkflowExecutionService(api_client)

        # Generate fallback hash if file_hash is empty to prevent KeyError
        content_hash = (file_hash.file_hash or "").strip()
        if not content_hash:
            # Generate fallback hash using file metadata for consistent identification
            import hashlib

            fallback_data = f"{file_hash.file_name or ''}{file_hash.file_path or ''}{file_hash.file_size or 0}"
            content_hash = hashlib.md5(fallback_data.encode()).hexdigest()
            logger.warning(
                f"Generated fallback hash for {file_hash.file_name}: {content_hash}"
            )

        execution_result = workflow_service.execute_workflow_for_file(
            organization_id=organization_id,
            workflow_id=workflow_id,
            file_data={
                "file_name": file_hash.file_name
                or "unknown",  # Type-safe dataclass access
                "file_path": file_hash.file_path or "",  # Type-safe dataclass access
                "file_hash": content_hash,  # Use generated hash if original is empty
                "mime_type": file_hash.mime_type
                or "application/octet-stream",  # Type-safe dataclass access
                "provider_file_uuid": file_hash.provider_file_uuid,  # CRITICAL FIX: Include provider_file_uuid
                "source_connection_type": file_hash.source_connection_type,  # Include for consistent API detection
                # Pass through connector metadata for FILESYSTEM workflows (stored in fs_metadata)
                "connector_metadata": file_hash.fs_metadata.get("connector_metadata")
                if file_hash.fs_metadata
                else None,
                "connector_id": file_hash.fs_metadata.get("connector_id")
                if file_hash.fs_metadata
                else None,
            },
            execution_id=execution_id,
            is_api=is_api_workflow,
            workflow_file_execution_id=str(
                workflow_file_execution.id
            ),  # CRITICAL FIX: Pass the ID
            workflow_file_execution_object=workflow_file_execution,  # CRITICAL FIX: Pass the object too!
        )

        # execution_result is already in Django FileExecutionResult format
        # Just return it directly (has file, file_execution_id, error, result, metadata)
        return execution_result

    except Exception as e:
        # Enhanced error handling with more context - use dataclass attribute access
        file_name = file_hash.file_name or "unknown" if file_hash else "unknown"
        provider_uuid = file_hash.provider_file_uuid or "N/A" if file_hash else "N/A"

        logger.error(
            f"Failed to process file '{file_name}' (provider_uuid: {provider_uuid}): {e}",
            exc_info=True,
        )
        logger.error(
            f"Error occurred during file processing for execution {execution_id}, workflow {workflow_id}"
        )

        # Try to get file execution ID safely
        file_execution_id = None
        if "workflow_file_execution" in locals() and workflow_file_execution:
            file_execution_id = getattr(workflow_file_execution, "id", None)

        # Return Django FileExecutionResult format for exceptions
        return {
            "file": file_name,
            "file_execution_id": file_execution_id,
            "error": f"File processing failed: {str(e)}",
            "result": None,
            "metadata": None,
        }


def _is_api_workflow(
    api_client: InternalAPIClient,
    workflow_id: str,
    file_hash: FileHashData,
    max_retries: int = 2,
) -> bool:
    """Enhanced API workflow detection with robust error handling and retries.

    Uses the enhanced detection logic from workflow_service.detect_connection_type()
    with additional error handling for improved reliability.

    Args:
        api_client: Internal API client
        workflow_id: Workflow ID to check
        file_hash: Optional file hash data for fallback detection
        max_retries: Maximum number of retries for API calls (default: 2)

    Returns:
        bool: True if this is an API workflow, False otherwise
    """
    detection_context = {
        "workflow_id": workflow_id,
        "file_source_type": file_hash.source_connection_type,
        "file_path_prefix": file_hash.file_path[:50],
        "detection_methods_tried": [],
    }

    try:
        logger.info(
            f"Enhanced API workflow detection for {workflow_id}: source_type={detection_context['file_source_type']}, path_prefix={detection_context['file_path_prefix']}"
        )

        # Method 1: Backend API endpoint check with retry logic
        endpoint_result = _check_workflow_endpoints_with_retry(
            api_client, workflow_id, max_retries
        )
        detection_context["detection_methods_tried"].append(
            f"endpoint_check: {endpoint_result['status']}"
        )

        if endpoint_result["success"]:
            if endpoint_result["is_api"]:
                logger.info(
                    f"Workflow {workflow_id} confirmed as API workflow via backend endpoint check: {endpoint_result['details']}"
                )
                return True
            else:
                logger.debug(
                    f"Workflow {workflow_id} confirmed as non-API workflow via backend endpoint check: {endpoint_result['details']}"
                )
                # Don't return False yet, check file data as backup
        else:
            logger.warning(
                f"Backend endpoint check failed for workflow {workflow_id}: {endpoint_result['error']}"
            )

        # Method 2: File data analysis (high-confidence fallback)
        if file_hash:
            file_result = _analyze_file_hash_for_api_indicators(workflow_id, file_hash)
            detection_context["detection_methods_tried"].append(
                f"file_analysis: {file_result['confidence']}"
            )

            # High confidence file-based detection
            if file_result["confidence"] == "high" and file_result["is_api"]:
                logger.info(
                    f"Workflow {workflow_id} detected as API workflow from high-confidence file analysis: {file_result['reason']}"
                )
                return True
            elif file_result["confidence"] == "high" and not file_result["is_api"]:
                logger.info(
                    f"Workflow {workflow_id} detected as non-API workflow from high-confidence file analysis: {file_result['reason']}"
                )
                return False

            # Medium confidence - use if endpoint check failed
            if not endpoint_result["success"] and file_result["confidence"] == "medium":
                logger.info(
                    f"Using medium-confidence file analysis for workflow {workflow_id}: {file_result['reason']}"
                )
                return file_result["is_api"]

        # Method 3: Graceful degradation
        if endpoint_result["success"]:
            # Use endpoint result as final decision
            return endpoint_result["is_api"]

        # Default fallback with detailed logging
        logger.info(
            f"Workflow {workflow_id} detection completed - methods tried: {', '.join(detection_context['detection_methods_tried'])}"
        )
        logger.info(
            f"Defaulting to non-API workflow for {workflow_id} (conservative fallback)"
        )
        return False

    except Exception as e:
        logger.error(
            f"Critical error in API workflow detection for {workflow_id}: {str(e)}",
            exc_info=True,
        )
        logger.info(f"Detection context when error occurred: {detection_context}")
        # Conservative fallback - assume non-API to avoid breaking functionality
        return False


def _check_workflow_endpoints_with_retry(
    api_client: InternalAPIClient, workflow_id: str, max_retries: int
) -> dict[str, Any]:
    """Check workflow endpoints with retry logic and sophisticated response analysis."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            workflow_endpoints = api_client.get_workflow_endpoints(workflow_id)

            # Handle new enhanced response format
            if isinstance(workflow_endpoints, dict):
                has_api = workflow_endpoints.get("has_api_endpoints", False)
                endpoints = workflow_endpoints.get("endpoints", [])

                api_endpoint_count = 0
                total_active_endpoints = 0

                for endpoint in endpoints:
                    if endpoint.get("is_active", True):
                        total_active_endpoints += 1
                        connection_type_str = endpoint.get("connection_type", "").upper()
                        endpoint_type = endpoint.get("endpoint_type", "").upper()

                        if (
                            connection_type_str == "API"
                            or endpoint_type == "API_DEPLOYMENT"
                        ):
                            api_endpoint_count += 1

                return {
                    "success": True,
                    "is_api": has_api or api_endpoint_count > 0,
                    "status": "new_format_success",
                    "details": f"API endpoints: {api_endpoint_count}/{total_active_endpoints}, has_api_flag: {has_api}",
                }

            # Handle legacy response format
            elif isinstance(workflow_endpoints, list):
                if len(workflow_endpoints) > 0:
                    return {
                        "success": True,
                        "is_api": True,
                        "status": "legacy_format_success",
                        "details": f"Found {len(workflow_endpoints)} endpoints (legacy format)",
                    }
                else:
                    return {
                        "success": True,
                        "is_api": False,
                        "status": "legacy_format_empty",
                        "details": "Empty endpoint list (legacy format)",
                    }

            # Handle invalid response
            else:
                return {
                    "success": True,
                    "is_api": False,
                    "status": "invalid_response",
                    "details": f"Invalid response type: {type(workflow_endpoints)}",
                }

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                logger.warning(
                    f"Endpoint check attempt {attempt + 1}/{max_retries + 1} failed for workflow {workflow_id}: {e}"
                )
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff
            else:
                logger.error(
                    f"All {max_retries + 1} endpoint check attempts failed for workflow {workflow_id}: {e}"
                )

    return {
        "success": False,
        "is_api": False,
        "status": "api_failure",
        "error": last_error or "Unknown error",
    }


def _analyze_file_hash_for_api_indicators(
    workflow_id: str, file_hash: FileHashData
) -> dict[str, Any]:
    """Analyze file hash data for API workflow indicators with confidence scoring."""
    file_path = file_hash.file_path
    source_connection_type = file_hash.source_connection_type

    # High confidence indicators
    if source_connection_type == ConnectionType.API.value:
        return {
            "is_api": True,
            "confidence": "high",
            "reason": "source_connection_type field is 'API'",
        }

    if (
        source_connection_type
        and source_connection_type.upper() == ConnectionType.FILESYSTEM.value
    ):
        return {
            "is_api": False,
            "confidence": "high",
            "reason": "source_connection_type field is 'FILESYSTEM'",
        }

    # Medium confidence indicators
    if file_path.startswith("unstract/api/"):
        return {
            "is_api": True,
            "confidence": "medium",
            "reason": f"file path starts with 'unstract/api/': {file_path[:50]}...",
        }

    if "/api/" in file_path and "unstract" in file_path:
        return {
            "is_api": True,
            "confidence": "medium",
            "reason": f"file path contains API pattern: {file_path[:50]}...",
        }

    # Filesystem path indicators
    if file_path.startswith("/") or file_path.startswith("./") or "\\" in file_path:
        return {
            "is_api": False,
            "confidence": "medium",
            "reason": f"file path appears to be local filesystem: {file_path[:50]}...",
        }

    # Low confidence - unclear
    return {
        "is_api": False,
        "confidence": "low",
        "reason": f"no clear indicators - source_type: '{source_connection_type}', path: '{file_path[:30]}...'",
    }


@app.task(
    bind=True,
    name="process_file_batch_api",
    max_retries=0,  # Match Django backend
    ignore_result=False,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
    default_retry_delay=5,
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
        batch_id=batch_id,
        pipeline_id=pipeline_id,
    ):
        logger.info(
            f"Processing API file batch {batch_id} with {len(created_files)} files"
        )

        try:
            # Set organization context exactly like Django backend
            StateStore.set(Account.ORGANIZATION_ID, schema_name)

            # Initialize API client with organization context
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Get workflow execution context
                execution_context = api_client.get_workflow_execution(execution_id)
                workflow_execution = execution_context.get("execution", {})

                # Set log events ID in StateStore like Django backend
                log_events_id = workflow_execution.get("execution_log_id")
                if log_events_id:
                    StateStore.set("LOG_EVENTS_ID", log_events_id)

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

        except Exception as e:
            logger.error(f"API file batch processing failed for {batch_id}: {e}")
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
        logger.error(
            f"Failed to process file {file_name} after {processing_time:.2f}s: {e}"
        )

        # Try to update file execution status to failed
        try:
            api_client.update_file_execution_status(
                file_execution_id=file_execution_id, status="FAILED", error_message=str(e)
            )
        except Exception as update_error:
            logger.error(f"Failed to update file execution status: {update_error}")

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

        history_result = api_client.get_file_history_by_cache_key(
            cache_key=cache_key,
            workflow_id=workflow_id,
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
        "payload": (None, json.dumps(payload), "application/json"),
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
        except Exception as e:
            logger.error(f"Unexpected error calling runner service: {e}")
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
    return mime_type or "application/octet-stream"


def _process_single_file(
    api_client: InternalAPIClient,
    workflow_id: str,
    execution_id: str,
    file_key: str,
    file_hash_data: dict[str, Any],
    workflow_data: dict[str, Any],
    use_file_history: bool,
    is_api: bool,
    pipeline_id: str | None = None,
) -> dict[str, Any]:
    """Process a single file using internal APIs.

    This implements the hybrid approach where file coordination happens via APIs
    but actual tool execution is handled by Django backend.
    """
    logger.info(f" ==========_process_single_file=========== Processing file: {file_key}")
    start_time = time.time()

    try:
        file_name = file_hash_data.get("file_name", file_key)
        cache_key = file_hash_data.get("cache_key", file_key)

        logger.info(f"Processing file: {file_name}")

        # Check file history if enabled
        if use_file_history:
            history_result = api_client.get_file_history_by_cache_key(
                cache_key=cache_key,
                workflow_id=workflow_id,
                file_path=file_hash_data.get("file_path"),
            )

            if history_result.get("found"):
                logger.info(f"File {file_name} found in history, skipping processing")
                return {
                    "file_key": file_key,
                    "file_name": file_name,
                    "status": "skipped",
                    "reason": "found_in_history",
                    "processing_time": time.time() - start_time,
                    "cache_key": cache_key,
                }

        # Get tool instances for the workflow
        tools_result = api_client.get_tool_instances_by_workflow(workflow_id)
        tool_instances = tools_result.get("tool_instances", [])

        if not tool_instances:
            logger.warning(f"No tool instances found for workflow {workflow_id}")
            return {
                "file_key": file_key,
                "file_name": file_name,
                "status": "error",
                "error": "no_tool_instances",
                "processing_time": time.time() - start_time,
            }

        # Execute tools in sequence using internal APIs
        tool_results = []
        current_input = file_hash_data

        for tool_instance in sorted(tool_instances, key=lambda t: t.get("step", 0)):
            tool_result = _execute_tool_for_file(
                api_client=api_client,
                tool_instance=tool_instance,
                file_data=current_input,
                execution_context={
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    "file_key": file_key,
                    "pipeline_id": pipeline_id,
                    "is_api": is_api,
                },
            )

            tool_results.append(tool_result)

            # Use tool output as input for next tool
            if tool_result.get("status") == "success":
                current_input = tool_result.get("output", current_input)
            else:
                # Stop processing if tool fails
                logger.error(
                    f"Tool execution failed for {file_name}: {tool_result.get('error')}"
                )
                break

        # Create file history record if processing was successful
        if use_file_history and all(tr.get("status") == "success" for tr in tool_results):
            try:
                api_client.create_file_history(
                    workflow_id=workflow_id,
                    file_name=file_hash_data.get("file_name", "unknown"),
                    file_path=file_hash_data.get("file_path", ""),
                    file_hash=file_hash_data.get("file_hash", ""),
                    file_size=file_hash_data.get("file_size", 0),
                    mime_type=file_hash_data.get("mime_type", ""),
                    provider_file_uuid=file_hash_data.get("provider_file_uuid"),
                    result=str(current_input) if current_input else "",
                    metadata="",  # Can be populated with workflow metadata if needed
                    status="COMPLETED",
                    is_api=is_api,
                )
                logger.info(f"Created file history record for {file_name}")
            except Exception as e:
                logger.warning(f"Failed to create file history for {file_name}: {e}")

        processing_time = time.time() - start_time

        # Determine overall status
        if all(tr.get("status") == "success" for tr in tool_results):
            status = "success"
        elif any(tr.get("status") == "success" for tr in tool_results):
            status = "partial_success"
        else:
            status = "error"

        result = {
            "file_key": file_key,
            "file_name": file_name,
            "status": status,
            "processing_time": processing_time,
            "tools_executed": len(tool_results),
            "tool_results": tool_results,
            "cache_key": cache_key,
            "final_output": current_input,
        }

        logger.info(
            f"Completed processing file {file_name} in {processing_time:.2f}s: {status}"
        )

        return result

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Failed to process file {file_key}: {e}")

        return {
            "file_key": file_key,
            "file_name": file_hash_data.get("file_name", file_key),
            "status": "error",
            "error": str(e),
            "processing_time": processing_time,
        }


def _execute_tool_for_file(
    api_client: InternalAPIClient,
    tool_instance: dict[str, Any],
    file_data: dict[str, Any],
    execution_context: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single tool for a file using internal APIs.

    This calls the Django backend to perform the actual tool execution
    while maintaining coordination in the lightweight worker.
    """
    tool_id = tool_instance.get("id")
    tool_function = tool_instance.get("tool_function")

    try:
        logger.info(f"Executing tool {tool_function} (ID: {tool_id}) for file")

        # Call Django backend to execute the tool
        execution_result = api_client.execute_tool(
            tool_instance_id=tool_id,
            input_data=file_data,
            file_data=file_data,
            execution_context=execution_context,
        )

        if execution_result.get("status") == "success":
            return {
                "tool_id": tool_id,
                "tool_function": tool_function,
                "step": tool_instance.get("step"),
                "status": "success",
                "output": execution_result.get("execution_result"),
                "execution_time": execution_result.get("execution_time", 0),
            }
        else:
            return {
                "tool_id": tool_id,
                "tool_function": tool_function,
                "step": tool_instance.get("step"),
                "status": "error",
                "error": execution_result.get("error_message", "Tool execution failed"),
            }

    except Exception as e:
        logger.error(f"Failed to execute tool {tool_function}: {e}")
        return {
            "tool_id": tool_id,
            "tool_function": tool_function,
            "step": tool_instance.get("step"),
            "status": "error",
            "error": str(e),
        }


# Simple resilient executor decorator (placeholder)
def resilient_executor(func):
    """Simple resilient executor decorator."""
    return func


# Resilient file processor
@app.task(bind=True)
@resilient_executor
def process_file_batch_resilient(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    """Resilient file batch processing with advanced error handling."""
    task_id = self.request.id

    with log_context(task_id=task_id, execution_id=execution_id, workflow_id=workflow_id):
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
