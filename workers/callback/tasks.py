"""File Processing Callback Worker Tasks

Handles workflow execution finalization and status updates when file processing completes.
Provides Redis-based caching, exponential backoff, and circuit breaker patterns for reliability.
"""

import time
from typing import Any

# Use Celery current_app to avoid circular imports
from celery import current_app as app

# Import shared worker infrastructure
from shared.api import InternalAPIClient

# Import from shared worker modules
from shared.enums import PipelineType
from shared.enums.status_enums import PipelineStatus
from shared.enums.task_enums import TaskName

# Import performance optimization utilities
from shared.infrastructure.caching.cache_utils import (
    get_cache_manager,
    initialize_cache_manager,
)
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import (
    WorkerLogger,
    log_context,
    monitor_performance,
)
from shared.patterns.notification.helper import handle_status_notifications
from shared.patterns.retry.backoff import (
    initialize_backoff_managers,
)
from shared.patterns.retry.utils import CircuitBreakerOpenError, circuit_breaker
from shared.processing.files.time_utils import (
    WallClockTimeCalculator,
    aggregate_file_batch_results,
)

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus

logger = WorkerLogger.get_logger(__name__)

# Constants
NOT_FOUND_MSG = "Not Found"

# Initialize performance optimization managers on module load
_performance_managers_initialized = False


def _get_callback_timeouts():
    """Get coordinated timeout values to prevent mismatch with file processing.

    This ensures callback tasks have adequate time to complete even if file processing
    took longer than expected. Uses workflow-level timeout coordination.
    """
    from shared.infrastructure.config import WorkerConfig

    config = WorkerConfig()
    timeouts = config.get_coordinated_timeouts()
    return timeouts["callback"], timeouts["callback_soft"]


def _initialize_performance_managers():
    """Initialize performance optimization managers once per worker process."""
    global _performance_managers_initialized

    if _performance_managers_initialized:
        return

    try:
        # Initialize with worker configuration
        config = WorkerConfig()

        # Initialize cache manager
        cache_manager = initialize_cache_manager(config)
        logger.info(f"Cache manager initialized: available={cache_manager.is_available}")

        # Initialize backoff and retry managers
        initialize_backoff_managers(cache_manager)
        logger.info("Backoff and retry managers initialized")

        _performance_managers_initialized = True
        logger.info("All performance optimization managers initialized successfully")

    except Exception as e:
        logger.warning(
            f"Failed to initialize performance managers: {e}. Callback will work without optimizations."
        )


def _map_execution_status_to_pipeline_status(execution_status: str) -> str:
    """Map workflow execution status to pipeline status.

    Based on the Pipeline model PipelineStatus choices:
    - SUCCESS = "SUCCESS"
    - FAILURE = "FAILURE"
    - INPROGRESS = "INPROGRESS"
    - YET_TO_START = "YET_TO_START"
    - RESTARTING = "RESTARTING"
    - PAUSED = "PAUSED"

    Args:
        execution_status: Workflow execution status

    Returns:
        Corresponding pipeline status
    """
    status_mapping = {
        # ExecutionStatus enum values
        ExecutionStatus.COMPLETED.value: PipelineStatus.SUCCESS.value,
        ExecutionStatus.ERROR.value: PipelineStatus.FAILURE.value,
        ExecutionStatus.EXECUTING.value: PipelineStatus.INPROGRESS.value,
        ExecutionStatus.PENDING.value: PipelineStatus.YET_TO_START.value,
        ExecutionStatus.STOPPED.value: PipelineStatus.FAILURE.value,
        ExecutionStatus.QUEUED.value: PipelineStatus.INPROGRESS.value,
        ExecutionStatus.CANCELED.value: PipelineStatus.FAILURE.value,
        # Legacy status values for backward compatibility
        "SUCCESS": PipelineStatus.SUCCESS.value,  # Legacy alias for COMPLETED
        "FAILED": PipelineStatus.FAILURE.value,  # Legacy alias for ERROR
        "FAILURE": PipelineStatus.FAILURE.value,  # Legacy variant
        "RUNNING": PipelineStatus.INPROGRESS.value,  # Legacy alias for EXECUTING
        "INPROGRESS": PipelineStatus.INPROGRESS.value,  # Legacy variant
        "YET_TO_START": PipelineStatus.YET_TO_START.value,  # Legacy variant
    }

    # Default to FAILURE for unknown statuses
    return status_mapping.get(execution_status.upper(), "FAILURE")


def _fetch_pipeline_data(
    pipeline_id: str, organization_id: str, api_client: InternalAPIClient
) -> dict | None:
    """Fetch complete pipeline data from Pipeline or APIDeployment models via internal API.

    This function calls the v1/pipeline/{pipeline_id}/ endpoint which returns either:
    - Pipeline model data (if it's an ETL/TASK/APP pipeline)
    - APIDeployment model data (if it's an API deployment)

    Args:
        pipeline_id: Pipeline or API deployment ID
        organization_id: Organization context
        api_client: API client instance

    Returns:
        Complete pipeline data dict or None if not found
    """
    try:
        logger.debug(
            f"Fetching complete pipeline data for {pipeline_id} from internal API"
        )

        # Set organization context for API call
        api_client.set_organization_context(organization_id)

        # Call the pipeline data endpoint (from execution_client.py)
        response = api_client.get_pipeline_data(pipeline_id, organization_id)

        if response.success and response.data:
            # The response.data might be the pipeline data directly, or nested under "pipeline"
            if "pipeline" in response.data:
                pipeline_data = response.data.get("pipeline", {})
            else:
                # Treat response.data as pipeline data directly
                pipeline_data = response.data

            # Determine if this is an API deployment or Pipeline based on available fields
            # APIDeployment has: api_name, display_name, api_endpoint
            # Pipeline has: pipeline_name, pipeline_type
            is_api = bool(
                pipeline_data.get("api_name") or pipeline_data.get("api_endpoint")
            )

            if is_api:
                # This is APIDeployment data
                pipeline_name = pipeline_data.get("api_name")
                pipeline_type = PipelineType.API.value
                logger.info(
                    f"Found API deployment {pipeline_id}: name='{pipeline_name}', type='{pipeline_type}', display_name='{pipeline_data.get('display_name')}'"
                )
            else:
                # This is Pipeline data
                pipeline_name = pipeline_data.get("pipeline_name")
                pipeline_type = pipeline_data.get("pipeline_type", PipelineType.ETL.value)
                logger.info(
                    f"Found Pipeline {pipeline_id}: name='{pipeline_name}', type='{pipeline_type}', active={pipeline_data.get('active')}"
                )

            # Add computed fields to the data for compatibility
            pipeline_data["resolved_pipeline_name"] = pipeline_name
            pipeline_data["resolved_pipeline_type"] = pipeline_type
            pipeline_data["is_api"] = is_api

            return pipeline_data
        else:
            logger.warning(
                f"Pipeline data API failed for {pipeline_id}: {response.error}"
            )
            return None

    except Exception as e:
        logger.error(f"Failed to fetch pipeline data for {pipeline_id}: {e}")
        return None


