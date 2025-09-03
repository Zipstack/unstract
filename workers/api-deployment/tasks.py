"""API Deployment Worker Tasks

Exact implementation matching Django backend patterns for API deployment tasks.
Uses the same patterns as workflow_helper.py and file_execution_tasks.py
"""

import time
from typing import Any

# Import shared worker infrastructure using new structure
from shared.api import InternalAPIClient

# Import from shared worker modules
from shared.enums.task_enums import TaskName
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import (
    WorkerLogger,
    monitor_performance,
    with_execution_context,
)
from shared.infrastructure.logging.helpers import log_file_info
from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger
from shared.patterns.retry.utils import retry
from shared.processing.files import FileProcessingUtils

# Import new shared utilities
from shared.workflow.execution import WorkerExecutionContext, WorkflowOrchestrationUtils

# Import from local worker module (avoid circular import)
from worker import app

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus, FileHashData

# Note: FileExecutionResult removed - file worker now handles all result caching

logger = WorkerLogger.get_logger(__name__)


def _log_api_statistics_to_ui(
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None,
    message: str,
) -> None:
    """Helper method to log API deployment statistics to UI.

    Args:
        execution_id: Execution ID for workflow logger
        organization_id: Organization ID for workflow logger
        pipeline_id: Pipeline ID for workflow logger
        message: Message to log to UI
    """
    try:
        workflow_logger = WorkerWorkflowLogger.create_for_api_workflow(
            execution_id=execution_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
        )

        if workflow_logger:
            log_file_info(
                workflow_logger,
                None,  # Execution-level logging for API workflows
                message,
            )
    except Exception as log_error:
        logger.debug(f"Failed to log API statistics: {log_error}")


def _log_api_file_history_statistics(
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None,
    total_files: int,
    cached_count: int,
    use_file_history: bool,
) -> None:
    """Helper method to log file history statistics for API deployments.

    Args:
        execution_id: Execution ID for workflow logger
        organization_id: Organization ID for workflow logger
        pipeline_id: Pipeline ID for workflow logger
        total_files: Total number of files
        cached_count: Number of cached files
        use_file_history: Whether file history is enabled
    """
    if use_file_history and cached_count > 0:
        processing_count = total_files - cached_count
        _log_api_statistics_to_ui(
            execution_id=execution_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            message=f"📋 Processing {total_files} files: {cached_count} from cache, {processing_count} new files",
        )
    else:
        _log_api_statistics_to_ui(
            execution_id=execution_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            message=f"📋 Processing {total_files} files (file history disabled)",
        )


def _log_api_batch_creation_statistics(
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None,
    batches: list,
    total_files: int,
) -> None:
    """Helper method to log batch creation statistics for API deployments.

    Args:
        execution_id: Execution ID for workflow logger
        organization_id: Organization ID for workflow logger
        pipeline_id: Pipeline ID for workflow logger
        batches: List of file batches created
        total_files: Total number of files
    """
    batch_sizes = [len(batch) for batch in batches]
    avg_batch_size = sum(batch_sizes) / len(batch_sizes) if batch_sizes else 0

    _log_api_statistics_to_ui(
        execution_id=execution_id,
        organization_id=organization_id,
        pipeline_id=pipeline_id,
        message=f"📦 Created {len(batches)} API batches for {total_files} files (avg: {avg_batch_size:.1f} files/batch)",
    )

    if len(batches) > 1:
        _log_api_statistics_to_ui(
            execution_id=execution_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            message=f"📊 API batch sizes: {', '.join(map(str, batch_sizes))}",
        )


