"""API Deployment Worker Tasks

Exact implementation matching Django backend patterns for API deployment tasks.
Uses the same patterns as workflow_helper.py and file_execution_tasks.py
"""

import time
from typing import Any

# Import shared worker infrastructure
from shared.api_client import InternalAPIClient
from shared.config import WorkerConfig

# Import from shared worker modules
from shared.constants import Account
from shared.local_context import StateStore
from shared.logging_utils import WorkerLogger, log_context, monitor_performance
from shared.retry_utils import retry

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus, FileHashData

# Import from local worker module (avoid circular import)
from .worker import app

# Note: FileExecutionResult removed - file worker now handles all result caching

logger = WorkerLogger.get_logger(__name__)


@app.task(
    bind=True,
    name="async_execute_bin_api",
    autoretry_for=(Exception,),
    max_retries=0,  # Match Django backend pattern
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
@monitor_performance
def async_execute_bin_api(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[
        str, dict | FileHashData
    ],  # Backend sends dicts, we convert to FileHashData
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    log_events_id: str | None = None,
    use_file_history: bool = False,
    **kwargs: dict[str, Any],
) -> dict[str, Any]:
    """API deployment workflow execution task.

    This matches exactly the Django backend pattern for API deployments,
    following the same execution flow as the current system.

    Args:
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        hash_values_of_files: File hash data
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        pipeline_id: Pipeline ID (for API deployments)
        log_events_id: Log events ID
        use_file_history: Whether to use file history

    Returns:
        Execution result dictionary
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
    ):
        # Convert hash_values_of_files from dicts to FileHashData objects if needed
        # Backend sends file_hash_in_str which contains .to_json() results (dicts)
        converted_files = {}
        for file_key, file_data in (hash_values_of_files or {}).items():
            if isinstance(file_data, dict):
                # Convert dict back to FileHashData object
                try:
                    converted_files[file_key] = FileHashData.from_dict(file_data)
                except Exception as e:
                    logger.warning(f"Failed to convert file data for {file_key}: {e}")
                    continue
            elif isinstance(file_data, FileHashData):
                # Already correct type
                converted_files[file_key] = file_data
            else:
                logger.warning(
                    f"Unexpected file data type for {file_key}: {type(file_data)}"
                )
                continue

        hash_values_of_files = converted_files

        # DEBUG: Log all task parameters for debugging K8s vs local differences
        logger.info(
            f"Starting API deployment execution for workflow {workflow_id}, execution {execution_id}"
        )
        logger.info(
            f"DEBUG: Task received parameters - schema_name='{schema_name}' (type: {type(schema_name).__name__})"
        )
        logger.info(
            f"DEBUG: Task parameters - workflow_id={workflow_id}, execution_id={execution_id}"
        )
        logger.info(
            f"DEBUG: Task parameters - pipeline_id={pipeline_id}, scheduled={scheduled}"
        )
        logger.info(
            f"DEBUG: Task parameters - files_count={len(hash_values_of_files) if hash_values_of_files else 0}"
        )

        try:
            # DEBUG: Verify schema_name before using it
            if (
                schema_name is None
                or schema_name == ""
                or str(schema_name).lower() == "none"
            ):
                logger.error(
                    f"CRITICAL: Invalid schema_name received: '{schema_name}' - this will cause organization context issues!"
                )
            else:
                logger.info(f"DEBUG: Valid schema_name received: '{schema_name}'")

            # Set organization context in StateStore (matching Django pattern)
            StateStore.set(Account.ORGANIZATION_ID, schema_name)
            logger.info(f"DEBUG: Set StateStore organization_id to: '{schema_name}'")

            # Initialize API client with organization context
            config = WorkerConfig()
            logger.info(
                f"DEBUG: Worker config - internal_api_base_url: '{config.internal_api_base_url}'"
            )
            logger.info(
                f"DEBUG: Worker config - internal_api_key present: {bool(config.internal_api_key)}"
            )

            with InternalAPIClient(config) as api_client:
                logger.info(
                    f"DEBUG: Before set_organization_context - schema_name: '{schema_name}'"
                )
                api_client.set_organization_context(schema_name)
                logger.info(
                    "DEBUG: After set_organization_context - organization set on API client"
                )

                # Get workflow execution context
                api_client.get_workflow_execution(execution_id)
                logger.info(f"Retrieved execution context for {execution_id}")

                # Run workflow using the exact same pattern as Django backend
                return _run_workflow_api(
                    api_client=api_client,
                    schema_name=schema_name,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    hash_values_of_files=hash_values_of_files,
                    scheduled=scheduled,
                    execution_mode=execution_mode,
                    pipeline_id=pipeline_id,
                    use_file_history=use_file_history,
                    task_id=task_id,
                )

        except Exception as e:
            logger.error(f"API deployment execution failed for {execution_id}: {e}")

            # Try to update execution status to failed (matching Django pattern)
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                        attempts=self.request.retries + 1,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            # Re-raise for Celery retry mechanism
            raise


# Add alias for backward compatibility with backend
@app.task(
    bind=True,
    name="async_execute_bin",  # Backend sends this name
    autoretry_for=(Exception,),
    max_retries=0,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
@monitor_performance
def async_execute_bin(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[
        str, dict | FileHashData
    ],  # Backend sends dicts, we convert to FileHashData
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    log_events_id: str | None = None,
    use_file_history: bool = False,
    **kwargs: dict[str, Any],
) -> dict[str, Any]:
    """API deployment workflow execution task (alias for backend compatibility).

    The backend sends 'async_execute_bin' tasks but we want to handle them
    as API deployments. This is identical to async_execute_bin_api.
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
    ):
        # Convert hash_values_of_files from dicts to FileHashData objects if needed
        # Backend sends file_hash_in_str which contains .to_json() results (dicts)
        converted_files = {}
        for file_key, file_data in (hash_values_of_files or {}).items():
            if isinstance(file_data, dict):
                # Convert dict back to FileHashData object
                try:
                    converted_files[file_key] = FileHashData.from_dict(file_data)
                except Exception as e:
                    logger.warning(f"Failed to convert file data for {file_key}: {e}")
                    continue
            elif isinstance(file_data, FileHashData):
                # Already correct type
                converted_files[file_key] = file_data
            else:
                logger.warning(
                    f"Unexpected file data type for {file_key}: {type(file_data)}"
                )
                continue

        hash_values_of_files = converted_files

        # DEBUG: Log all task parameters for debugging K8s vs local differences
        logger.info(
            f"Starting API deployment execution for workflow {workflow_id}, execution {execution_id} [async_execute_bin alias]"
        )
        logger.info(
            f"DEBUG: Task received parameters - schema_name='{schema_name}' (type: {type(schema_name).__name__})"
        )
        logger.info(
            f"DEBUG: Task parameters - workflow_id={workflow_id}, execution_id={execution_id}"
        )
        logger.info(
            f"DEBUG: Task parameters - pipeline_id={pipeline_id}, scheduled={scheduled}"
        )
        logger.info(
            f"DEBUG: Task parameters - files_count={len(hash_values_of_files) if hash_values_of_files else 0}"
        )

        try:
            # DEBUG: Verify schema_name before using it
            if (
                schema_name is None
                or schema_name == ""
                or str(schema_name).lower() == "none"
            ):
                logger.error(
                    f"CRITICAL: Invalid schema_name received: '{schema_name}' - this will cause organization context issues!"
                )
            else:
                logger.info(f"DEBUG: Valid schema_name received: '{schema_name}'")

            # Set organization context in StateStore (matching Django pattern)
            StateStore.set(Account.ORGANIZATION_ID, schema_name)
            logger.info(f"DEBUG: Set StateStore organization_id to: '{schema_name}'")

            # Initialize API client with organization context
            config = WorkerConfig()
            logger.info(
                f"DEBUG: Worker config - internal_api_base_url: '{config.internal_api_base_url}'"
            )
            logger.info(
                f"DEBUG: Worker config - internal_api_key present: {bool(config.internal_api_key)}"
            )

            with InternalAPIClient(config) as api_client:
                logger.info(
                    f"DEBUG: Before set_organization_context - schema_name: '{schema_name}'"
                )
                api_client.set_organization_context(schema_name)
                logger.info(
                    "DEBUG: After set_organization_context - organization set on API client"
                )

                # Get workflow execution context
                api_client.get_workflow_execution(execution_id)
                logger.info(f"Retrieved execution context for {execution_id}")

                # Run workflow using the exact same pattern as Django backend
                return _run_workflow_api(
                    api_client=api_client,
                    schema_name=schema_name,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    hash_values_of_files=hash_values_of_files,
                    scheduled=scheduled,
                    execution_mode=execution_mode,
                    pipeline_id=pipeline_id,
                    use_file_history=use_file_history,
                    task_id=task_id,
                )

        except Exception as e:
            logger.error(f"API deployment execution failed for {execution_id}: {e}")

            # Try to update execution status to failed (matching Django pattern)
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                        attempts=self.request.retries + 1,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            # Re-raise for Celery retry mechanism
            raise