def _fetch_api_deployment_data(
    api_id: str, organization_id: str, api_client: InternalAPIClient
) -> dict | None:
    """Fetch APIDeployment data directly from v1 API deployment endpoint.

    This function is optimized for process_batch_callback_api since we know
    we're dealing with an API deployment. It uses the v1/api-deployments/{api_id}/
    endpoint which directly queries the APIDeployment model without checking Pipeline.

    Args:
        api_id: API deployment ID
        organization_id: Organization context
        api_client: API client instance

    Returns:
        Complete APIDeployment data dict or None if not found
    """
    try:
        logger.debug(
            f"Fetching APIDeployment data for {api_id} from v1 API deployment endpoint"
        )

        # Set organization context for API call
        api_client.set_organization_context(organization_id)

        # Call the v1 API deployment data endpoint
        response = api_client.get_api_deployment_data(api_id, organization_id)
        # DEFENSIVE: Handle both APIResponse objects and dict responses (due to caching inconsistency)
        if isinstance(response, dict):
            # Cache returned raw dict instead of APIResponse - convert it
            logger.warning(f"Converting dict response to APIResponse for {api_id}")
            from ..shared.data.response_models import APIResponse

            response = APIResponse.from_dict(response)

        if response.success and response.data:
            # Response format: {"status": "success", "pipeline": {...}}
            pipeline_data = response.data.get("pipeline", {})

            # API deployment data structure from serializer:
            pipeline_name = pipeline_data.get("api_name")
            pipeline_type = PipelineType.API.value

            logger.info(
                f"Found APIDeployment {api_id}: name='{pipeline_name}', type='{pipeline_type}', display_name='{pipeline_data.get('display_name')}'"
            )

            # Add computed fields for compatibility
            pipeline_data["resolved_pipeline_name"] = pipeline_name
            pipeline_data["resolved_pipeline_type"] = pipeline_type
            pipeline_data["is_api"] = True

            return pipeline_data
        else:
            logger.warning(
                f"API deployment data API failed for {api_id}: {response.error}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Failed to fetch API deployment data for {api_id}: {e}", exc_info=True
        )
        return None


def _update_pipeline_directly(
    pipeline_id: str,
    execution_id: str,
    status: str,
    organization_id: str,
    api_client: InternalAPIClient,
    **additional_fields,
) -> bool:
    """Update pipeline status using direct API call.

    Args:
        pipeline_id: Pipeline ID
        execution_id: Execution ID
        status: Pipeline status
        organization_id: Organization context
        api_client: API client instance
        **additional_fields: Additional pipeline fields

    Returns:
        True if update was successful
    """
    try:
        api_client.update_pipeline_status(
            pipeline_id=pipeline_id,
            status=status,
            organization_id=organization_id,
            **additional_fields,
        )

        # Invalidate cache after successful update
        cache_manager = get_cache_manager()
        if cache_manager:
            cache_manager.invalidate_pipeline_status(pipeline_id, organization_id)

        logger.debug(f"Pipeline update for {pipeline_id}: {status}")
        return True

    except Exception as e:
        logger.error(
            f"Failed to update pipeline status for {pipeline_id}: {e}", exc_info=True
        )
        return False


def _get_performance_stats() -> dict:
    """Get performance optimization statistics.

    Returns:
        Dictionary with performance statistics
    """
    stats = {}

    # Cache manager stats
    cache_manager = get_cache_manager()
    if cache_manager:
        stats["cache"] = cache_manager.get_cache_stats()

    # Note: Batch processor removed - it was ineffective with auto-flush disabled
    stats["optimizations"] = {
        "eliminated_batch_processor": True,
        "using_direct_api_calls": True,
    }

    return stats


class CallbackContext:
    """Container for callback processing context data."""

    def __init__(self):
        self.task_id: str = ""
        self.execution_id: str = ""
        self.pipeline_id: str | None = None
        self.organization_id: str | None = None
        self.workflow_id: str | None = None
        self.pipeline_name: str | None = None
        self.pipeline_type: str | None = None
        self.pipeline_data: dict[str, Any] | None = None
        self.api_client: InternalAPIClient | None = None