@with_execution_context
def _unified_api_execution(
    task_instance,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, dict | FileHashData],
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    log_events_id: str | None = None,
    use_file_history: bool = False,
    task_type: str = "api",
    **kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Unified API deployment execution logic.

    This consolidates the duplicate logic from async_execute_bin_api
    and async_execute_bin methods.

    Args:
        task_instance: The Celery task instance
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        hash_values_of_files: File hash data
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        pipeline_id: Pipeline ID (for API deployments)
        log_events_id: Log events ID
        use_file_history: Whether to use file history
        task_type: Type of task (api/legacy) for differentiation
        **kwargs: Additional keyword arguments

    Returns:
        Execution result dictionary
    """
    try:
        # Set up execution context using shared utilities
        organization_id = schema_name
        config, api_client = WorkerExecutionContext.setup_execution_context(
            organization_id, execution_id, workflow_id
        )

        # Log task start with standardized format
        WorkerExecutionContext.log_task_start(
            f"unified_api_execution_{task_type}",
            execution_id,
            workflow_id,
            {
                "pipeline_id": pipeline_id,
                "scheduled": scheduled,
                "use_file_history": use_file_history,
                "files_count": len(hash_values_of_files) if hash_values_of_files else 0,
            },
        )

        # Convert file hash data using standardized conversion
        converted_files = FileProcessingUtils.convert_file_hash_data(hash_values_of_files)

        if not converted_files:
            logger.warning("No valid files to process after conversion")
            return {
                "execution_id": execution_id,
                "status": "COMPLETED",
                "message": "No files to process",
                "files_processed": 0,
            }

        # Validate orchestration parameters
        WorkflowOrchestrationUtils.validate_orchestration_parameters(
            execution_id, workflow_id, organization_id, converted_files
        )

        # Create file batches using standardized algorithm with organization-specific config
        file_batches = FileProcessingUtils.create_file_batches(
            files=converted_files,
            organization_id=organization_id,
            api_client=api_client,
            batch_size_env_var="MAX_PARALLEL_FILE_BATCHES",
            # default_batch_size not needed - will use environment default
        )

        logger.info(
            f"Processing {len(converted_files)} files in {len(file_batches)} batches"
        )

        # Execute workflow through direct API orchestration
        result = _run_workflow_api(
            api_client=api_client,
            schema_name=organization_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            hash_values_of_files=converted_files,  # Changed parameter name
            scheduled=scheduled,
            execution_mode=execution_mode,
            pipeline_id=pipeline_id,
            use_file_history=use_file_history,
            task_id=task_instance.request.id,  # Add required task_id
        )

        # Log completion with standardized format
        WorkerExecutionContext.log_task_completion(
            f"unified_api_execution_{task_type}",
            execution_id,
            True,
            f"files_processed={len(converted_files)}",
        )

        # CRITICAL: Clean up StateStore to prevent data leaks between tasks
        try:
            from shared.infrastructure.context import StateStore

            StateStore.clear_all()
            logger.debug("🧹 Cleaned up StateStore context to prevent data leaks")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup StateStore context: {cleanup_error}")

        return result

    except Exception as e:
        logger.error(f"API execution failed: {e}")

        # Handle execution error with standardized pattern
        if "api_client" in locals():
            WorkerExecutionContext.handle_execution_error(
                api_client, execution_id, e, logger, f"api_execution_{task_type}"
            )

        # Log completion with error
        WorkerExecutionContext.log_task_completion(
            f"unified_api_execution_{task_type}",
            execution_id,
            False,
            f"error={str(e)}",
        )

        # CRITICAL: Clean up StateStore to prevent data leaks between tasks (error path)
        try:
            from shared.infrastructure.context import StateStore

            StateStore.clear_all()
            logger.debug(
                "🧹 Cleaned up StateStore context to prevent data leaks (error path)"
            )
        except Exception as cleanup_error:
            logger.warning(
                f"Failed to cleanup StateStore context on error: {cleanup_error}"
            )

        return {
            "execution_id": execution_id,
            "status": "ERROR",
            "error": str(e),
            "files_processed": 0,
        }


@app.task(
    bind=True,
    name=TaskName.ASYNC_EXECUTE_BIN_API,
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
    return _unified_api_execution(
        task_instance=self,
        schema_name=schema_name,
        workflow_id=workflow_id,
        execution_id=execution_id,
        hash_values_of_files=hash_values_of_files,
        scheduled=scheduled,
        execution_mode=execution_mode,
        pipeline_id=pipeline_id,
        log_events_id=log_events_id,
        use_file_history=use_file_history,
        task_type="api",
        **kwargs,
    )


@app.task(
    bind=True,
    name=TaskName.ASYNC_EXECUTE_BIN,
    autoretry_for=(Exception,),
    max_retries=0,  # Match Django backend pattern
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
    return _unified_api_execution(
        task_instance=self,
        schema_name=schema_name,
        workflow_id=workflow_id,
        execution_id=execution_id,
        hash_values_of_files=hash_values_of_files,
        scheduled=scheduled,
        execution_mode=execution_mode,
        pipeline_id=pipeline_id,
        log_events_id=log_events_id,
        use_file_history=use_file_history,
        task_type="api",
        **kwargs,
    )


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

    # Update total_files at workflow start
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

        # Mark cached files as executed and add their results to API cache
        if cached_results:
            logger.info(
                f"Marking {len(cached_results)} files as already executed (cached)"
            )
            logger.info(
                f"DEBUG: cached_results type: {type(cached_results)}, keys: {list(cached_results.keys()) if isinstance(cached_results, dict) else 'not a dict'}"
            )

            # CRITICAL FIX: Add cached file history results to API results cache
            # This ensures cached files appear in the final API response
            # NOTE: This fix is ONLY for API deployments, not for ETL/TASK workflows
            try:
                from shared.workflow.execution.service import (
                    WorkerWorkflowExecutionService,
                )

                # Create workflow service for caching (API deployment only)
                workflow_service = WorkerWorkflowExecutionService(api_client=api_client)

                for file_hash_str, cached_result in cached_results.items():
                    # Find the corresponding FileHashData object and mark it as executed
                    for hash_data in hash_values_of_files.values():
                        if hash_data.file_hash == file_hash_str:
                            hash_data.is_executed = True
                            logger.info(
                                f"Marked file {hash_data.file_name} as is_executed=True"
                            )

                            # Add cached result to API results cache for final response
                            # Parse cached result if it's a JSON string (from file_history storage)
                            cached_result_data = cached_result.get("result")
                            if isinstance(cached_result_data, str):
                                try:
                                    import json

                                    cached_result_data = json.loads(cached_result_data)
                                except (json.JSONDecodeError, TypeError) as e:
                                    logger.warning(
                                        f"Failed to parse cached result JSON for {hash_data.file_name}: {e}"
                                    )
                                    # Fallback: try to parse Python string representation (legacy format)
                                    try:
                                        import ast

                                        cached_result_data = ast.literal_eval(
                                            cached_result_data
                                        )
                                        logger.info(
                                            f"Successfully parsed legacy Python string format for {hash_data.file_name}"
                                        )
                                    except (ValueError, SyntaxError) as parse_error:
                                        logger.warning(
                                            f"Failed to parse legacy format for {hash_data.file_name}: {parse_error}"
                                        )
                                        # Keep as string if all parsing fails

                            api_result = {
                                "file": hash_data.file_name,
                                "file_execution_id": hash_data.provider_file_uuid or "",
                                "status": "Success",  # Cached results are always successful
                                "result": cached_result_data,
                                "error": None,
                                "metadata": {
                                    "processing_time": 0.0,  # Cached files take no time
                                    "source": "file_history_cache",
                                },
                            }

                            # Cache the result for API response aggregation
                            workflow_service.cache_api_result(
                                workflow_id=workflow_id,
                                execution_id=execution_id,
                                result=api_result,
                                is_api=True,
                            )
                            logger.info(
                                f"Added cached file history result to API results cache: {hash_data.file_name}"
                            )
                            break

            except Exception as cache_error:
                logger.error(
                    f"Failed to cache file history results for API response: {cache_error}"
                )
                # Continue execution - caching failures shouldn't stop the workflow

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

    # Log file history statistics to UI
    _log_api_file_history_statistics(
        execution_id=execution_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
        total_files=total_files,
        cached_count=cached_count,
        use_file_history=use_file_history,
    )

    # Get file batches using the exact same logic as Django backend with organization-specific config
    batches = _get_file_batches(
        input_files=files_to_send,
        organization_id=schema_name,  # schema_name is the organization_id
        api_client=api_client,
    )
    logger.info(
        f"Execution {execution_id} processing {total_files} files in {len(batches)} batches"
    )

    # Log batch creation statistics to UI
    _log_api_batch_creation_statistics(
        execution_id=execution_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
        batches=batches,
        total_files=total_files,
    )

    # Create batch tasks following the exact Django pattern
    batch_tasks = []
    execution_mode_str = (
        (execution_mode[1] if isinstance(execution_mode, tuple) else str(execution_mode))
        if execution_mode
        else None
    )

    for batch_index, batch in enumerate(batches):
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

        # Determine queue using the same logic as Django backend
        file_processing_queue = _get_queue_name_api()

        # Create batch data exactly matching Django FileBatchData structure
        batch_data = _create_batch_data(files=batch, file_data=file_data)

        # Create task signature matching Django backend pattern
        batch_tasks.append(
            app.signature(
                "process_file_batch",
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


def _get_file_batches(
    input_files: dict[str, FileHashData],
    organization_id: str | None = None,
    api_client=None,
) -> list:
    """Get file batches using the exact same logic as Django backend with organization-specific config.

    This matches WorkflowHelper.get_file_batches() exactly, but now supports organization-specific
    MAX_PARALLEL_FILE_BATCHES configuration.

    Args:
        input_files: Dictionary of FileHashData objects (already converted by FileProcessingUtils)
        organization_id: Organization ID for configuration lookup
        api_client: Internal API client for configuration access

    Returns:
        List of file batches

    Note:
        This function expects FileHashData objects since convert_file_hash_data() is called upstream.
        The function converts them to dict format for Celery serialization.
    """
    import math

    # Convert FileHashData objects to serializable format for batching
    # At this point, input_files should contain only FileHashData objects
    # (converted upstream by FileProcessingUtils.convert_file_hash_data)
    if not isinstance(input_files, dict):
        raise TypeError(f"Expected dict[str, FileHashData], got {type(input_files)}")

    json_serializable_files = {}
    for file_name, file_hash_data in input_files.items():
        if isinstance(file_hash_data, FileHashData):
            json_serializable_files[file_name] = file_hash_data.to_dict()
        else:
            # This should not happen if convert_file_hash_data was called upstream
            logger.error(
                f"Unexpected file data type for '{file_name}': {type(file_hash_data)}. "
                f"Expected FileHashData object. This suggests convert_file_hash_data() was not called upstream."
            )
            # Try to handle gracefully
            if isinstance(file_hash_data, dict):
                json_serializable_files[file_name] = file_hash_data
            else:
                continue

    # Prepare batches of files for parallel processing with organization-specific config
    from shared.infrastructure.config.client import get_batch_size_with_fallback

    BATCH_SIZE = get_batch_size_with_fallback(
        organization_id=organization_id,
        api_client=api_client,
        env_var_name="MAX_PARALLEL_FILE_BATCHES",
        # default_value not needed - will use environment default
    )
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
@with_execution_context
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

            # Set LOG_EVENTS_ID in StateStore for WebSocket messaging (critical for UI logs)
            # This enables the WorkerWorkflowLogger to send logs to the UI via WebSocket
            execution_data = execution_context.get("execution", {})
            execution_log_id = execution_data.get("execution_log_id")
            if execution_log_id:
                # Import and set LOG_EVENTS_ID like backend Celery workers do
                from shared.infrastructure.context import StateStore

                StateStore.set("LOG_EVENTS_ID", execution_log_id)
                logger.info(
                    f"Set LOG_EVENTS_ID for WebSocket messaging: {execution_log_id}"
                )
            else:
                logger.warning(
                    f"No execution_log_id found for execution {execution_id}, WebSocket logs may not be delivered"
                )

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
@with_execution_context
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
    logger.info(f"Starting cleanup for API deployment execution {execution_id}")

    try:
        # Cleanup logic would go here
        # - Remove temporary files
        # - Clean up API deployment resources
        # - Archive execution data if needed
        task_id = self.request.id

        cleanup_result = {
            "execution_id": execution_id,
            "cleanup_completed": True,
            "cleanup_time": time.time(),
            "task_id": task_id,
        }

        logger.info(f"Cleanup completed for API deployment execution {execution_id}")

        return cleanup_result

    except Exception as e:
        logger.error(f"Cleanup failed for API deployment execution {execution_id}: {e}")
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