def _run_workflow_api(
    api_client: InternalAPIClient,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, FileHashData],  # Already converted in task
    scheduled: bool,
    execution_mode: tuple | None,
    pipeline_id: str | None,
    use_file_history: bool,
    task_id: str,
) -> dict[str, Any]:
    """Run workflow matching the exact pattern from Django backend.

    This follows the same logic as WorkflowHelper.run_workflow() and
    WorkflowHelper.process_input_files() methods.
    """
    total_files = len(hash_values_of_files)

    # Update total_files immediately so UI can show proper progress (fixes race condition)
    api_client.update_workflow_execution_status(
        execution_id=execution_id,
        status=ExecutionStatus.EXECUTING.value,
        total_files=total_files,
    )

    logger.info(f"Processing {total_files} files for execution {execution_id}")

    if not hash_values_of_files:
        logger.info(f"Execution {execution_id} no files to process")
        # Complete immediately with no files
        api_client.update_workflow_execution_status(
            execution_id=execution_id, status=ExecutionStatus.COMPLETED.value
        )

        # Update pipeline status if needed
        if pipeline_id:
            api_client.update_pipeline_status(
                pipeline_id=pipeline_id,
                execution_id=execution_id,
                status=ExecutionStatus.COMPLETED.value,
            )

        return {
            "status": "completed",
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "files_processed": 0,
            "message": "No files to process",
        }

    # Check file history if enabled - get both files to process and cached results
    files_to_process = hash_values_of_files
    cached_results = {}
    if use_file_history:
        files_to_process, cached_results = _check_file_history_api(
            api_client=api_client,
            workflow_id=workflow_id,
            hash_values_of_files=hash_values_of_files,
            execution_id=execution_id,
        )

        # Mark cached files as executed and send ALL files to file worker
        if cached_results:
            logger.info(
                f"Marking {len(cached_results)} files as already executed (cached)"
            )
            for file_hash_str, cached_result in cached_results.items():
                # Find the corresponding FileHashData object and mark it as executed
                for hash_data in hash_values_of_files.values():
                    if hash_data.file_hash == file_hash_str:
                        hash_data.is_executed = True
                        logger.info(
                            f"Marked file {hash_data.file_name} as is_executed=True"
                        )
                        break

    # Send ALL files to file worker (both cached and non-cached)
    # File worker will handle cached files by checking is_executed flag
    files_to_send = hash_values_of_files  # Send all files, not just non-cached ones
    total_files = len(files_to_send)
    cached_count = len(cached_results)
    if use_file_history:
        logger.info(
            f"Sending {total_files} files to file worker: {cached_count} cached, {total_files - cached_count} to process"
        )
    else:
        logger.info(f"Sending {total_files} files to file worker (file history disabled)")

    # Get file batches using the exact same logic as Django backend
    batches = _get_file_batches(files_to_send)
    logger.info(
        f"Execution {execution_id} processing {total_files} files in {len(batches)} batches"
    )

    # Create batch tasks following the exact Django pattern
    batch_tasks = []
    execution_mode_str = (
        (execution_mode[1] if isinstance(execution_mode, tuple) else str(execution_mode))
        if execution_mode
        else None
    )

    for batch in batches:
        # Create file data exactly matching Django FileBatchData structure
        file_data = _create_file_data(
            workflow_id=workflow_id,
            execution_id=execution_id,
            organization_id=schema_name,
            pipeline_id=pipeline_id,
            scheduled=scheduled,
            execution_mode=execution_mode_str,
            use_file_history=use_file_history,
            api_client=api_client,
            total_files=total_files,
        )

        # Calculate manual review decisions for this specific batch
        if file_data.get("manual_review_config", {}).get("review_required", False):
            file_decisions = _calculate_manual_review_decisions_for_batch_api(
                batch=batch, manual_review_config=file_data["manual_review_config"]
            )
            # Update the file_data with batch-specific decisions
            file_data["manual_review_config"]["file_decisions"] = file_decisions
            logger.info(
                f"Calculated manual review decisions for API batch: {sum(file_decisions)}/{len(file_decisions)} files selected"
            )

        # Create batch data exactly matching Django FileBatchData structure
        batch_data = _create_batch_data(files=batch, file_data=file_data)

        # Determine queue using the same logic as Django backend
        file_processing_queue = _get_queue_name_api()

        # Create task signature matching Django backend pattern
        batch_tasks.append(
            app.signature(
                "process_file_batch",  # Use same task name as Django
                args=[batch_data],
                queue=file_processing_queue,
            )
        )

    try:
        # Create callback queue using same logic as Django backend
        file_processing_callback_queue = _get_callback_queue_name_api()

        # Execute chord exactly matching Django pattern
        from celery import chord

        result = chord(batch_tasks)(
            app.signature(
                "process_batch_callback_api",  # Use API-specific callback
                kwargs={
                    "execution_id": str(execution_id),
                    "pipeline_id": str(pipeline_id) if pipeline_id else None,
                    "organization_id": str(schema_name),
                },  # Pass required parameters for API callback
                queue=file_processing_callback_queue,
            )
        )

        if not result:
            exception = f"Failed to queue execution task {execution_id}"
            logger.error(exception)
            raise Exception(exception)

        logger.info(f"Execution {execution_id} task queued successfully")

        return {
            "status": "orchestrated",
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "files_processed": total_files,
            "files_from_cache": len(cached_results),
            "batches_created": len(batches),
            "chord_id": result.id,
            "cached_results": list(cached_results.keys())
            if cached_results
            else [],  # Include cache info
            "message": f"File processing orchestrated: {total_files} files processing, {len(cached_results)} from cache",
        }

    except Exception as e:
        # Update execution to ERROR status matching Django pattern
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.ERROR.value,
            error_message=f"Error while processing files: {str(e)}",
        )
        logger.error(f"Execution {execution_id} failed: {str(e)}", exc_info=True)
        raise