def _extract_callback_parameters(
    task_instance, results: list, kwargs: dict[str, Any]
) -> CallbackContext:
    """Extract and validate all callback parameters using workflow execution as single source of truth.

    Args:
        task_instance: The Celery task instance
        results: List of batch results
        kwargs: Keyword arguments from the callback

    Returns:
        CallbackContext with all parameters populated

    Raises:
        ValueError: If required parameters are missing
    """
    context = CallbackContext()
    context.task_id = (
        task_instance.request.id if hasattr(task_instance, "request") else "unknown"
    )

    # 1. Get execution_id from kwargs (always present)
    context.execution_id = kwargs.get("execution_id")
    if not context.execution_id:
        raise ValueError("execution_id is required in kwargs")

    # 2. Always fetch workflow execution data (authoritative source for all context)
    logger.info(
        f"Fetching complete context from workflow execution {context.execution_id}"
    )

    config = WorkerConfig()
    with InternalAPIClient(config) as temp_api_client:
        try:
            execution_response = temp_api_client.get_workflow_execution(
                context.execution_id
            )

            if not execution_response.success:
                raise ValueError(
                    f"Failed to get workflow execution: {execution_response.error}"
                )

            execution_data = execution_response.data

            # Extract nested structures from response (corrected paths)
            execution_info = execution_data.get("execution", {})
            workflow_definition = execution_data.get("workflow_definition", {})
            organization_context = execution_data.get("organization_context", {})
            source_config = execution_data.get("source_config", {})

            # 3. Extract parameters with kwargs as fast path, execution data as fallback
            context.pipeline_id = kwargs.get("pipeline_id") or execution_info.get(
                "pipeline_id"
            )
            context.organization_id = (
                kwargs.get("organization_id")
                or organization_context.get("organization_id")
                or workflow_definition.get("organization_id")
            )

            # Always populate workflow_id from correct nested path
            context.workflow_id = execution_info.get(
                "workflow_id"
            ) or workflow_definition.get("workflow_id")

            # Use existing API detection from source_config (no additional API calls needed)
            is_api_deployment = source_config.get("is_api", False)

            if is_api_deployment:
                # This is an API deployment
                context.pipeline_data = {
                    "is_api": True,
                    "resolved_pipeline_type": "API",
                    "resolved_pipeline_name": workflow_definition.get(
                        "workflow_name", "Unknown API"
                    ),
                }
                context.pipeline_type = "API"
                context.pipeline_name = workflow_definition.get(
                    "workflow_name", "Unknown API"
                )
                logger.info(
                    f"Detected API deployment from source_config: {context.pipeline_id}"
                )
            else:
                # This is ETL/TASK/APP workflow
                context.pipeline_data = {
                    "is_api": False,
                    "resolved_pipeline_type": "ETL",
                    "resolved_pipeline_name": workflow_definition.get(
                        "workflow_name", "Unknown Workflow"
                    ),
                }
                context.pipeline_type = "ETL"
                context.pipeline_name = workflow_definition.get(
                    "workflow_name", "Unknown Workflow"
                )
                logger.info(
                    f"Detected ETL workflow from source_config: {context.pipeline_id}"
                )

            logger.info(
                f"Extracted from kwargs: pipeline_id={kwargs.get('pipeline_id')}, org_id={kwargs.get('organization_id')}"
            )
            logger.info(
                f"Extracted from execution: workflow_id={context.workflow_id}, is_api={is_api_deployment}, pipeline_type={context.pipeline_type}"
            )

        except Exception as e:
            logger.error(f"Failed to fetch workflow execution context: {e}")
            raise ValueError(f"Could not get execution context: {e}")

    # 4. Validate required context is now available
    if not context.organization_id:
        raise ValueError("organization_id could not be determined from execution context")

    # 5. Setup persistent API client for callback operations (single source of truth)
    config = WorkerConfig()
    context.api_client = InternalAPIClient(config)
    context.api_client.set_organization_context(context.organization_id)

    logger.info(
        f"✅ Extracted complete callback context: execution={context.execution_id}, "
        f"pipeline={context.pipeline_id}, workflow={context.workflow_id}, org={context.organization_id}, "
        f"api_client=initialized, pipeline_data=✓, type={context.pipeline_type}"
    )

    return context


def _process_results_and_update_status(
    context: CallbackContext, results: list, config: WorkerConfig
) -> tuple[dict[str, Any], str]:
    """Process batch results, calculate final status, and update execution.

    Args:
        context: Callback context with execution details
        results: List of batch processing results
        config: Worker configuration

    Returns:
        Tuple of (aggregated_results, final_status)
    """
    # Aggregate results from all file batches (exactly like Django backend)
    aggregated_results = aggregate_file_batch_results(results)

    # FIXED: Use wall-clock execution time instead of summed file processing times
    # For parallel execution: 3 files x 3 sec each = 4 sec wall-clock, not 9 sec
    wall_clock_time = WallClockTimeCalculator.calculate_execution_time(
        context.api_client, context.execution_id, context.organization_id
    )

    original_time = aggregated_results["total_execution_time"]
    if wall_clock_time != original_time:
        logger.info(
            f"FIXED: Wall-clock execution time: {wall_clock_time:.2f}s (was: {original_time:.2f}s summed)"
        )
        aggregated_results["total_execution_time"] = wall_clock_time

    # Update execution with aggregated results using optimized batching
    # Set ERROR status only if ALL files failed (per API documentation)
    final_status = (
        ExecutionStatus.COMPLETED.value
        if aggregated_results["failed_files"] != aggregated_results["total_files"]
        else ExecutionStatus.ERROR.value
    )

    # OPTIMIZATION: Return results without status update
    # Status update is now consolidated in main flow to avoid redundant calls
    return aggregated_results, final_status


