"""General Worker Tasks

Lightweight implementations of general tasks including webhook notifications
and general workflow executions using internal APIs.
"""

import time
from typing import Any

# Removed requests import - no longer needed after removing webhook tasks
# Import shared worker infrastructure
from shared.api_client import InternalAPIClient
from shared.logging_utils import WorkerLogger, log_context, monitor_performance
from shared.retry_utils import circuit_breaker
from shared.source_connector import WorkerSourceConnector
from shared.type_utils import FileDataValidator, TypeConverter
from shared.workflow_execution_service import WorkerWorkflowExecutionService

# Import shared data models for type safety
from unstract.core.data_models import (
    ExecutionStatus,
    FileBatchData,
    FileHash,
    FileHashData,
    WorkerFileData,
)

# Import common workflow utilities
from unstract.core.workflow_utils import PipelineTypeResolver, WorkflowTypeDetector

# Import from local worker module (avoid circular import)
from .worker import app, config

logger = WorkerLogger.get_logger(__name__)


# Webhook tasks removed - they should only be handled by the notification worker


@app.task(
    bind=True,
    name="async_execute_bin_general",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=60.0)
def async_execute_bin_general(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, FileHash],
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    log_events_id: str | None = None,
    use_file_history: bool = False,
    llm_profile_id: str | None = None,
    hitl_queue_name: str | None = None,
) -> dict[str, Any]:
    """Lightweight general workflow execution task.

    This handles general (non-API deployment) workflow executions,
    using internal APIs instead of direct Django ORM access.

    Args:
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        hash_values_of_files: File hash data
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        pipeline_id: Pipeline ID (None for general workflows)
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
        logger.info(
            f"Starting general workflow execution for workflow {workflow_id}, execution {execution_id}"
        )

        try:
            # Initialize API client with organization context
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Get workflow execution context
                execution_response = api_client.get_workflow_execution(execution_id)
                if not execution_response.success:
                    raise Exception(
                        f"Failed to get execution context: {execution_response.error}"
                    )
                execution_context = execution_response.data
                logger.info(f"Retrieved execution context for {execution_id}")

                # Update execution status to in progress
                api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status=ExecutionStatus.EXECUTING.value,
                    attempts=self.request.retries + 1,
                )

                # Process file batches if files provided
                file_batch_results = []
                if hash_values_of_files:
                    file_batch_results = _process_file_batches_general(
                        api_client, execution_id, hash_values_of_files, pipeline_id
                    )

                # Execute workflow-specific logic for general workflows
                execution_result = _execute_general_workflow(
                    api_client,
                    execution_context,
                    file_batch_results,
                    pipeline_id,
                    execution_mode,
                    use_file_history,
                    scheduled,
                )

                # Calculate execution time
                execution_time = execution_result.get("execution_time", 0)

                # Update execution status to completed
                # Only include total_files if we have files to avoid overwriting with 0
                update_params = {
                    "execution_id": execution_id,
                    "status": ExecutionStatus.COMPLETED.value,
                    "execution_time": execution_time,
                }
                if hash_values_of_files:
                    update_params["total_files"] = len(hash_values_of_files)

                api_client.update_workflow_execution_status(**update_params)

                logger.info(
                    f"Successfully completed general workflow execution {execution_id}"
                )

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                    "execution_time": execution_time,
                    "files_processed": len(hash_values_of_files)
                    if hash_values_of_files
                    else 0,
                    "file_batch_results": file_batch_results,
                    "execution_result": execution_result,
                    "is_general_workflow": True,
                }

        except Exception as e:
            logger.error(f"General workflow execution failed for {execution_id}: {e}")

            # Try to update execution status to failed
            try:
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            # Re-raise for Celery retry mechanism
            raise


def _process_file_batches_general(
    api_client: InternalAPIClient,
    execution_id: str,
    hash_values_of_files: dict[str, FileHash],
    pipeline_id: str | None = None,
) -> list:
    """Process file batches for general workflow execution.

    Args:
        api_client: Internal API client
        execution_id: Execution ID
        hash_values_of_files: File hash data
        pipeline_id: Pipeline ID (may be None for general workflows)

    Returns:
        List of file batch results
    """
    logger.info(
        f"Processing {len(hash_values_of_files)} files for general execution {execution_id}"
    )

    try:
        # Convert FileHash objects to file data format expected by API
        files_data = []
        for file_key, file_hash_data in hash_values_of_files.items():
            # TRACE: Log incoming file data
            logger.info(f"Processing FileHash for file '{file_key}'")
            logger.info(f"  FileHash: {file_hash_data}")

            # Validate that we have a FileHash object
            if not isinstance(file_hash_data, FileHash):
                logger.error(
                    f"Expected FileHash object for '{file_key}', got {type(file_hash_data)}"
                )
                # Try to convert from dict if possible
                if isinstance(file_hash_data, dict):
                    try:
                        file_hash_data = FileHashData.from_dict(file_hash_data)
                        logger.info(
                            f"Successfully converted dict to FileHashData for '{file_key}'"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to convert dict to FileHash for '{file_key}': {e}"
                        )
                        continue
                else:
                    logger.error(f"Cannot process file '{file_key}' - invalid data type")
                    continue

            # Use FileHash to_dict method for consistent data structure
            file_data = file_hash_data.to_dict()

            # TRACE: Log final file data
            logger.info(
                f"  Final file_data for '{file_key}': provider_file_uuid='{file_data.get('provider_file_uuid')}'"
            )
            files_data.append(file_data)

        # VALIDATION: Check file data integrity before API call
        _validate_provider_file_uuid_integrity(files_data, "process_file_batches_general")

        # Create file batch via internal API
        batch_response = api_client.create_file_batch(
            workflow_execution_id=execution_id,
            files=files_data,
            is_api=False,  # This is for general workflows, not API deployments
        )

        logger.info(
            f"Created file batch {batch_response.get('batch_id')} with {batch_response.get('total_files')} files"
        )

        return [batch_response]

    except Exception as e:
        logger.error(f"Failed to process file batches: {e}")
        raise


def _execute_general_workflow(
    api_client: InternalAPIClient,
    execution_context: dict[str, Any],
    file_batch_results: list,
    pipeline_id: str | None,
    execution_mode: tuple | None,
    use_file_history: bool,
    scheduled: bool,
) -> dict[str, Any]:
    """Execute general workflow specific logic for ETL/TASK workflows.

    This implements real workflow execution using source/destination connectors
    and file processing orchestration, similar to the API worker but for
    FILESYSTEM-based workflows.

    Args:
        api_client: Internal API client
        execution_context: Execution context from API
        file_batch_results: File batch processing results (unused - we create our own)
        pipeline_id: Pipeline ID (may be None)
        execution_mode: Execution mode
        use_file_history: Whether to use file history
        scheduled: Whether execution is scheduled

    Returns:
        Execution result
    """
    start_time = time.time()

    logger.info("Executing general workflow logic for ETL/TASK workflow")

    try:
        execution_data = execution_context.get("execution", {})
        workflow_definition = execution_context.get("workflow_definition", {})

        execution_id = execution_data.get("id")
        workflow_id = execution_data.get("workflow_id") or workflow_definition.get(
            "workflow_id"
        )
        organization_id = (
            execution_data.get("organization_id")
            or execution_context.get("organization_id")
            or execution_context.get("organization_context", {}).get("organization_id")
        )

        logger.info(
            f"Starting real workflow execution for workflow {workflow_id}, execution {execution_id}, organization_id={organization_id}"
        )

        # Get workflow endpoints to determine connection type
        workflow_endpoints = api_client.get_workflow_endpoints(workflow_id)
        has_api_endpoints = workflow_endpoints.get("has_api_endpoints", False)

        if has_api_endpoints:
            logger.warning(
                f"Workflow {workflow_id} has API endpoints but routed to general worker - this should use API worker"
            )

        # For ETL/TASK workflows, we need to:
        # 1. Get source files from the source connector
        # 2. Create file batches for processing
        # 3. Orchestrate file processing through file_processing workers
        # 4. Aggregate results through callback workers

        # Initialize workflow execution service with migrated business logic
        workflow_service = WorkerWorkflowExecutionService(
            api_client=api_client,
            workflow_id=workflow_id,
            organization_id=api_client.organization_id,  # Use api_client's organization_id (already formatted)
            pipeline_id=pipeline_id,
            single_step=False,  # General workflows are complete execution
            scheduled=scheduled,
            execution_id=execution_id,
            use_file_history=use_file_history,
        )

        # Create or get workflow execution
        if not execution_id:
            execution_id = workflow_service.create_workflow_execution()
            logger.info(f"Created new workflow execution: {execution_id}")

        # Compile workflow
        compilation_success = workflow_service.compile_workflow()
        if not compilation_success:
            logger.error("Workflow compilation failed")
            workflow_service.update_execution_status(
                status=ExecutionStatus.ERROR,
                error="Workflow compilation failed",
            )
            return

        # Get source files using backend-compatible operations
        source_connector = WorkerSourceConnector(
            api_client=api_client,
            workflow_id=workflow_id,
            execution_id=execution_id,
            organization_id=api_client.organization_id,  # Use api_client's organization_id (already formatted)
            use_file_history=use_file_history,
        )

        # List files from source
        source_files, total_files = source_connector.list_files_from_source()

        # Get connection type from endpoint config
        connection_type = source_connector.endpoint_config.get(
            "connection_type", "FILESYSTEM"
        )
        is_api = connection_type == "API"

        logger.info(
            f"Listed {total_files} files from {connection_type} source (API: {is_api}, file_history: {use_file_history})"
        )

        # Update total_files immediately so UI can show proper progress (fixes race condition)
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.EXECUTING.value,
            total_files=total_files,
        )

        logger.info(f"Retrieved {total_files} source files for processing")

        if not source_files:
            logger.info(f"Execution {execution_id} no files to process")
            # Complete immediately with no files using workflow service
            workflow_service.update_execution_status(
                status=ExecutionStatus.COMPLETED,
                completed_files=0,
                failed_files=0,
            )

            # Update pipeline status if needed
            if pipeline_id:
                try:
                    api_client.update_pipeline_status(
                        pipeline_id=pipeline_id,
                        execution_id=execution_id,
                        status=ExecutionStatus.COMPLETED.value,
                    )
                except Exception as pipeline_error:
                    logger.warning(f"Failed to update pipeline status: {pipeline_error}")

            execution_time = time.time() - start_time
            return {
                "status": "completed",
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "execution_time": execution_time,
                "files_processed": 0,
                "message": "No files to process",
                "is_general_workflow": True,
            }

        # Orchestrate file processing using chord pattern
        try:
            # Use orchestration method that creates chord and returns immediately
            orchestration_result = _orchestrate_file_processing_general(
                api_client=api_client,
                workflow_id=workflow_id,
                execution_id=execution_id,
                source_files=source_files,
                pipeline_id=pipeline_id,
                scheduled=scheduled,
                execution_mode=execution_mode,
                use_file_history=use_file_history,
                organization_id=api_client.organization_id,  # Use api_client's organization_id (already formatted)
            )

            # The orchestration result contains the chord_id and batch information
            # Pipeline status will be updated by the callback worker
            logger.info(
                f"General workflow orchestration completed in {time.time() - start_time:.2f}s"
            )

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            workflow_service.update_execution_status(
                status=ExecutionStatus.ERROR,
                error=str(e),
            )

            orchestration_result = {
                "status": "error",
                "success": False,
                "error": str(e),
            }

        execution_time = time.time() - start_time
        orchestration_result["execution_time"] = execution_time
        orchestration_result["is_general_workflow"] = True

        logger.info(f"General workflow orchestration completed in {execution_time:.2f}s")

        return orchestration_result

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"General workflow failed after {execution_time:.2f}s: {e}")
        raise


def _orchestrate_file_processing_general(
    api_client: InternalAPIClient,
    workflow_id: str,
    execution_id: str,
    source_files: dict[str, FileHash],
    pipeline_id: str | None,
    scheduled: bool,
    execution_mode: tuple | None,
    use_file_history: bool,
    organization_id: str,
) -> dict[str, Any]:
    """Orchestrate file processing for general workflows using the same pattern as API worker.

    This creates file batches and sends them to file_processing workers using chord/callback.

    Args:
        api_client: Internal API client
        workflow_id: Workflow ID
        execution_id: Execution ID
        source_files: Dictionary of source files to process
        pipeline_id: Pipeline ID
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        use_file_history: Whether to use file history
        organization_id: Organization ID for callback context

    Returns:
        Orchestration result
    """
    logger.info(
        f"Orchestrating file processing for {len(source_files)} files with organization_id={organization_id}"
    )

    try:
        # Get file batches using the same logic as Django backend
        batches = _get_file_batches_general(source_files)
        logger.info(f"Created {len(batches)} file batches for processing")

        # Create batch tasks following the exact Django pattern
        batch_tasks = []
        execution_mode_str = (
            (
                execution_mode[1]
                if isinstance(execution_mode, tuple)
                else str(execution_mode)
            )
            if execution_mode
            else None
        )

        print(f"Execution mode: {execution_mode_str}")
        print(f"Pipeline ID: {pipeline_id}")
        print(f"Scheduled: {scheduled}")
        print(f"Execution mode: {execution_mode_str}")
        print(f"Use file history: {use_file_history}")
        print(f"Batches -------------------->>>: {batches}")

        # Calculate manual review configuration ONCE for all files before batching
        from shared.manual_review_factory import get_manual_review_service

        manual_review_service = get_manual_review_service(
            api_client, api_client.organization_id
        )
        global_file_data = (
            manual_review_service.create_workflow_file_data_with_manual_review(
                workflow_id=workflow_id,
                execution_id=execution_id,
                organization_id=api_client.organization_id,
                pipeline_id=pipeline_id,
                scheduled=scheduled,
                execution_mode=execution_mode_str,
                use_file_history=use_file_history,
                total_files=len(source_files),
            )
        )
        print(f"Global file data: {global_file_data}")
        # Pre-calculate file decisions for ALL files based on total count - not per batch!
        q_file_no_list = global_file_data.manual_review_config.get("q_file_no_list", [])
        logger.info(
            f"Pre-calculated manual review selection: {len(q_file_no_list)} files selected from {len(source_files)} total files for manual review"
        )

        for batch_idx, batch in enumerate(batches):
            # Create file data using the pre-calculated global configuration
            file_data = (
                manual_review_service.create_workflow_file_data_with_manual_review(
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    organization_id=api_client.organization_id,
                    pipeline_id=pipeline_id,
                    scheduled=scheduled,
                    execution_mode=execution_mode_str,
                    use_file_history=use_file_history,
                    total_files=len(source_files),
                )
            )

            # Calculate batch-specific decisions based on the global q_file_no_list
            file_decisions = []
            for file_name, file_hash in batch:
                file_number = file_hash.get("file_number", 0)
                is_selected = file_number in q_file_no_list
                file_decisions.append(is_selected)

            # Update the file_data with batch-specific decisions
            file_data.manual_review_config["file_decisions"] = file_decisions
            logger.info(
                f"Calculated manual review decisions for batch {batch_idx + 1}: {sum(file_decisions)}/{len(file_decisions)} files selected"
            )

            # Create batch data exactly matching Django FileBatchData structure
            batch_data = _create_batch_data_general(
                files=batch, file_data=file_data, source_files=source_files
            )

            print(
                f"Batch {batch_idx + 1} contains {len(batch)} files (BEFORE enhancement): {batch_data}"
            )

            # Debug: Log the files in this batch BEFORE enhancement
            logger.info(
                f"Batch {batch_idx + 1} contains {len(batch)} files (BEFORE enhancement):"
            )
            for file_name, file_hash in batch:
                provider_uuid = (
                    file_hash.get("provider_file_uuid")
                    if isinstance(file_hash, dict)
                    else "N/A"
                )
                logger.info(f"  📄 {file_name}: provider_file_uuid='{provider_uuid}'")

            # Debug: Log the files in this batch AFTER enhancement
            logger.info(f"Batch {batch_idx + 1} files AFTER enhancement:")
            for file_name, file_hash in batch_data.files:
                provider_uuid = (
                    file_hash.get("provider_file_uuid")
                    if isinstance(file_hash, dict)
                    else "N/A"
                )
                logger.info(f"  📄 {file_name}: provider_file_uuid='{provider_uuid}'")

            # VALIDATION: Check batch data integrity using dataclass
            _validate_batch_data_integrity_dataclass(batch_data, batch_idx + 1)

            # Determine queue using FILESYSTEM logic (not API)
            file_processing_queue = _get_queue_name_general()

            # Create task signature matching Django backend pattern
            batch_tasks.append(
                app.signature(
                    "process_file_batch",  # Use same task name as Django
                    args=[
                        batch_data.to_dict()
                    ],  # Convert FileBatchData to dict for Celery serialization
                    queue=file_processing_queue,
                )
            )

        # Create callback queue using FILESYSTEM logic
        file_processing_callback_queue = _get_callback_queue_name_general()

        # Execute chord exactly matching Django pattern
        from celery import chord

        logger.info(
            f"DEBUG: Creating callback kwargs with organization_id={organization_id}"
        )
        callback_kwargs = {
            "execution_id": str(execution_id),
            "organization_id": str(organization_id),
        }

        # CRITICAL FIX: Pass pipeline_id directly to callback to ensure pipeline status updates
        if pipeline_id:
            callback_kwargs["pipeline_id"] = str(pipeline_id)
            logger.info(
                f"Passing pipeline_id {pipeline_id} to callback for proper status updates"
            )

        # Create callback signature exactly matching the working API deployment pattern
        # Import to ensure we have the right app context
        from .worker import app as celery_app

        callback_signature = celery_app.signature(
            "process_batch_callback",
            kwargs=callback_kwargs,  # Pass execution_id and pipeline_id as kwargs
            queue=file_processing_callback_queue,
        )

        result = chord(batch_tasks)(callback_signature)

        if not result:
            exception = f"Failed to queue execution task {execution_id}"
            logger.error(exception)
            raise Exception(exception)

        logger.info(f"Execution {execution_id} file processing orchestrated successfully")

        return {
            "status": "orchestrated",
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "files_processed": len(source_files),
            "batches_created": len(batches),
            "chord_id": result.id,
            "message": "File processing orchestrated, waiting for completion",
        }

    except Exception as e:
        # Update execution to ERROR status matching Django pattern
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.ERROR.value,
            error_message=f"Error while processing files: {str(e)}",
        )
        logger.error(
            f"File processing orchestration failed for {execution_id}: {str(e)}",
            exc_info=True,
        )
        raise


def _get_file_batches_general(input_files: dict[str, FileHash] | list[dict]) -> list:
    """Get file batches using the exact same logic as Django backend.

    This matches WorkflowHelper.get_file_batches() exactly.

    Args:
        input_files: Dictionary of file hash data or list of file dictionaries (for backward compatibility)

    Returns:
        List of file batches
    """
    import math
    import os

    # Use type converter to ensure consistent format
    try:
        standardized_files = TypeConverter.ensure_file_dict_format(input_files)
        logger.info(
            f"Successfully standardized {len(standardized_files)} files to dict format"
        )
    except Exception as e:
        logger.error(f"Failed to standardize input files: {e}")
        raise TypeError(f"Could not convert input files to standard format: {e}")

    # Validate file batch format
    is_valid, errors = FileDataValidator.validate_file_batch_data(standardized_files)
    if not is_valid:
        logger.error(f"File batch validation failed: {errors}")
        # Continue processing but log warnings
        for error in errors:
            logger.warning(f"Validation error: {error}")

    # Convert FileHash objects to serializable format for batching
    json_serializable_files = {}
    for file_name, file_hash_data in standardized_files.items():
        try:
            json_serializable_files[file_name] = file_hash_data.to_dict()
        except Exception as e:
            logger.error(f"Failed to serialize file '{file_name}': {e}")
            continue

    # Prepare batches of files for parallel processing (exact Django logic)
    BATCH_SIZE = int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "1"))  # Default from Django
    file_items = list(json_serializable_files.items())

    # Calculate how many items per batch (exact Django logic)
    num_files = len(file_items)
    if num_files == 0:
        return []  # No files to batch

    num_batches = min(BATCH_SIZE, num_files)
    items_per_batch = math.ceil(num_files / num_batches)

    # Split into batches (exact Django logic)
    batches = []
    for start_index in range(0, len(file_items), items_per_batch):
        end_index = start_index + items_per_batch
        batch = file_items[start_index:end_index]
        batches.append(batch)

    return batches


# Manual review logic moved to plugins/manual_review/workflow_service.py


# This function has been moved to plugins/manual_review/workflow_service.py


# This function has been moved to plugins/manual_review/workflow_service.py


def _create_batch_data_general(
    files: list, file_data: WorkerFileData, source_files: dict[str, FileHash] = None
) -> FileBatchData:
    """Create batch data matching Django FileBatchData structure exactly.

    Args:
        files: List of (file_name, file_hash) tuples
        file_data: File data dictionary
        source_files: Source files data containing connector metadata

    Returns:
        Batch data dictionary matching Django FileBatchData
    """
    # Create enhanced files list with proper metadata handling
    enhanced_files = []

    # Extract manual review decisions from file_data
    manual_review_decisions = file_data.manual_review_config.get("file_decisions", [])
    logger.info(
        f"BATCH_DATA: Applying manual review decisions: {manual_review_decisions}"
    )

    if source_files:
        for file_index, (file_name, file_hash) in enumerate(files):
            # DEBUG: Log file metadata mapping to detect collisions
            logger.info(f"BATCH_DATA: Processing file '{file_name}' in batch creation")
            logger.info(
                f"  Original file_hash keys: {list(file_hash.keys()) if isinstance(file_hash, dict) else 'not a dict'}"
            )
            if isinstance(file_hash, dict):
                logger.info(
                    f"  Original provider_file_uuid: '{file_hash.get('provider_file_uuid')}' (type: {type(file_hash.get('provider_file_uuid'))})"
                )
                logger.info(f"  Original file_path: '{file_hash.get('file_path')}'")

            # Get source file data to extract connector metadata
            source_file_data = source_files.get(file_name)

            # DEBUG: Log source file data lookup
            if source_file_data:
                if isinstance(source_file_data, FileHash):
                    logger.info(
                        f"  Found FileHash for '{file_name}': provider_file_uuid='{source_file_data.provider_file_uuid}'"
                    )
                    source_dict = source_file_data.to_dict()
                elif isinstance(source_file_data, dict):
                    logger.info(
                        f"  Found dict source file data for '{file_name}': {list(source_file_data.keys())}"
                    )
                    source_dict = source_file_data
                else:
                    logger.warning(
                        f"  Unexpected source file data type for '{file_name}': {type(source_file_data)}"
                    )
                    source_dict = {}
            else:
                logger.warning(
                    f"  No source file data found for '{file_name}' in source_files with keys: {list(source_files.keys())}"
                )
                source_dict = {}

            # CRITICAL FIX: Create deep copy and update with correct source file metadata
            import copy

            enhanced_file_hash = (
                copy.deepcopy(file_hash) if isinstance(file_hash, dict) else {}
            )

            # TRACE: Before updating from source_files
            logger.info(
                f"  Enhanced file_hash BEFORE update: provider_file_uuid='{enhanced_file_hash.get('provider_file_uuid')}'"
            )

            # Update core metadata from source_files to ensure each file gets correct data
            if source_dict and isinstance(enhanced_file_hash, dict):
                # CRITICAL: Handle provider_file_uuid correctly - prefer source_files but don't overwrite with None
                original_uuid = enhanced_file_hash.get("provider_file_uuid")
                source_uuid = source_dict.get("provider_file_uuid")

                if source_uuid is not None:
                    # Source has a provider_file_uuid, use it
                    enhanced_file_hash["provider_file_uuid"] = source_uuid
                    logger.info(
                        f"  Updated provider_file_uuid: '{original_uuid}' -> '{source_uuid}' (from source_files)"
                    )
                elif original_uuid is not None:
                    # Keep original provider_file_uuid if source doesn't have one
                    logger.info(
                        f"  Keeping original provider_file_uuid: '{original_uuid}' (source_files has None)"
                    )
                else:
                    # Neither source nor original has provider_file_uuid
                    logger.warning(
                        f"  No provider_file_uuid in source_files or original file_hash for '{file_name}'"
                    )

                # Update file_path (always update if available)
                if "file_path" in source_dict:
                    enhanced_file_hash["file_path"] = source_dict["file_path"]
                    logger.info(f"  Updated file_path: '{source_dict['file_path']}'")

                # Update additional metadata if available (but don't overwrite with None/empty)
                for field in ["file_size", "mime_type", "file_hash", "fs_metadata"]:
                    if field in source_dict and source_dict[field] is not None:
                        # Only update if source has a non-None value
                        enhanced_file_hash[field] = source_dict[field]
                        logger.info(f"  Updated {field}: '{source_dict[field]}'")

                # Add connector metadata if available
                connector_metadata = source_dict.get("connector_metadata")
                connector_id = source_dict.get("connector_id")
                if connector_metadata and connector_id:
                    enhanced_file_hash["connector_metadata"] = connector_metadata
                    enhanced_file_hash["connector_id"] = connector_id
                    logger.info("  Added connector_metadata and connector_id")
            else:
                logger.warning(
                    f"  No source file data or enhanced_file_hash is not dict for '{file_name}'"
                )

            # CRITICAL FIX: Apply manual review decision to this file using GLOBAL file number
            # Use the original file_number from the file hash, not the batch-local file_index
            original_file_number = enhanced_file_hash.get(
                "file_number", file_index + 1
            )  # fallback to batch index + 1
            global_q_file_no_list = file_data.manual_review_config.get(
                "q_file_no_list", []
            )

            is_manual_review_required = original_file_number in global_q_file_no_list

            # Set manual review fields in file hash
            enhanced_file_hash["is_manualreview_required"] = is_manual_review_required
            enhanced_file_hash["file_destination"] = (
                "MANUALREVIEW" if is_manual_review_required else "destination"
            )

            logger.info(
                f"  MANUAL REVIEW: File #{original_file_number} '{file_name}' (batch_index={file_index}) -> is_manualreview_required={is_manual_review_required}, global_q_file_no_list={global_q_file_no_list}"
            )

            # DEBUG: Show final file_hash state
            logger.info(f"  Final file_hash for '{file_name}':")
            logger.info(
                f"    provider_file_uuid: '{enhanced_file_hash.get('provider_file_uuid')}' (type: {type(enhanced_file_hash.get('provider_file_uuid'))})"
            )
            logger.info(f"    file_path: '{enhanced_file_hash.get('file_path')}'")
            logger.info(f"    file_name: '{enhanced_file_hash.get('file_name')}'")
            logger.info(
                f"    is_manualreview_required: '{enhanced_file_hash.get('is_manualreview_required')}'"
            )
            logger.info(
                f"    file_destination: '{enhanced_file_hash.get('file_destination')}'"
            )
            if enhanced_file_hash.get("connector_id"):
                logger.info(
                    f"    connector_id: '{enhanced_file_hash.get('connector_id')}'"
                )

            enhanced_files.append((file_name, enhanced_file_hash))
    else:
        # No source files, use original files but still apply manual review decisions
        for file_index, (file_name, file_hash) in enumerate(files):
            # Ensure file_hash is a dictionary we can modify
            if isinstance(file_hash, dict):
                enhanced_file_hash = file_hash.copy()
            else:
                enhanced_file_hash = {}

            # CRITICAL FIX: Apply manual review decision to this file using GLOBAL file number
            # Use the original file_number from the file hash, not the batch-local file_index
            original_file_number = enhanced_file_hash.get(
                "file_number", file_index + 1
            )  # fallback to batch index + 1
            global_q_file_no_list = file_data.manual_review_config.get(
                "q_file_no_list", []
            )

            is_manual_review_required = original_file_number in global_q_file_no_list

            # Set manual review fields in file hash
            enhanced_file_hash["is_manualreview_required"] = is_manual_review_required
            enhanced_file_hash["file_destination"] = (
                "MANUALREVIEW" if is_manual_review_required else "destination"
            )

            logger.info(
                f"  MANUAL REVIEW (no source): File #{original_file_number} '{file_name}' (batch_index={file_index}) -> is_manualreview_required={is_manual_review_required}, global_q_file_no_list={global_q_file_no_list}"
            )
            enhanced_files.append((file_name, enhanced_file_hash))

    # Create FileBatchData object
    return FileBatchData(files=enhanced_files, file_data=file_data)


def _get_queue_name_general() -> str:
    """Get the appropriate file processing queue for general (FILESYSTEM) workflows.

    For general workflows, we use the standard file_processing queue, not the API one.

    Returns:
        Queue name for file processing
    """
    # Use common utility for consistent queue naming
    file_queue, _ = WorkflowTypeDetector.get_queue_names(is_api_workflow=False)
    return file_queue


def _get_callback_queue_name_general() -> str:
    """Get the appropriate callback queue for general (FILESYSTEM) workflows.

    For general workflows, we use the standard callback queue, not the API one.

    Returns:
        Queue name for callback processing
    """
    # Use common utility for consistent queue naming
    _, callback_queue = WorkflowTypeDetector.get_queue_names(is_api_workflow=False)
    return callback_queue


def _validate_provider_file_uuid_integrity(files_data: list, operation_name: str) -> None:
    """Validate that provider_file_uuid values are preserved and not corrupted.

    Args:
        files_data: List of file data dictionaries
        operation_name: Name of the operation for logging
    """
    missing_uuid_count = 0
    empty_uuid_count = 0
    valid_uuid_count = 0

    for file_data in files_data:
        file_name = file_data.get("file_name", "unknown")
        provider_uuid = file_data.get("provider_file_uuid")

        if provider_uuid is None:
            missing_uuid_count += 1
            logger.warning(
                f"VALIDATION [{operation_name}]: File '{file_name}' has missing provider_file_uuid"
            )
        elif isinstance(provider_uuid, str) and not provider_uuid.strip():
            empty_uuid_count += 1
            logger.warning(
                f"VALIDATION [{operation_name}]: File '{file_name}' has empty provider_file_uuid"
            )
        else:
            valid_uuid_count += 1
            logger.debug(
                f"VALIDATION [{operation_name}]: File '{file_name}' has valid provider_file_uuid: '{provider_uuid}'"
            )

    total_files = len(files_data)
    logger.info(
        f"VALIDATION [{operation_name}]: {valid_uuid_count}/{total_files} files have valid provider_file_uuid"
    )

    if missing_uuid_count > 0 or empty_uuid_count > 0:
        logger.warning(
            f"VALIDATION [{operation_name}]: {missing_uuid_count} missing, {empty_uuid_count} empty provider_file_uuid values"
        )


def _validate_batch_data_integrity(batch_data: dict[str, Any], batch_idx: int) -> None:
    """Validate that batch data has proper provider_file_uuid values.

    Args:
        batch_data: Batch data dictionary
        batch_idx: Batch index for logging
    """
    files = batch_data.get("files", [])

    if not files:
        logger.warning(f"VALIDATION [Batch {batch_idx}]: No files in batch data")
        return

    missing_uuid_count = 0
    valid_uuid_count = 0

    for file_name, file_hash in files:
        provider_uuid = (
            file_hash.get("provider_file_uuid") if isinstance(file_hash, dict) else None
        )

        if provider_uuid is None or (
            isinstance(provider_uuid, str) and not provider_uuid.strip()
        ):
            missing_uuid_count += 1
            logger.warning(
                f"VALIDATION [Batch {batch_idx}]: File '{file_name}' missing/empty provider_file_uuid"
            )
        else:
            valid_uuid_count += 1

    total_files = len(files)
    logger.info(
        f"VALIDATION [Batch {batch_idx}]: {valid_uuid_count}/{total_files} files have valid provider_file_uuid"
    )

    if missing_uuid_count > 0:
        logger.error(
            f"VALIDATION [Batch {batch_idx}]: {missing_uuid_count} files missing provider_file_uuid - this may cause FileHistory issues"
        )


def _validate_batch_data_integrity_dataclass(
    batch_data: FileBatchData, batch_idx: int
) -> None:
    """Validate that FileBatchData has proper provider_file_uuid values.

    Args:
        batch_data: FileBatchData object
        batch_idx: Batch index for logging
    """
    files = batch_data.files

    if not files:
        logger.warning(f"VALIDATION [Batch {batch_idx}]: No files in FileBatchData")
        return

    missing_uuid_count = 0
    valid_uuid_count = 0

    for file_name, file_hash in files:
        provider_uuid = (
            file_hash.get("provider_file_uuid") if isinstance(file_hash, dict) else None
        )

        if provider_uuid is None or (
            isinstance(provider_uuid, str) and not provider_uuid.strip()
        ):
            missing_uuid_count += 1
            logger.warning(
                f"VALIDATION [Batch {batch_idx}]: File '{file_name}' missing/empty provider_file_uuid"
            )
        else:
            valid_uuid_count += 1

    total_files = len(files)
    logger.info(
        f"VALIDATION [Batch {batch_idx}]: {valid_uuid_count}/{total_files} files have valid provider_file_uuid"
    )

    if missing_uuid_count > 0:
        logger.error(
            f"VALIDATION [Batch {batch_idx}]: {missing_uuid_count} files missing provider_file_uuid - this may cause FileHistory issues"
        )


@app.task(
    bind=True,
    name="async_execute_bin",
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
    hash_values_of_files: dict[str, Any],
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    use_file_history: bool = True,
    **kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Router task that determines workflow type and executes appropriately.

    This task is called by the Django backend and routes to the appropriate
    execution handler based on workflow type detection.

    Args:
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        hash_values_of_files: File hash data
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        pipeline_id: Pipeline ID
        use_file_history: Whether to use file history

    Returns:
        Execution result
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
            f"Router task async_execute_bin received for execution {execution_id}"
        )

        try:
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Use common resolver to determine routing
                resolver = PipelineTypeResolver(api_client)
                should_use_api, routing_info = resolver.should_route_to_api_worker(
                    pipeline_id, workflow_id
                )

                logger.info(
                    f"Routing decision: {routing_info['routing_reason']} "
                    f"(use_api: {should_use_api})"
                )

                if should_use_api:
                    # API workflows should be handled by the dedicated API deployment worker
                    logger.warning(
                        f"API workflow {workflow_id} routed to general worker - should use API deployment worker"
                    )
                    # For now, reject API tasks from general worker to prevent conflicts
                    raise Exception(
                        f"API workflow {workflow_id} should be handled by API deployment worker, not general worker"
                    )
                else:
                    # Route to general workflow handler
                    return async_execute_bin_general(
                        schema_name=schema_name,
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        hash_values_of_files=hash_values_of_files,
                        scheduled=scheduled,
                        execution_mode=execution_mode,
                        pipeline_id=pipeline_id,
                        use_file_history=use_file_history,
                        **kwargs,
                    )

        except Exception as e:
            logger.error(f"Router task failed for execution {execution_id}: {e}")

            # Try to update execution status to failed
            try:
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            raise


# All webhook tasks removed - they should only be handled by the notification worker


# Removed async_execute_bin_api task - it should only be handled by the API deployment worker
# This prevents task routing conflicts and ensures proper separation of concerns