def _get_file_batches(input_files: dict[str, FileHashData] | list[dict]) -> list:
    """Get file batches using the exact same logic as Django backend.

    This matches WorkflowHelper.get_file_batches() exactly.

    Args:
        input_files: Dictionary of file hash data or list of file dictionaries (for backward compatibility)

    Returns:
        List of file batches
    """
    import math
    import os

    # Handle both list and dict formats for backward compatibility
    if isinstance(input_files, list):
        # Convert list format to dict format
        logger.info(f"Converting list format to dict format for {len(input_files)} files")
        dict_files = {}
        for file_data in input_files:
            if isinstance(file_data, dict):
                file_name = file_data.get("file_name", f"file_{len(dict_files)}")
                # Handle duplicate file names
                if file_name in dict_files:
                    base_name, ext = os.path.splitext(file_name)
                    counter = 1
                    while f"{base_name}_{counter}{ext}" in dict_files:
                        counter += 1
                    file_name = f"{base_name}_{counter}{ext}"
                    logger.warning(
                        f"Duplicate file name detected, renamed to: {file_name}"
                    )
                dict_files[file_name] = file_data
            else:
                logger.error(f"Unexpected file data type in list: {type(file_data)}")
                continue
        input_files = dict_files
    elif not isinstance(input_files, dict):
        logger.error(
            f"Unexpected input_files type: {type(input_files)}, expected dict or list"
        )
        raise TypeError(f"input_files must be dict or list, got {type(input_files)}")

    # Convert FileHashData objects to serializable format for batching
    json_serializable_files = {}
    for file_name, file_hash_data in input_files.items():
        if isinstance(file_hash_data, FileHashData):
            json_serializable_files[file_name] = file_hash_data.to_dict()
        elif isinstance(file_hash_data, dict):
            # Backward compatibility for dict format
            json_serializable_files[file_name] = file_hash_data
        else:
            logger.error(
                f"Unexpected file data type for '{file_name}': {type(file_hash_data)}"
            )
            continue

    # Prepare batches of files for parallel processing (exact Django logic)
    BATCH_SIZE = int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "4"))  # Default from Django
    file_items = list(json_serializable_files.items())

    # Calculate how many items per batch (exact Django logic)
    num_files = len(file_items)
    num_batches = min(BATCH_SIZE, num_files)
    items_per_batch = math.ceil(num_files / num_batches)

    # Split into batches (exact Django logic)
    batches = []
    for start_index in range(0, len(file_items), items_per_batch):
        end_index = start_index + items_per_batch
        batch = file_items[start_index:end_index]
        batches.append(batch)

    return batches