def _finalize_execution(
    context: CallbackContext, final_status: str, aggregated_results: dict[str, Any]
) -> dict[str, Any]:
    """Finalize the workflow execution with optimized single status update.

    OPTIMIZATION: This is the ONLY place where workflow execution status is updated,
    eliminating redundant status calls and reducing API overhead.

    Args:
        context: Callback context with execution details
        final_status: Final execution status
        aggregated_results: Aggregated processing results

    Returns:
        Finalization result dictionary
    """
    try:
        # OPTIMIZATION: Single consolidated workflow execution status update
        # Note: execution_time is now automatically calculated by the model's update_execution method
        context.api_client.update_workflow_execution_status(
            execution_id=context.execution_id,
            status=final_status,
            total_files=aggregated_results["total_files"],
            organization_id=context.organization_id,
        )

        finalization_result = {
            "status": "completed",
            "method": "optimized_status_update",
            "message": "Execution finalized via optimized status update",
            "execution_id": context.execution_id,
            "final_status": final_status,
            "total_files": aggregated_results["total_files"],
            # execution_time is now calculated by backend model from (timezone.now() - created_at)
        }

        logger.info(f"Successfully finalized execution {context.execution_id}")

        return finalization_result

    except Exception as e:
        logger.error(
            f"Failed to finalize execution {context.execution_id} via status update: {e}"
        )
        # Return error result instead of re-raising to maintain callback flow
        return {
            "status": "failed",
            "method": "optimized_status_update",
            "error": str(e),
            "execution_id": context.execution_id,
        }


def _update_pipeline_status(context: CallbackContext, final_status: str) -> bool:
    """Update pipeline status using optimized batching.

    Args:
        context: Callback context with pipeline details
        final_status: Final execution status to map to pipeline status

    Returns:
        True if pipeline was updated successfully
    """
    # OPTIMIZATION: Skip pipeline status update for API deployments to avoid 404 errors
    pipeline_updated = False
    if context.pipeline_id:
        # First validate that pipeline_id is a proper UUID
        try:
            import uuid

            uuid.UUID(str(context.pipeline_id))
        except ValueError:
            # Invalid UUID - this is likely an execution_log_id from worker-based execution
            logger.info(
                f"WORKERS FLOW: Skipping pipeline status update - pipeline_id '{context.pipeline_id}' is not a valid UUID (likely execution_log_id from worker-based execution)"
            )
            return True  # Return True to indicate successful handling (no pipeline to update)

        # Check if this is an API deployment (has pipeline_data with is_api=True)
        is_api_deployment = context.pipeline_data and context.pipeline_data.get(
            "is_api", False
        )

        if is_api_deployment:
            logger.info(
                f"OPTIMIZATION: Skipping pipeline status update for API deployment {context.pipeline_id} (no Pipeline record exists)"
            )
            pipeline_updated = True  # Mark as "updated" to avoid warnings
        else:
            try:
                logger.info(
                    f"Updating pipeline {context.pipeline_id} status with organization_id: {context.organization_id}"
                )

                # Map execution status to pipeline status
                pipeline_status = _map_execution_status_to_pipeline_status(final_status)

                # Use direct pipeline update (optimized - removed ineffective batching)
                pipeline_updated = _update_pipeline_directly(
                    pipeline_id=context.pipeline_id,
                    execution_id=context.execution_id,
                    status=pipeline_status,
                    organization_id=context.organization_id,
                    api_client=context.api_client,
                    last_run_status=pipeline_status,
                    last_run_time=time.time(),
                    increment_run_count=True,
                )

                if pipeline_updated:
                    logger.info(
                        f"Successfully updated pipeline {context.pipeline_id} last_run_status to {pipeline_status}"
                    )
                else:
                    logger.warning(
                        f"Failed to update pipeline for {context.pipeline_id} - pipeline_status={pipeline_status}, pipeline_name={context.pipeline_name}"
                    )
            except CircuitBreakerOpenError:
                # TODO: Implement retry queue to prevent lost DB updates
                # When circuit breaker is open, we should queue the update for later retry
                # instead of skipping it completely. This could lead to stale pipeline status in DB.
                # Proposed solution:
                # 1. Queue update in Redis: redis_client.lpush(f"pending_pipeline_updates:{org_id}", {...})
                # 2. Add reconciliation task to process pending updates when circuit closes
                # 3. Consider using eventual consistency pattern with status reconciliation
                logger.warning(
                    "Pipeline status update circuit breaker open - skipping update"
                )
                pass
            except Exception as e:
                # ROOT CAUSE FIX: Handle pipeline not found errors gracefully
                if (
                    "404" in str(e)
                    or "Pipeline not found" in str(e)
                    or NOT_FOUND_MSG in str(e)
                ):
                    logger.info(
                        f"Pipeline {context.pipeline_id} not found - likely using stale reference, skipping update"
                    )
                    pass
                else:
                    logger.warning(f"Failed to update pipeline status: {str(e)}")

    return pipeline_updated


def _is_api_deployment(context: CallbackContext) -> bool:
    """Check if this is an API deployment execution.

    API deployments should preserve cache for subsequent requests.
    """
    try:
        # Check if this is an API deployment by looking at the pipeline type
        if hasattr(context, "pipeline_type") and context.pipeline_type:
            return context.pipeline_type.lower() == "api"

        # Fallback: check execution type if available
        if hasattr(context, "execution_type") and context.execution_type:
            return "api" in context.execution_type.lower()

        # If we can't determine, be conservative and assume it's not API
        return False
    except Exception:
        # If any error occurs, be conservative
        return False


def _cleanup_execution_cache_direct(context: CallbackContext) -> None:
    """Clean execution cache directly using cache manager.

    This replaces the broken backend API call with direct cache operations.
    """
    try:
        # Use the existing cache manager to clear execution cache
        from shared.cache import get_cache_manager

        cache_manager = get_cache_manager()
        if cache_manager and hasattr(cache_manager, "delete_execution_cache"):
            # Use the direct cache method similar to ExecutionCacheUtils.delete_execution
            cache_manager.delete_execution_cache(
                workflow_id=context.workflow_id, execution_id=context.execution_id
            )
            logger.info(f"Cleared execution cache for {context.execution_id}")
        else:
            logger.debug("Cache manager not available or method not found")
    except ImportError:
        logger.debug("Cache manager not available for direct cleanup")
    except Exception as e:
        logger.warning(f"Failed to clear execution cache directly: {e}")
        # Don't raise - cache cleanup is not critical for callback success


def _create_cleanup_result(cleanup_type: str, status: str, **kwargs) -> dict[str, Any]:
    """Create standardized cleanup result structure.

    Args:
        cleanup_type: Type of cleanup (api, workflow, backend, etc.)
        status: Status (success, failed, skipped)
        **kwargs: Additional fields (message, error, cleaned_paths, files_deleted, etc.)

    Returns:
        Standardized cleanup result dictionary
    """
    result = {
        "type": cleanup_type,
        "status": status,
    }

    # Add optional fields if provided
    if "message" in kwargs:
        result["message"] = kwargs["message"]
    if "error" in kwargs:
        result["error"] = str(kwargs["error"])
    if "cleaned_paths" in kwargs:
        result["cleaned_paths"] = kwargs["cleaned_paths"]
    if "failed_paths" in kwargs:
        result["failed_paths"] = kwargs["failed_paths"]
    if "files_deleted" in kwargs:
        result["files_deleted"] = kwargs["files_deleted"]
    if "method" in kwargs:
        result["method"] = kwargs["method"]
    if "reason" in kwargs:
        result["reason"] = kwargs["reason"]

    return result


def _setup_file_system(storage_type):
    """Setup FileSystem instance with error handling.

    Args:
        storage_type: FileStorageType enum value

    Returns:
        FileStorage instance

    Raises:
        Exception: If FileSystem setup fails
    """
    from unstract.filesystem import FileSystem

    file_system = FileSystem(storage_type)
    return file_system.get_file_storage()


def _cleanup_directory(
    file_storage, directory_path: str, cleanup_type: str
) -> dict[str, Any]:
    """Perform directory cleanup with file counting and logging.

    Args:
        file_storage: FileStorage instance
        directory_path: Path to directory to clean
        cleanup_type: Type identifier for logging (api/workflow)

    Returns:
        Cleanup result dictionary
    """
    try:
        if file_storage.exists(directory_path):
            # Get file count before cleanup
            try:
                files = file_storage.ls(directory_path)
                file_count = len(files) if files else 0

                # Remove the entire execution directory
                file_storage.rm(directory_path, recursive=True)

                logger.info(
                    f"✅ Successfully cleaned up {cleanup_type} execution directory: {directory_path} ({file_count} files)"
                )

                return _create_cleanup_result(
                    cleanup_type=cleanup_type,
                    status="success",
                    cleaned_paths=[directory_path],
                    files_deleted=file_count,
                    message=f"{cleanup_type.title()} execution directory cleaned: {directory_path}",
                )

            except Exception as cleanup_error:
                logger.error(
                    f"Failed to clean {cleanup_type} execution directory: {cleanup_error}"
                )
                return _create_cleanup_result(
                    cleanup_type=cleanup_type,
                    status="failed",
                    error=cleanup_error,
                    failed_paths=[directory_path],
                )
        else:
            logger.warning(
                f"{cleanup_type.title()} execution directory not found: {directory_path}"
            )
            return _create_cleanup_result(
                cleanup_type=cleanup_type,
                status="skipped",
                message=f"Directory not found: {directory_path}",
            )

    except Exception as e:
        logger.error(f"Directory cleanup failed for {cleanup_type}: {e}")
        return _create_cleanup_result(cleanup_type=cleanup_type, status="failed", error=e)


def _get_execution_directory(context: CallbackContext) -> tuple[str, any, str]:
    """Determine execution directory path, storage type, and cleanup type.

    Args:
        context: Callback context with execution details

    Returns:
        Tuple of (directory_path, storage_type, cleanup_type)

    Raises:
        ValueError: If execution type cannot be determined
    """
    from unstract.filesystem import FileStorageType
    from unstract.workflow_execution.execution_file_handler import ExecutionFileHandler

    # Determine if this is an API or workflow execution
    is_api_execution = context.pipeline_data and context.pipeline_data.get(
        "is_api", False
    )

    if is_api_execution and context.pipeline_id:
        # API execution
        api_execution_dir = ExecutionFileHandler.get_api_execution_dir(
            workflow_id=context.workflow_id,
            execution_id=context.execution_id,
            organization_id=context.organization_id,
        )
        return api_execution_dir, FileStorageType.API, "api"

    elif context.workflow_id:
        # Workflow execution
        file_handler = ExecutionFileHandler(
            workflow_id=context.workflow_id,
            execution_id=context.execution_id,
            organization_id=context.organization_id,
        )
        execution_dir = file_handler.execution_dir
        return execution_dir, FileStorageType.WORKFLOW_EXECUTION, "workflow"

    else:
        raise ValueError(
            f"Cannot determine execution type: is_api={is_api_execution}, "
            f"workflow_id={context.workflow_id}, pipeline_id={context.pipeline_id}"
        )


def _cleanup_execution_directory(context: CallbackContext) -> dict[str, Any]:
    """Clean up execution directory with unified logic for API and workflow types.

    Args:
        context: Callback context with execution details

    Returns:
        Directory cleanup result dictionary
    """
    try:
        # Get directory path and storage type
        directory_path, storage_type, cleanup_type = _get_execution_directory(context)

        logger.info(
            f"🧹 Starting {cleanup_type} execution directory cleanup for {context.execution_id}"
        )

        # Setup file system
        file_storage = _setup_file_system(storage_type)

        # Perform cleanup
        return _cleanup_directory(file_storage, directory_path, cleanup_type)

    except ValueError as ve:
        logger.warning(f"⚠️ {ve}")
        return _create_cleanup_result(
            cleanup_type="unknown", status="skipped", message=str(ve)
        )
    except Exception as e:
        logger.error(f"Failed to setup directory cleanup: {e}")
        return _create_cleanup_result(
            cleanup_type="unknown", status="failed", error=f"Setup error: {str(e)}"
        )