def _calculate_q_file_no_list_api(
    manual_review_config: dict, total_files: int
) -> list[int]:
    """Get pre-calculated file numbers for manual review queue for API deployments.

    This uses the pre-calculated q_file_no_list from the ManualReviewAPIClient
    which matches the Django backend WorkflowUtil.get_q_no_list() logic.

    Args:
        manual_review_config: Manual review configuration with pre-calculated list
        total_files: Total number of files (not used, kept for compatibility)

    Returns:
        List of file numbers (1-indexed) that should go to manual review
    """
    if not manual_review_config:
        return []

    # Use pre-calculated list from the client if available
    q_file_no_list = manual_review_config.get("q_file_no_list", [])
    if q_file_no_list:
        return q_file_no_list

    # Fallback to percentage calculation if pre-calculated list is not available
    percentage = manual_review_config.get("review_percentage", 0)
    if percentage <= 0 or total_files <= 0:
        return []

    # Match Django backend _mrq_files() logic exactly as fallback
    import random

    num_to_select = max(1, int(total_files * (percentage / 100)))
    return list(set(random.sample(range(1, total_files + 1), num_to_select)))


def _create_file_data(
    workflow_id: str,
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None,
    scheduled: bool,
    execution_mode: str | None,
    use_file_history: bool,
    api_client: InternalAPIClient,
    total_files: int = 0,
) -> dict[str, Any]:
    """Create file data matching Django FileData structure exactly.

    Args:
        workflow_id: Workflow ID
        execution_id: Execution ID
        organization_id: Organization ID
        pipeline_id: Pipeline ID
        scheduled: Whether scheduled execution
        execution_mode: Execution mode string
        use_file_history: Whether to use file history
        api_client: API client for fetching manual review rules

    Returns:
        File data dictionary matching Django FileData with manual review config
    """
    # Initialize manual review config with defaults
    manual_review_config = {
        "review_required": False,
        "review_percentage": 0,
        "rule_logic": None,
        "rule_json": None,
    }

    # ARCHITECTURE FIX: Skip manual review DB rules for API deployments
    # API deployments handle manual review through different mechanisms (if supported)
    # The DB rules endpoint is designed for ETL workflows, not API deployments
    logger.info(
        "API deployment workflow detected - skipping manual review DB rules lookup"
    )

    # For future: API deployments could support manual review through other mechanisms
    # such as workflow-specific configuration or query parameters passed in the API request
    logger.info(
        f"No manual review rules configured for API deployment workflow {workflow_id}"
    )

    # Keep the default manual_review_config (review_required=False, percentage=0)

    return {
        "workflow_id": str(workflow_id),
        "execution_id": str(execution_id),
        "organization_id": str(organization_id),
        "pipeline_id": str(pipeline_id) if pipeline_id else None,
        "scheduled": scheduled,
        "execution_mode": execution_mode,
        "use_file_history": use_file_history,
        "single_step": False,  # API deployments are always complete execution
        "q_file_no_list": _calculate_q_file_no_list_api(
            manual_review_config, total_files
        ),
        "manual_review_config": manual_review_config,  # Add manual review configuration
    }