def _cleanup_backend_cache(context: CallbackContext) -> dict[str, Any]:
    """Clean up backend cache for non-API deployments.

    Args:
        context: Callback context with execution details

    Returns:
        Backend cleanup result dictionary
    """
    try:
        # Only clear execution cache for non-API deployments
        # API deployments may need cache persistence for subsequent requests
        if not _is_api_deployment(context):
            _cleanup_execution_cache_direct(context)
            logger.info(
                "✅ Direct execution cache cleanup completed for non-API deployment"
            )
            return _create_cleanup_result(
                cleanup_type="backend",
                status="cleaned_direct",
                method="direct_cache_cleanup",
                message="Execution cache cleared for non-API deployment",
            )
        else:
            logger.info("ℹ️  Cache cleanup skipped for API deployment (cache preserved)")
            return _create_cleanup_result(
                cleanup_type="backend",
                status="skipped",
                reason="api_deployment",
                message="Cache preserved for API deployment",
            )
    except Exception as e:
        logger.warning(f"Direct cache cleanup failed: {e}")
        return _create_cleanup_result(cleanup_type="backend", status="failed", error=e)


def _cleanup_execution_resources(context: CallbackContext) -> dict[str, Any]:
    """Streamlined resource cleanup with unified logic for backend cache and directories.

    REFACTORED: Eliminated ~200 lines of duplicated code by extracting common utilities.
    Now uses shared functions for consistent error handling and result structures.

    Args:
        context: Callback context with execution details

    Returns:
        Cleanup result dictionary with status and details
    """
    # 1. Backend cache cleanup
    backend_result = _cleanup_backend_cache(context)

    # 2. Directory cleanup (unified logic for API and workflow)
    directory_result = _cleanup_execution_directory(context)

    # 3. Aggregate results with consistent status logic
    backend_success = backend_result.get("status") in [
        "success",
        "completed",
        "skipped",
        "cleaned_direct",
    ]
    directory_success = directory_result.get("status") in ["success", "skipped"]

    overall_status = "completed" if (backend_success and directory_success) else "partial"

    return {
        "status": overall_status,
        "backend": backend_result,
        "directories": directory_result,
    }


def _handle_callback_notifications(context: CallbackContext) -> None:
    """Handle status notifications after successful batch completion.

    Args:
        context: Callback context with execution details
    """
    # Trigger notifications after successful batch completion
    try:
        # Try to trigger notifications using workflow_id if pipeline_id is None
        notification_target_id = (
            context.pipeline_id if context.pipeline_id else context.workflow_id
        )
        if notification_target_id:
            logger.info(
                f"Triggering notifications for target_id={notification_target_id} (execution completed)"
            )
            # Ensure organization context is set for notification requests
            context.api_client.set_organization_context(context.organization_id)
            handle_status_notifications(
                api_client=context.api_client,
                pipeline_id=notification_target_id,
                status=ExecutionStatus.COMPLETED.value,
                execution_id=context.execution_id,
                error_message=None,
                pipeline_name=context.pipeline_name,
                pipeline_type=context.pipeline_type,
                organization_id=context.organization_id,
            )
        else:
            logger.info("No target ID available for notifications")
    except Exception as notif_error:
        logger.warning(f"Failed to trigger completion notifications: {notif_error}")
        # Continue execution - notifications are not critical for callback success


def _process_batch_callback_core(
    task_instance, results, *args, **kwargs
) -> dict[str, Any]:
    """Simplified callback processing with optimized single-source-of-truth approach.

    OPTIMIZATIONS:
    - Single parameter extraction function handles all context setup
    - Only 2 essential status updates: workflow execution + pipeline status
    - Eliminated redundant organization context setup functions
    - Direct API calls replace ineffective batch processing

    Args:
        task_instance: The Celery task instance (self)
        results (list): List of results from each batch
        **kwargs: Additional arguments including execution_id, pipeline_id, organization_id

    Returns:
        Callback processing result with optimized execution flow
    """
    # Initialize performance optimizations
    _initialize_performance_managers()

    # Extract and validate all parameters using single source of truth
    context = _extract_callback_parameters(task_instance, results, kwargs)

    # Validate that context is properly set up (API client and organization already configured in _extract_callback_parameters)
    if not context.organization_id or not context.api_client:
        logger.error(
            f"CRITICAL: Context not properly initialized for execution {context.execution_id}. "
            f"organization_id={context.organization_id}, api_client={context.api_client is not None}"
        )
        raise RuntimeError(f"Invalid context for execution {context.execution_id}")

    # Note: Batch processor removed - it was ineffective with auto-flush disabled
    # Using direct API calls for the 1-2 status updates in callback is more efficient

    with log_context(
        task_id=context.task_id,
        execution_id=context.execution_id,
        workflow_id=context.workflow_id,
        organization_id=context.organization_id,
        pipeline_id=context.pipeline_id,
    ):
        logger.info(
            f"Starting batch callback processing for execution {context.execution_id}"
        )

        try:
            # Process and aggregate batch results
            config = WorkerConfig()  # Create config for wall-clock time calculation
            aggregated_results, final_status = _process_results_and_update_status(
                context, results, config
            )

            # 1. Update workflow execution status (consolidated single call)
            finalization_result = _finalize_execution(
                context, final_status, aggregated_results
            )

            # 2. Update pipeline status (second essential call)
            _update_pipeline_status(context, final_status)

            # 3. Cleanup execution resources (only for non-API deployments)
            cleanup_result = _cleanup_execution_resources(context)

            # Note: Destination processing is handled in file processing worker
            destination_results = {
                "status": "handled_in_file_processing",
                "successful_files": aggregated_results["successful_files"],
            }

            # Collect performance statistics
            performance_stats = _get_performance_stats()

            callback_result = {
                "status": "completed",
                "execution_id": context.execution_id,
                "workflow_id": context.workflow_id,
                "task_id": context.task_id,
                "aggregated_results": aggregated_results,
                "destination_results": destination_results,
                "finalization_result": finalization_result,
                "cleanup_result": cleanup_result,
                "pipeline_id": context.pipeline_id,
                "performance_optimizations": {
                    "optimized_finalization": True,  # Using simple status update instead of complex finalization
                    "direct_api_calls": True,  # Using direct API calls instead of ineffective batching
                    "cache_stats": performance_stats.get("cache", {}),
                    "optimizations": performance_stats.get("optimizations", {}),
                    "eliminated_complex_features": [
                        "finalize_workflow_execution",
                        "batch_processor (was disabled anyway)",
                    ],
                },
            }

            logger.info(
                f"Completed callback processing for execution {context.execution_id}"
            )

            # 4. Handle notifications (non-critical)
            _handle_callback_notifications(context)

            return callback_result

        except Exception as e:
            logger.error(
                f"Batch callback processing failed for execution {context.execution_id}: {e}"
            )

            # Try to mark execution as failed using simple status update
            try:
                # Reuse existing API client from context
                context.api_client.set_organization_context(context.organization_id)
                # Use optimized simple status update instead of complex finalization
                context.api_client.update_workflow_execution_status(
                    execution_id=context.execution_id,
                    status=ExecutionStatus.ERROR.value,
                    error_message=str(e)[:500],  # Limit error message length
                    organization_id=context.organization_id,
                )
                logger.info(f"Marked execution {context.execution_id} as failed")
            except Exception as cleanup_error:
                logger.error(f"Failed to mark execution as failed: {cleanup_error}")

            # Re-raise for Celery retry mechanism
            raise