def _create_batch_data(files: list, file_data: dict[str, Any]) -> dict[str, Any]:
    """Create batch data matching Django FileBatchData structure exactly.

    Args:
        files: List of (file_name, file_hash) tuples
        file_data: File data dictionary

    Returns:
        Batch data dictionary matching Django FileBatchData
    """
    return {"files": files, "file_data": file_data}


def _get_queue_name_api() -> str:
    """Get queue name for API file processing matching Django logic.

    This matches FileExecutionTasks.get_queue_name() for API deployments.

    Returns:
        Queue name for API file processing
    """
    # For API deployments, use api_file_processing queue
    return "api_file_processing"


def _get_callback_queue_name_api() -> str:
    """Get callback queue name for API deployments matching Django logic.

    This matches FileExecutionTasks.get_queue_name() for API callbacks.

    Returns:
        Queue name for API file processing callbacks
    """
    # For API deployments, use api_file_processing_callback queue
    return "api_file_processing_callback"


def _calculate_manual_review_decisions_for_batch_api(
    batch: list, manual_review_config: dict
) -> list[bool]:
    """Calculate manual review decisions for files in this API batch.

    Args:
        batch: List of (file_name, file_hash) tuples
        manual_review_config: Manual review configuration with percentage, etc.

    Returns:
        List of boolean decisions for each file in the batch
    """
    try:
        percentage = manual_review_config.get("review_percentage", 0)

        if percentage <= 0:
            return [False] * len(batch)

        # Calculate target count (at least 1 if percentage > 0)
        target_count = max(1, (len(batch) * percentage) // 100)

        if target_count >= len(batch):
            return [True] * len(batch)

        # Create deterministic selection based on file hashes
        import hashlib

        file_scores = []

        for i, (file_name, file_hash) in enumerate(batch):
            # For API batches, file_hash should be a dict with file info
            file_path = ""
            if isinstance(file_hash, dict):
                file_path = file_hash.get("file_path", "")

            # Use file name + path for consistent hashing
            hash_input = f"{file_name}:{file_path}"
            score = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
            file_scores.append((score, i))  # Store index instead of file object

        # Sort by score and select top N files
        file_scores.sort(key=lambda x: x[0])
        selected_indices = {item[1] for item in file_scores[:target_count]}

        # Create boolean list for this batch
        decisions = [i in selected_indices for i in range(len(batch))]

        logger.info(
            f"API manual review batch calculation: {len(batch)} files, {percentage}% = {target_count} files, selected indices: {sorted(selected_indices)}"
        )

        return decisions

    except Exception as e:
        logger.error(f"Error calculating manual review decisions for API batch: {e}")
        return [False] * len(batch)


@app.task(bind=True)
@monitor_performance
@retry(max_attempts=3, base_delay=2.0)
def api_deployment_status_check(
    self, execution_id: str, organization_id: str
) -> dict[str, Any]:
    """Check status of API deployment execution.

    Args:
        execution_id: Execution ID to check
        organization_id: Organization context

    Returns:
        Status information
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id, execution_id=execution_id, organization_id=organization_id
    ):
        logger.info(f"Checking status for API deployment execution {execution_id}")

        try:
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(organization_id)

                # Get execution status
                execution_response = api_client.get_workflow_execution(execution_id)
                if not execution_response.success:
                    raise Exception(
                        f"Failed to get execution context: {execution_response.error}"
                    )
                execution_context = execution_response.data
                execution_data = execution_context.get("execution", {})

                status_info = {
                    "execution_id": execution_id,
                    "status": execution_data.get("status"),
                    "created_at": execution_data.get("created_at"),
                    "modified_at": execution_data.get("modified_at"),
                    "total_files": execution_data.get("total_files"),
                    "attempts": execution_data.get("attempts"),
                    "execution_time": execution_data.get("execution_time"),
                    "error_message": execution_data.get("error_message"),
                    "is_api_deployment": True,
                }

                logger.info(
                    f"API deployment execution {execution_id} status: {status_info['status']}"
                )

                return status_info

        except Exception as e:
            logger.error(f"Failed to check API deployment status: {e}")
            raise


@app.task(bind=True)
@monitor_performance
def api_deployment_cleanup(
    self, execution_id: str, organization_id: str
) -> dict[str, Any]:
    """Cleanup resources after API deployment execution.

    Args:
        execution_id: Execution ID
        organization_id: Organization context

    Returns:
        Cleanup result
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id, execution_id=execution_id, organization_id=organization_id
    ):
        logger.info(f"Starting cleanup for API deployment execution {execution_id}")

        try:
            # Cleanup logic would go here
            # - Remove temporary files
            # - Clean up API deployment resources
            # - Archive execution data if needed

            cleanup_result = {
                "execution_id": execution_id,
                "cleanup_completed": True,
                "cleanup_time": time.time(),
                "task_id": task_id,
            }

            logger.info(f"Cleanup completed for API deployment execution {execution_id}")

            return cleanup_result

        except Exception as e:
            logger.error(
                f"Cleanup failed for API deployment execution {execution_id}: {e}"
            )
            raise


def _check_file_history_api(
    api_client: InternalAPIClient,
    workflow_id: str,
    hash_values_of_files: dict[str, FileHashData],  # Already converted from dicts
    execution_id: str,
) -> tuple[dict[str, FileHashData], dict[str, dict]]:
    """Check file history for API deployment and return both files to process and cached results.

    This implements the same logic as backend's _check_processing_history method.
    When use_file_history=True:
    - Files with existing successful results are returned as cached results
    - Files without history are returned for processing

    Args:
        api_client: Internal API client
        workflow_id: Workflow ID
        hash_values_of_files: Dictionary of files to check
        execution_id: Execution ID for logging

    Returns:
        Tuple of:
        - Dictionary of files that need to be processed (excludes already completed)
        - Dictionary of cached results from file history (file_hash -> result details)
    """
    try:
        # Extract file hashes for batch check
        file_hashes = []
        hash_to_file = {}

        for file_key, file_hash_data in hash_values_of_files.items():
            # Handle both FileHashData objects and dict formats
            if isinstance(file_hash_data, FileHashData):
                file_hash = file_hash_data.file_hash
            elif isinstance(file_hash_data, dict):
                file_hash = file_hash_data.get("file_hash")
            else:
                logger.warning(f"Unexpected file data type: {type(file_hash_data)}")
                continue

            if file_hash:
                file_hashes.append(file_hash)
                hash_to_file[file_hash] = (file_key, file_hash_data)

        if not file_hashes:
            logger.info(
                f"No file hashes available for history check in execution {execution_id}, processing all files"
            )
            return hash_values_of_files

        logger.info(
            f"Checking file history for {len(file_hashes)} files in execution {execution_id}"
        )

        # Check which files were already processed successfully
        response = api_client.check_file_history_batch(
            workflow_id=workflow_id,
            file_hashes=file_hashes,
            organization_id=None,  # Will use the organization from api_client context
        )

        processed_hashes = set(response.get("processed_file_hashes", []))
        file_history_details = response.get("file_history_details", {})
        logger.info(
            f"File history check found {len(processed_hashes)} already processed files"
        )

        # Separate files into: to process vs cached results
        files_to_process = {}
        cached_results = {}
        skipped_files = []

        for file_hash_str in file_hashes:
            file_key, file_hash_data = hash_to_file[file_hash_str]

            if file_hash_str in processed_hashes:
                # Get file name for logging
                if isinstance(file_hash_data, FileHashData):
                    file_name = file_hash_data.file_name
                elif isinstance(file_hash_data, dict):
                    file_name = file_hash_data.get("file_name", file_key)
                else:
                    file_name = file_key

                # Store cached result details
                if file_hash_str in file_history_details:
                    cached_results[file_hash_str] = {
                        "file_name": file_name,
                        "file_key": file_key,
                        "file_hash_data": file_hash_data,
                        **file_history_details[file_hash_str],  # result, metadata, etc.
                    }

                skipped_files.append(file_name)
                logger.info(
                    f"Using cached result for file: {file_name} (hash: {file_hash_str[:16]}...)"
                )
            else:
                files_to_process[file_key] = file_hash_data

        # Add files without hashes (will be processed normally)
        for file_key, file_hash_data in hash_values_of_files.items():
            if isinstance(file_hash_data, FileHashData):
                has_hash = bool(file_hash_data.file_hash)
            elif isinstance(file_hash_data, dict):
                has_hash = bool(file_hash_data.get("file_hash"))
            else:
                has_hash = False

            if not has_hash and file_key not in files_to_process:
                files_to_process[file_key] = file_hash_data

        logger.info(
            f"File history check completed for execution {execution_id}: {len(cached_results)} cached results, processing {len(files_to_process)} files"
        )

        return files_to_process, cached_results

    except Exception as e:
        logger.warning(
            f"File history check failed for execution {execution_id}, processing all files: {e}"
        )
        return hash_values_of_files, {}