@app.task(
    bind=True,
    name=TaskName.PROCESS_BATCH_CALLBACK,
    max_retries=0,  # Match Django backend pattern
    ignore_result=False,  # Match Django backend pattern
    task_time_limit=_get_callback_timeouts()[
        0
    ],  # Configurable hard timeout (default: 1 hour)
    task_soft_time_limit=_get_callback_timeouts()[
        1
    ],  # Configurable soft timeout (default: 55 minutes)
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
def process_batch_callback(self, results, *args, **kwargs) -> dict[str, Any]:
    """Callback task to handle batch processing results.

    This is the main task entry point for new workers.

    Args:
        results (list): List of results from each batch
        **kwargs: Additional arguments including execution_id

    Returns:
        Callback processing result
    """
    return _process_batch_callback_core(self, results, *args, **kwargs)


@app.task(
    bind=True,
    name="process_batch_callback_api",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    task_time_limit=_get_callback_timeouts()[
        0
    ],  # Configurable hard timeout (default: 1 hour)
    task_soft_time_limit=_get_callback_timeouts()[
        1
    ],  # Configurable soft timeout (default: 55 minutes)
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
def process_batch_callback_api(
    self,
    file_batch_results: list[dict[str, Any]],
    *args,
    **kwargs,
) -> dict[str, Any]:
    """Lightweight API batch callback processing task.

    This handles the final step of API workflow execution after all file batches complete.
    In a chord, this receives the results from all file processing tasks.

    Args:
        file_batch_results: Results from all file processing tasks (from chord)
        kwargs: Contains execution_id, pipeline_id, organization_id

    Returns:
        Final execution result
    """
    task_id = self.request.id

    # Extract parameters from kwargs (passed by API deployment worker)
    execution_id = kwargs.get("execution_id")
    pipeline_id = kwargs.get("pipeline_id")
    organization_id = kwargs.get("organization_id")

    if not execution_id:
        raise ValueError("execution_id is required in kwargs")

    logger.info(
        f"API callback received: execution_id={execution_id}, pipeline_id={pipeline_id}, organization_id={organization_id}"
    )

    # Get workflow execution context via API to get workflow_id and schema_name
    config = WorkerConfig()
    with InternalAPIClient(config) as api_client:
        # Set organization context BEFORE making API calls
        if organization_id:
            api_client.set_organization_context(organization_id)
            logger.info(f"Set organization context before API calls: {organization_id}")

        execution_response = api_client.get_workflow_execution(execution_id)
        if not execution_response.success:
            raise Exception(
                f"Failed to get execution context: {execution_response.error}"
            )
        execution_context = execution_response.data
        workflow_execution = execution_context.get("execution", {})
        workflow = execution_context.get("workflow", {})

        # Extract schema_name and workflow_id from context
        schema_name = organization_id  # For API callbacks, schema_name = organization_id
        workflow_id = workflow_execution.get("workflow_id") or workflow.get("id")

        logger.info(
            f"Extracted context: schema_name={schema_name}, workflow_id={workflow_id}, pipeline_id={pipeline_id}"
        )

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=organization_id,
        pipeline_id=pipeline_id,
    ):
        logger.info(
            f"Processing API callback for execution {execution_id} with {len(file_batch_results)} batch results"
        )

        try:
            # Initialize API client with organization context
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Get APIDeployment data directly from v2 API endpoint (optimized for API callbacks)
                pipeline_name = None
                pipeline_type = None
                pipeline_data = None

                if pipeline_id:
                    # Since we know this is an API callback, use the optimized API-specific endpoint
                    pipeline_data = _fetch_api_deployment_data(
                        pipeline_id, schema_name, api_client
                    )
                    if pipeline_data:
                        pipeline_name = pipeline_data.get("resolved_pipeline_name")
                        pipeline_type = pipeline_data.get("resolved_pipeline_type")
                        logger.info(
                            f"✅ APIDeployment data from v1/api-deployments endpoint: name='{pipeline_name}', type='{pipeline_type}', display_name='{pipeline_data.get('display_name')}'"
                        )
                    else:
                        # Fallback to unified endpoint only if API deployment endpoint fails
                        logger.warning(
                            f"v1/api-deployments endpoint failed for {pipeline_id}, falling back to unified endpoint"
                        )
                        pipeline_data = _fetch_pipeline_data(
                            pipeline_id, schema_name, api_client
                        )
                        if pipeline_data:
                            pipeline_name = pipeline_data.get("resolved_pipeline_name")
                            pipeline_type = pipeline_data.get("resolved_pipeline_type")
                            logger.info(
                                f"✅ Pipeline data from fallback unified endpoint: name='{pipeline_name}', type='{pipeline_type}'"
                            )
                else:
                    # No pipeline_id provided - this is a critical error for API callbacks
                    error_msg = f"No pipeline_id provided for API callback. execution_id={execution_id}, workflow_id={workflow_id}"
                    logger.error(error_msg)
                    logger.error(
                        "API callbacks require pipeline_id to fetch APIDeployment data. Cannot proceed without it."
                    )
                    raise ValueError(error_msg)

                # Aggregate results from all file processing tasks
                total_files_processed = 0
                all_file_results = []

                for batch_result in file_batch_results:
                    if batch_result and isinstance(batch_result, dict):
                        total_files_processed += batch_result.get("files_processed", 0)
                        all_file_results.extend(batch_result.get("file_results", []))

                # Check for errors in file results to determine execution status
                failed_files = []
                successful_files = 0

                for file_result in all_file_results:
                    if file_result.get("error"):
                        failed_files.append(
                            {
                                "file": file_result.get("file_name", "unknown"),
                                "error": file_result.get("error"),
                            }
                        )
                    else:
                        successful_files += 1

                # Calculate execution time and finalize
                # FIXED: Use wall-clock time instead of sum of file processing times
                # For parallel execution: 3 files x 3 sec each = 4 sec wall-clock, not 9 sec
                execution_time = WallClockTimeCalculator.calculate_execution_time(
                    api_client, execution_id, organization_id, all_file_results
                )

                # Debug logging for execution time calculation
                if execution_time == 0:
                    logger.warning(
                        f"Execution time is 0! File results for execution {execution_id}"
                    )

                # Determine execution status based on file results (ERROR only if ALL files failed)
                total_files = len(all_file_results)
                if failed_files and len(failed_files) == total_files:
                    # ALL files failed - mark as ERROR
                    execution_status = ExecutionStatus.ERROR.value
                    logger.error(
                        f"API deployment execution {execution_id} failed - all {total_files} files failed"
                    )
                else:
                    # Some or all files succeeded - mark as COMPLETED
                    execution_status = ExecutionStatus.COMPLETED.value
                    if failed_files:
                        logger.warning(
                            f"API deployment execution {execution_id} completed with {len(failed_files)} failed files out of {total_files} total"
                        )

                # Update workflow execution status
                api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status=execution_status,
                    total_files=total_files,
                    organization_id=organization_id,
                )

                # OPTIMIZATION: Skip pipeline status update for API deployments
                # API deployments use APIDeployment model, not Pipeline model
                # Pipeline status updates don't apply to APIDeployments and cause 404 errors
                if pipeline_id:
                    # API callbacks always handle APIDeployments, so skip pipeline status update
                    logger.info(
                        f"OPTIMIZATION: Skipping pipeline status update for API deployment {pipeline_id} (no Pipeline record exists)"
                    )

                    # Trigger notifications for API deployment
                    try:
                        config = WorkerConfig.from_env("CALLBACK")
                        handle_status_notifications(
                            api_client=api_client,
                            pipeline_id=pipeline_id,
                            status=ExecutionStatus.COMPLETED.value,  # Use execution status, not pipeline status
                            execution_id=execution_id,
                            error_message=None,  # API callbacks typically don't have error messages
                            pipeline_name=pipeline_name,
                            pipeline_type=pipeline_type,
                            organization_id=organization_id,
                        )
                    except Exception as notif_error:
                        logger.warning(
                            f"Failed to trigger API notifications for {pipeline_id}: {notif_error}"
                        )
                        # Continue execution - notifications are not critical for callback success

                callback_result = {
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "pipeline_id": pipeline_id,
                    "status": "completed",
                    "total_files_processed": total_files_processed,
                    "total_execution_time": execution_time,
                    "batches_processed": len(file_batch_results),
                    "task_id": task_id,
                    "optimization": {
                        "method": "simple_status_update",
                        "eliminated_complex_finalization": True,
                    },
                }

                logger.info(
                    f"Successfully completed API callback for execution {execution_id}"
                )
                return callback_result

        except Exception as e:
            logger.error(
                f"API callback processing failed for execution {execution_id}: {e}"
            )

            # Try to update execution status to failed
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    # Update execution status to error
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e)[:500],  # Limit error message length
                        organization_id=schema_name,
                    )

                    # OPTIMIZATION: Skip pipeline status update for API deployments on error
                    if pipeline_id:
                        logger.info(
                            f"OPTIMIZATION: Skipping pipeline status update for API deployment {pipeline_id} on error (no Pipeline record exists)"
                        )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            raise


@app.task(
    bind=True,
    name="workflow_manager.workflow_v2.file_execution_tasks.process_batch_callback",
    max_retries=0,
    ignore_result=False,
)
def process_batch_callback_django_compat(
    self, results, *args, **kwargs
) -> dict[str, Any]:
    """Backward compatibility wrapper for Django backend callback task name.

    This allows new workers to handle callback tasks sent from the old Django backend
    during the transition period when both systems are running.

    Args:
        results: Batch processing results from Django backend
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Returns:
        Same result as process_batch_callback
    """
    logger.info(
        "Processing batch callback via Django compatibility task name: "
        "workflow_manager.workflow_v2.file_execution_tasks.process_batch_callback"
    )

    # Delegate to the core implementation (same as main task)
    return _process_batch_callback_core(self, results, *args, **kwargs)
