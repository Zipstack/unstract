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
from shared.infrastructure import create_api_client

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
from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger
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
        self.file_executions: list[dict[str, Any]] = []


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


def _fetch_pipeline_data_simplified(
    pipeline_id: str,
    organization_id: str,
    api_client: InternalAPIClient,
    is_api_deployment: bool = False,
) -> tuple[str | None, str | None]:
    """Simplified pipeline data fetching that returns only name and type.

    Args:
        pipeline_id: Pipeline or API deployment ID
        organization_id: Organization context
        api_client: API client instance
        is_api_deployment: If True, use API deployment endpoint; otherwise try unified endpoint

    Returns:
        Tuple of (pipeline_name, pipeline_type) or (None, None) if not found
    """
    try:
        api_client.set_organization_context(organization_id)

        if is_api_deployment:
            # Try API deployment endpoint first
            response = api_client.get_api_deployment_data(pipeline_id, organization_id)
            if response.success and response.data:
                pipeline_data = response.data.get("pipeline", {})
                return pipeline_data.get("api_name"), PipelineType.API.value

        # Fallback to unified pipeline endpoint
        response = api_client.get_pipeline_data(pipeline_id, organization_id)
        if response.success and response.data:
            pipeline_data = response.data.get("pipeline", response.data)

            # Check if it's an API deployment or regular pipeline
            if pipeline_data.get("api_name") or pipeline_data.get("api_endpoint"):
                return pipeline_data.get("api_name"), PipelineType.API.value
            else:
                return pipeline_data.get("pipeline_name"), pipeline_data.get(
                    "pipeline_type", PipelineType.ETL.value
                )

        logger.warning(f"No pipeline data found for {pipeline_id}")
        return None, None

    except Exception as e:
        logger.warning(f"Failed to fetch pipeline data for {pipeline_id}: {e}")
        return None, None


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


def _determine_execution_status_unified(
    file_batch_results: list[dict[str, Any]],
    api_client: InternalAPIClient,
    execution_id: str,
    organization_id: str,
) -> tuple[dict[str, Any], str, int]:
    """Unified status determination logic with timeout detection for all callback types.

    This function combines the logic from both process_batch_callback_api and
    _process_batch_callback_core, ensuring consistent status determination across
    all callback tasks including timeout failure detection.

    Args:
        file_batch_results: Results from all file processing tasks
        api_client: Internal API client for workflow execution queries
        execution_id: Workflow execution ID
        organization_id: Organization context

    Returns:
        Tuple of (aggregated_results, final_status, expected_files)
    """
    # Step 1: Aggregate results from all file batches using existing helper
    aggregated_results = aggregate_file_batch_results(file_batch_results)

    # Step 2: Calculate wall-clock execution time (consistent across both implementations)
    wall_clock_time = WallClockTimeCalculator.calculate_execution_time(
        api_client,
        execution_id,
        organization_id,
        aggregated_results.get("file_results", []),
    )

    # Update aggregated results with wall-clock time
    original_time = aggregated_results.get("total_execution_time", 0)
    if wall_clock_time != original_time:
        logger.info(
            f"FIXED: Wall-clock execution time: {wall_clock_time:.2f}s (was: {original_time:.2f}s summed)"
        )
        aggregated_results["total_execution_time"] = wall_clock_time

    # Debug logging for execution time calculation
    if wall_clock_time == 0:
        logger.warning(f"Execution time is 0! File results for execution {execution_id}")

    # Step 3: Get expected file count from workflow execution details for timeout detection
    expected_files = 0
    try:
        execution_response = api_client.get_workflow_execution(
            execution_id, file_execution=False
        )
        if execution_response.success:
            execution_data = execution_response.data
            expected_files = execution_data.get("total_files", 0)
            logger.info(
                f"Expected files from execution details: {expected_files} for execution {execution_id}"
            )
        else:
            logger.warning(
                f"Could not fetch execution details for {execution_id}: {execution_response.error}"
            )
    except Exception as e:
        logger.warning(f"Could not fetch execution details for {execution_id}: {e}")

    # Step 4: Extract file processing metrics for status determination
    total_files_processed = aggregated_results.get("total_files_processed", 0)
    failed_files = aggregated_results.get("failed_files", 0)
    total_files = aggregated_results.get("total_files", 0)
    successful_files = aggregated_results.get("successful_files", 0)

    # Step 5: Unified status determination with timeout failure detection

    # Detect timeout failures: expected files but processed none (likely SoftTimeLimitExceeded)
    has_timeout_failure = (
        total_files == 0 and total_files_processed == 0 and expected_files > 0
    )

    if has_timeout_failure:
        # Timeout or complete failure - mark as ERROR
        final_status = ExecutionStatus.ERROR.value
        logger.error(
            f"Execution {execution_id} failed - expected {expected_files} files "
            f"but processed 0 (likely timeout/failure)"
        )
    elif failed_files > 0 and failed_files == total_files:
        # ALL processed files failed - mark as ERROR
        final_status = ExecutionStatus.ERROR.value
        logger.error(f"Execution {execution_id} failed - all {total_files} files failed")
    else:
        # Some or all files succeeded, or legitimate empty batch - mark as COMPLETED
        final_status = ExecutionStatus.COMPLETED.value
        if failed_files > 0:
            logger.warning(
                f"Execution {execution_id} completed with {failed_files} failed files out of {total_files} total"
            )
        elif total_files == 0 and expected_files == 0:
            logger.info(
                f"Execution {execution_id} completed - legitimate empty batch (no files to process)"
            )
        else:
            logger.info(
                f"Execution {execution_id} completed successfully - {successful_files} files processed"
            )

    return aggregated_results, final_status, expected_files


def _update_execution_status_unified(
    api_client: InternalAPIClient,
    execution_id: str,
    final_status: str,
    aggregated_results: dict[str, Any],
    organization_id: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Unified workflow execution status update for all callback types.

    This function provides consistent workflow execution status updates across
    all callback tasks with proper error handling and result structure.

    Args:
        api_client: Internal API client for making the update call
        execution_id: Workflow execution ID
        final_status: Final execution status (COMPLETED, ERROR, etc.)
        aggregated_results: Aggregated file processing results
        organization_id: Organization context
        error_message: Optional error message for failed executions

    Returns:
        Execution update result dictionary
    """
    try:
        # Consistent workflow execution status update across all callback types
        total_files = aggregated_results.get("total_files", 0)

        # Make the unified API call
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=final_status,
            total_files=total_files,
            organization_id=organization_id,
            error_message=error_message,
        )

        # Return consistent result structure
        update_result = {
            "status": "completed",
            "method": "unified_execution_update",
            "message": f"Execution status updated to {final_status}",
            "execution_id": execution_id,
            "final_status": final_status,
            "total_files": total_files,
            "organization_id": organization_id,
        }

        logger.info(
            f"Successfully updated execution {execution_id} status to {final_status}"
        )
        return update_result

    except Exception as e:
        logger.error(
            f"Failed to update execution status for {execution_id}: {e}", exc_info=True
        )
        # Return error result instead of re-raising to maintain callback flow
        return {
            "status": "failed",
            "method": "unified_execution_update",
            "error": str(e),
            "execution_id": execution_id,
            "final_status": final_status,
            "organization_id": organization_id,
        }


def _handle_pipeline_updates_unified(
    context: CallbackContext, final_status: str, is_api_deployment: bool = False
) -> dict[str, Any]:
    """Unified pipeline status handling for all callback types.

    This function handles the difference between API deployments (which skip pipeline
    updates) and ETL/TASK/APP workflows (which require pipeline status updates).

    Args:
        context: Callback context with pipeline details
        final_status: Final execution status to map to pipeline status
        is_api_deployment: Whether this is an API deployment (skips pipeline updates)

    Returns:
        Pipeline update result dictionary
    """
    if is_api_deployment:
        # API deployments use APIDeployment model, not Pipeline model
        # Pipeline status updates don't apply and would cause 404 errors
        logger.info(
            f"OPTIMIZATION: Skipping pipeline status update for API deployment {context.pipeline_id} "
            f"(no Pipeline record exists)"
        )
        return {
            "status": "skipped",
            "reason": "api_deployment",
            "message": "Pipeline update skipped for API deployment",
            "pipeline_id": context.pipeline_id,
        }

    # Non-API workflows (ETL/TASK/APP) need pipeline status updates
    if not context.pipeline_id:
        logger.info("No pipeline_id provided - skipping pipeline status update")
        return {
            "status": "skipped",
            "reason": "no_pipeline_id",
            "message": "No pipeline_id available for update",
        }

    try:
        # Validate pipeline_id is a proper UUID
        import uuid

        uuid.UUID(str(context.pipeline_id))
    except ValueError:
        # Invalid UUID - likely execution_log_id from worker-based execution
        logger.info(
            f"WORKERS FLOW: Skipping pipeline status update - pipeline_id '{context.pipeline_id}' "
            f"is not a valid UUID (likely execution_log_id from worker-based execution)"
        )
        return {
            "status": "skipped",
            "reason": "invalid_uuid",
            "message": "Pipeline ID is not a valid UUID",
            "pipeline_id": context.pipeline_id,
        }

    # Perform pipeline status update for ETL/TASK/APP workflows
    try:
        logger.info(
            f"Updating pipeline {context.pipeline_id} status with organization_id: {context.organization_id}"
        )

        # Map execution status to pipeline status
        pipeline_status = _map_execution_status_to_pipeline_status(final_status)

        # Use direct pipeline update
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
            return {
                "status": "completed",
                "pipeline_status": pipeline_status,
                "pipeline_id": context.pipeline_id,
                "message": f"Pipeline status updated to {pipeline_status}",
            }
        else:
            logger.warning(
                f"Failed to update pipeline for {context.pipeline_id} - "
                f"pipeline_status={pipeline_status}, pipeline_name={context.pipeline_name}"
            )
            return {
                "status": "failed",
                "pipeline_status": pipeline_status,
                "pipeline_id": context.pipeline_id,
                "message": "Pipeline update call failed",
            }

    except CircuitBreakerOpenError:
        logger.warning("Pipeline status update circuit breaker open - skipping update")
        return {
            "status": "skipped",
            "reason": "circuit_breaker_open",
            "message": "Circuit breaker prevented pipeline update",
            "pipeline_id": context.pipeline_id,
        }
    except Exception as e:
        # Handle pipeline not found errors gracefully
        if "404" in str(e) or "Pipeline not found" in str(e) or NOT_FOUND_MSG in str(e):
            logger.info(
                f"Pipeline {context.pipeline_id} not found - likely using stale reference, skipping update"
            )
            return {
                "status": "skipped",
                "reason": "pipeline_not_found",
                "message": "Pipeline not found (stale reference)",
                "pipeline_id": context.pipeline_id,
            }
        else:
            logger.warning(f"Failed to update pipeline status: {str(e)}")
            return {
                "status": "failed",
                "error": str(e),
                "pipeline_id": context.pipeline_id,
                "message": "Pipeline update failed with error",
            }


def _handle_notifications_unified(
    api_client: InternalAPIClient,
    status: str,
    organization_id: str,
    execution_id: str,
    pipeline_id: str | None = None,
    workflow_id: str | None = None,
    pipeline_name: str | None = None,
    pipeline_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Unified notification handling for all callback types.

    Args:
        api_client: Internal API client for notification calls
        execution_id: Workflow execution ID
        status: Execution status
        pipeline_id: Pipeline or API deployment ID
        workflow_id: Workflow ID (fallback if pipeline_id is None)
        organization_id: Organization context
        pipeline_name: Pipeline/API deployment name
        pipeline_type: Pipeline/API deployment type
        error_message: Error message (if any)

    Returns:
        Notification result dictionary
    """
    try:
        if not pipeline_id:
            logger.warning("No pipeline_id provided - skipping notifications")
            return {
                "status": "skipped",
                "reason": "no_pipeline_id",
                "message": "No pipeline_id available for notifications",
            }

        logger.info(
            f"Triggering notifications for target_id={pipeline_id} (execution completed)"
        )

        # Ensure organization context is set for notification requests
        api_client.set_organization_context(organization_id)

        handle_status_notifications(
            api_client=api_client,
            pipeline_id=pipeline_id,
            status=status,
            execution_id=execution_id,
            error_message=error_message,
            pipeline_name=pipeline_name,
            pipeline_type=pipeline_type,
            organization_id=organization_id,
        )

        return {
            "status": "completed",
            "target_id": pipeline_id,
            "message": "Notifications sent successfully",
        }

    except Exception as notif_error:
        logger.warning(f"Failed to trigger completion notifications: {notif_error}")
        return {
            "status": "failed",
            "error": str(notif_error),
            "message": "Notification delivery failed",
        }


def _fetch_pipeline_name_from_api(
    pipeline_id: str,
    api_client: InternalAPIClient,
) -> str | None:
    """Fetch actual pipeline name from Pipeline/APIDeployment models.

    Args:
        pipeline_id: Pipeline or API deployment ID
        api_client: API client instance

    Returns:
        Pipeline name from API, or None if fetch failed
    """
    try:
        from shared.models.pipeline_models import PipelineApiResponse

        logger.info(
            f"Fetching pipeline data for pipeline_id={pipeline_id} to get correct pipeline name"
        )
        pipeline_response = api_client.get_pipeline_data(
            pipeline_id=pipeline_id, check_active=False
        )

        if pipeline_response.success:
            # Parse response using type-safe dataclass
            pipeline_api_data = PipelineApiResponse.from_dict(pipeline_response.data)
            pipeline_name = pipeline_api_data.pipeline.pipeline_name

            logger.info(
                f"Fetched pipeline name from API: '{pipeline_name}' for pipeline_id={pipeline_id}"
            )
            return pipeline_name
        else:
            logger.warning(
                f"Could not fetch pipeline data for {pipeline_id}: {pipeline_response.error}"
            )
            return None
    except Exception:
        logger.exception(
            f"Error fetching pipeline name for {pipeline_id}."
            f"Will use 'Unknown API' or 'Unknown Pipeline' in notifications."
        )
        return None


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

    # 2. Check if organization_id is available in kwargs (fast path)
    try:
        org_id_from_kwargs = kwargs.get("organization_id")

        if org_id_from_kwargs:
            # Fast path: Create organization-scoped API client immediately
            logger.info(f"Using organization ID from kwargs: {org_id_from_kwargs}")
            api_client = create_api_client(org_id_from_kwargs)

            logger.info(
                f"Fetching complete context from workflow execution {context.execution_id}"
            )

            execution_response = api_client.get_workflow_execution(
                context.execution_id, file_execution=False
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
            context.file_executions = execution_data.get("file_executions", [])

            # 3. Extract parameters with kwargs as fast path, execution data as fallback
            context.pipeline_id = kwargs.get("pipeline_id") or execution_info.get(
                "pipeline_id"
            )
            context.organization_id = org_id_from_kwargs  # Use from kwargs
        else:
            # Fallback path: Need to fetch execution data first to get organization context
            logger.info(
                f"Organization ID not in kwargs, fetching from workflow execution {context.execution_id}"
            )

            # Create temporary API client for initial execution fetch (no org context needed)
            from shared.infrastructure.config import WorkerConfig

            temp_config = WorkerConfig()
            temp_api_client = InternalAPIClient(temp_config)
            try:
                execution_response = temp_api_client.get_workflow_execution(
                    context.execution_id,
                    file_execution=False,
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
                context.file_executions = execution_data.get("file_executions", [])

                # Extract organization ID from execution data
                context.organization_id = organization_context.get(
                    "organization_id"
                ) or workflow_definition.get("organization_id")

                if not context.organization_id:
                    raise ValueError(
                        "Could not determine organization_id from execution context"
                    )

                # Now create the proper organization-scoped API client
                api_client = create_api_client(context.organization_id)

                # Extract other parameters
                context.pipeline_id = kwargs.get("pipeline_id") or execution_info.get(
                    "pipeline_id"
                )
            finally:
                # Clean up temporary client
                if hasattr(temp_api_client, "close"):
                    temp_api_client.close()

        # Common processing for both paths - variables are available in both scopes
        # Always populate workflow_id from correct nested path
        context.workflow_id = execution_info.get(
            "workflow_id"
        ) or workflow_definition.get("workflow_id")

        # Use existing API detection from source_config (no additional API calls needed)
        is_api_deployment = source_config.get("is_api", False)

        # Fetch actual pipeline name from Pipeline/APIDeployment models
        pipeline_name_from_api = None
        if context.pipeline_id:
            pipeline_name_from_api = _fetch_pipeline_name_from_api(
                context.pipeline_id, api_client
            )

        if is_api_deployment:
            # This is an API deployment
            # Use fetched pipeline name if available, otherwise use "Unknown API"
            resolved_pipeline_name = pipeline_name_from_api or "Unknown API"
            context.pipeline_data = {
                "is_api": True,
                "resolved_pipeline_type": "API",
                "resolved_pipeline_name": resolved_pipeline_name,
            }
            context.pipeline_type = "API"
            context.pipeline_name = resolved_pipeline_name
            logger.info(
                f"Detected API deployment from source_config: {context.pipeline_id}, pipeline_name='{resolved_pipeline_name}'"
            )
        else:
            # This is ETL/TASK/APP workflow
            # Use fetched pipeline name if available, otherwise use "Unknown Pipeline"
            resolved_pipeline_name = pipeline_name_from_api or "Unknown Pipeline"
            context.pipeline_data = {
                "is_api": False,
                "resolved_pipeline_type": "ETL",
                "resolved_pipeline_name": resolved_pipeline_name,
            }
            context.pipeline_type = "ETL"
            context.pipeline_name = resolved_pipeline_name
            logger.info(
                f"Detected ETL workflow from source_config: {context.pipeline_id}, pipeline_name='{resolved_pipeline_name}'"
            )

        logger.info(
            f"Extracted from kwargs: pipeline_id={kwargs.get('pipeline_id')}, org_id={kwargs.get('organization_id')}"
        )
        logger.info(
            f"Extracted from execution: workflow_id={context.workflow_id}, "
            f"is_api={is_api_deployment}, pipeline_type={context.pipeline_type} "
            f"file_executions={len(context.file_executions)}"
        )

    except Exception as e:
        logger.exception("Failed to fetch workflow execution context")
        raise ValueError(f"Could not get execution context: {e}")

    # 4. Validate required context is now available
    if not context.organization_id:
        raise ValueError("organization_id could not be determined from execution context")

    # 5. Assign the already-created organization-scoped API client to context
    context.api_client = api_client

    logger.info(
        f"✅ Extracted complete callback context: execution={context.execution_id}, "
        f"pipeline={context.pipeline_id}, workflow={context.workflow_id}, org={context.organization_id}, "
        f"api_client=initialized, pipeline_data=✓, type={context.pipeline_type}"
    )

    return context


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
                logger.exception(
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
        logger.exception(f"Directory cleanup failed for {cleanup_type}")
        return _create_cleanup_result(cleanup_type=cleanup_type, status="failed", error=e)


def _get_execution_directories(context: CallbackContext) -> list[tuple[str, any, str]]:
    """Determine execution directories to clean, supporting both API and workflow directories for API executions.

    Args:
        context: Callback context with execution details

    Returns:
        List of tuples (directory_path, storage_type, cleanup_type) to clean

    Raises:
        ValueError: If execution type cannot be determined
    """
    from unstract.filesystem import FileStorageType
    from unstract.workflow_execution.execution_file_handler import ExecutionFileHandler

    # Determine if this is an API or workflow execution
    is_api_execution = context.pipeline_data and context.pipeline_data.get(
        "is_api", False
    )

    directories_to_clean = []

    if is_api_execution and context.pipeline_id and context.workflow_id:
        # API execution - clean BOTH API execution directory AND workflow execution directory

        # 1. API execution directory
        try:
            api_execution_dir = ExecutionFileHandler.get_api_execution_dir(
                workflow_id=context.workflow_id,
                execution_id=context.execution_id,
                organization_id=context.organization_id,
            )
            directories_to_clean.append((api_execution_dir, FileStorageType.API, "api"))
            logger.info(f"Added API execution directory for cleanup: {api_execution_dir}")
        except Exception as e:
            logger.warning(f"Could not get API execution directory: {e}")

        # 2. Workflow execution directory (files may exist here too for API executions)
        try:
            file_handler = ExecutionFileHandler(
                workflow_id=context.workflow_id,
                execution_id=context.execution_id,
                organization_id=context.organization_id,
            )
            workflow_execution_dir = file_handler.execution_dir
            directories_to_clean.append(
                (workflow_execution_dir, FileStorageType.WORKFLOW_EXECUTION, "workflow")
            )
            logger.info(
                f"Added workflow execution directory for cleanup: {workflow_execution_dir}"
            )
        except Exception as e:
            logger.warning(f"Could not get workflow execution directory: {e}")

    elif context.workflow_id:
        # Non-API workflow execution - clean only workflow execution directory
        try:
            file_handler = ExecutionFileHandler(
                workflow_id=context.workflow_id,
                execution_id=context.execution_id,
                organization_id=context.organization_id,
            )
            execution_dir = file_handler.execution_dir
            directories_to_clean.append(
                (execution_dir, FileStorageType.WORKFLOW_EXECUTION, "workflow")
            )
            logger.info(
                f"Added workflow execution directory for cleanup: {execution_dir}"
            )
        except Exception as e:
            logger.warning(f"Could not get workflow execution directory: {e}")

    else:
        raise ValueError(
            f"Cannot determine execution type: is_api={is_api_execution}, "
            f"workflow_id={context.workflow_id}, pipeline_id={context.pipeline_id}"
        )

    if not directories_to_clean:
        raise ValueError("No directories could be determined for cleanup")

    return directories_to_clean


def _cleanup_execution_directory(context: CallbackContext) -> dict[str, Any]:
    """Clean up execution directories with enhanced logic for API executions.

    For API executions: Cleans both API execution directory AND workflow execution directory
    For non-API executions: Cleans only workflow execution directory

    Args:
        context: Callback context with execution details

    Returns:
        Directory cleanup result dictionary with details for each directory cleaned
    """
    try:
        # Get all directories to clean (multiple for API executions)
        directories_to_clean = _get_execution_directories(context)

        logger.info(
            f"🧹 Starting directory cleanup for execution {context.execution_id} "
            f"({len(directories_to_clean)} directories to clean)"
        )

        cleanup_results = []
        total_files_deleted = 0
        successful_cleanups = 0
        failed_cleanups = 0

        # Clean each directory
        for directory_path, storage_type, cleanup_type in directories_to_clean:
            try:
                logger.info(f"🧹 Cleaning {cleanup_type} directory: {directory_path}")

                # Setup file system for this directory type
                file_storage = _setup_file_system(storage_type)

                # Perform cleanup for this directory
                cleanup_result = _cleanup_directory(
                    file_storage, directory_path, cleanup_type
                )
                cleanup_results.append(cleanup_result)

                # Track statistics
                if cleanup_result.get("status") == "success":
                    successful_cleanups += 1
                    total_files_deleted += cleanup_result.get("files_deleted", 0)
                else:
                    if cleanup_result.get("status") == "failed":
                        failed_cleanups += 1

            except Exception as dir_error:
                logger.error(
                    f"Failed to clean {cleanup_type} directory {directory_path}: {dir_error}"
                )
                cleanup_results.append(
                    _create_cleanup_result(
                        cleanup_type=cleanup_type,
                        status="failed",
                        error=dir_error,
                        failed_paths=[directory_path],
                    )
                )
                failed_cleanups += 1

        # Determine overall status
        if successful_cleanups > 0 and failed_cleanups == 0:
            overall_status = "success"
        elif successful_cleanups > 0 and failed_cleanups > 0:
            overall_status = "partial"
        elif successful_cleanups == 0 and failed_cleanups > 0:
            overall_status = "failed"
        else:
            overall_status = "skipped"  # All directories were skipped (not found)

        # Create comprehensive result
        return {
            "status": overall_status,
            "directories_processed": len(directories_to_clean),
            "successful_cleanups": successful_cleanups,
            "failed_cleanups": failed_cleanups,
            "total_files_deleted": total_files_deleted,
            "cleanup_details": cleanup_results,
            "message": f"Cleaned {successful_cleanups}/{len(directories_to_clean)} directories, {total_files_deleted} files deleted",
        }

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


def _track_subscription_usage_if_available(
    context: CallbackContext,
    execution_status: str,
) -> dict[str, Any] | None:
    """Track subscription usage for successful file executions if plugin available.

    This is a non-blocking operation - errors are logged but do not fail the workflow.
    Only tracks usage for completed workflows with successful file executions.

    Args:
        context: Callback execution context with organization and execution IDs
        execution_status: Final execution status (should be COMPLETED for tracking)

    Returns:
        dict with status, committed_count, message if tracking attempted
        None if plugin not available or workflow not completed
    """
    # Only track for completed workflows
    if execution_status != ExecutionStatus.COMPLETED.value:
        logger.debug(
            f"Skipping subscription tracking for execution {context.execution_id} "
            f"with status {execution_status}"
        )
        return None

    try:
        # Try to get subscription_usage client plugin
        from client_plugin_registry import get_client_plugin

        subscription_plugin = get_client_plugin("subscription_usage")

        if not subscription_plugin:
            logger.debug(
                f"Subscription usage plugin not found for execution {context.execution_id} (OSS mode)"
            )
            return None

        # Extract successful file execution IDs directly from context.file_executions
        # Status in database is "COMPLETED" for successful executions
        successful_file_exec_ids = [
            file_exec.get("id")
            for file_exec in context.file_executions
            if isinstance(file_exec, dict)
            and file_exec.get("status") == "COMPLETED"
            and file_exec.get("id")
            and not file_exec.get("execution_error")
        ]

        if not successful_file_exec_ids:
            logger.debug(
                f"No successful file executions to track for execution {context.execution_id}"
            )
            return {
                "status": "skipped",
                "committed_count": 0,
                "message": "No successful file executions",
            }

        logger.info(
            f"Committing subscription usage for {len(successful_file_exec_ids)} "
            f"successful file executions in execution {context.execution_id}"
        )

        subscription_tracking_result = (
            subscription_plugin.commit_batch_subscription_usage(
                organization_id=context.organization_id,
                file_execution_ids=successful_file_exec_ids,
            )
        )

        logger.info(
            f"Subscription usage committed: "
            f"{subscription_tracking_result.get('committed_count', 0)}/{len(successful_file_exec_ids)} "
            f"file executions (status: {subscription_tracking_result.get('status')})"
        )

        return subscription_tracking_result

    except Exception as tracking_error:
        logger.error(
            "Failed to commit subscription usage for execution "
            f"{context.execution_id} (continuing execution): {tracking_error}",
            exc_info=True,
        )
        return {
            "status": "error",
            "committed_count": 0,
            "error": str(tracking_error),
        }


def _process_batch_callback_core(
    task_instance, results, *args, **kwargs
) -> dict[str, Any]:
    """Unified callback processing using shared helper functions.

    Uses the same unified functions as API callbacks to eliminate code duplication
    and ensure consistent timeout detection logic across all callback types.

    Args:
        task_instance: The Celery task instance (self)
        results (list): List of results from each batch
        **kwargs: Additional arguments including execution_id, pipeline_id, organization_id

    Returns:
        Callback processing result with unified execution flow
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
            # Use unified status determination with timeout detection (shared with API callback)
            aggregated_results, execution_status, expected_files = (
                _determine_execution_status_unified(
                    file_batch_results=results,
                    api_client=context.api_client,
                    execution_id=context.execution_id,
                    organization_id=context.organization_id,
                )
            )
            # Update workflow execution status using unified function
            execution_update_result = _update_execution_status_unified(
                api_client=context.api_client,
                execution_id=context.execution_id,
                final_status=execution_status,
                aggregated_results=aggregated_results,
                organization_id=context.organization_id,
                error_message=None,
            )
            # Handle pipeline updates using unified function (non-API deployment)
            pipeline_result = _handle_pipeline_updates_unified(
                context, execution_status, is_api_deployment=False
            )

            # Track subscription usage if plugin is present
            subscription_tracking_result = _track_subscription_usage_if_available(
                context=context,
                execution_status=execution_status,
            )

            # Add missing UI logs for cost and final workflow status (matching backend behavior)
            _publish_final_workflow_ui_logs(
                context=context,
                aggregated_results=aggregated_results,
                execution_status=execution_status,
            )

            # Handle resource cleanup using existing function
            cleanup_result = _cleanup_execution_resources(context)
            callback_result = {
                "status": "completed",
                "execution_id": context.execution_id,
                "workflow_id": context.workflow_id,
                "task_id": context.task_id,
                "aggregated_results": aggregated_results,
                "execution_status": execution_status,
                "expected_files": expected_files,
                "execution_update_result": execution_update_result,
                "pipeline_result": pipeline_result,
                "subscription_tracking_result": subscription_tracking_result,
                "cleanup_result": cleanup_result,
                "pipeline_id": context.pipeline_id,
                "unified_callback": True,
                "shared_timeout_detection": True,
            }

            logger.info(
                f"Completed unified callback processing for execution {context.execution_id} "
                f"with status {execution_status}"
            )
            # Handle notifications using unified function (non-critical)
            try:
                notification_result = _handle_notifications_unified(
                    api_client=context.api_client,
                    status=execution_status,
                    organization_id=context.organization_id,
                    execution_id=context.execution_id,
                    pipeline_id=context.pipeline_id,
                    workflow_id=context.workflow_id,
                    pipeline_name=context.pipeline_name,
                    pipeline_type=context.pipeline_type,
                    error_message=None,
                )
                callback_result["notification_result"] = notification_result
            except Exception as notif_error:
                logger.warning(f"Failed to handle notifications: {notif_error}")
                callback_result["notification_result"] = {
                    "status": "failed",
                    "error": str(notif_error),
                }

            return callback_result

        except Exception as e:
            logger.error(
                f"Unified batch callback processing failed for execution {context.execution_id}: {e}"
            )

            # Try to mark execution as failed using unified function
            try:
                _update_execution_status_unified(
                    context.api_client,
                    context.execution_id,
                    ExecutionStatus.ERROR.value,
                    {"error": str(e)[:500]},
                    context.organization_id,
                    error_message=str(e)[:500],
                )
                logger.info(
                    f"Marked execution {context.execution_id} as failed using unified function"
                )
            except Exception as cleanup_error:
                logger.error(f"Failed to mark execution as failed: {cleanup_error}")

            # Re-raise for Celery retry mechanism
            raise


@app.task(
    bind=True,
    name=TaskName.PROCESS_BATCH_CALLBACK,
    max_retries=0,  # Match Django backend pattern
    ignore_result=False,  # Match Django backend pattern
    # Timeout inherited from global Celery config (CALLBACK_TASK_TIME_LIMIT env var)
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
    # Timeout inherited from global Celery config (CALLBACK_TASK_TIME_LIMIT env var)
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
    # Create organization-scoped API client using factory pattern
    if not organization_id:
        raise ValueError("organization_id is required for API callback")

    api_client = create_api_client(organization_id)
    logger.info(f"Created organization-scoped API client: {organization_id}")

    execution_response = api_client.get_workflow_execution(
        execution_id, file_execution=False
    )
    if not execution_response.success:
        raise Exception(f"Failed to get execution context: {execution_response.error}")
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
            # Create organization-scoped API client using factory pattern
            api_client = create_api_client(schema_name)

            # Get pipeline name and type (simplified approach)
            if not pipeline_id:
                error_msg = f"No pipeline_id provided for API callback. execution_id={execution_id}, workflow_id={workflow_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Use simplified pipeline data fetching
            pipeline_name, pipeline_type = _fetch_pipeline_data_simplified(
                pipeline_id, schema_name, api_client, is_api_deployment=True
            )

            if pipeline_name:
                logger.info(
                    f"✅ Found pipeline: name='{pipeline_name}', type='{pipeline_type}'"
                )
            else:
                logger.warning(f"Could not fetch pipeline data for {pipeline_id}")
                pipeline_name = "Unknown API"
                pipeline_type = PipelineType.API.value

            # Use unified status determination with timeout detection
            aggregated_results, execution_status, expected_files = (
                _determine_execution_status_unified(
                    file_batch_results=file_batch_results,
                    api_client=api_client,
                    execution_id=execution_id,
                    organization_id=organization_id,
                )
            )

            # Update workflow execution status using unified function
            execution_update_result = _update_execution_status_unified(
                api_client=api_client,
                execution_id=execution_id,
                final_status=execution_status,
                aggregated_results=aggregated_results,
                organization_id=organization_id,
            )

            # Create minimal context for unified pipeline handling
            context = CallbackContext()
            context.pipeline_id = pipeline_id
            context.execution_id = execution_id
            context.organization_id = organization_id
            context.workflow_id = workflow_id
            context.pipeline_name = pipeline_name
            context.pipeline_type = pipeline_type
            context.api_client = api_client
            context.file_executions = execution_context.get("file_executions", [])

            # Add missing UI logs for cost and final workflow status (matching backend behavior)
            _publish_final_workflow_ui_logs_api(
                context=context,
                aggregated_results=aggregated_results,
                execution_status=execution_status,
            )

            # Handle pipeline updates (skip for API deployments)
            pipeline_result = _handle_pipeline_updates_unified(
                context=context, final_status=execution_status, is_api_deployment=True
            )

            # Track subscription usage if plugin is present
            subscription_tracking_result = _track_subscription_usage_if_available(
                context=context,
                execution_status=execution_status,
            )

            # Handle notifications using unified function
            notification_result = _handle_notifications_unified(
                api_client=api_client,
                status=execution_status,
                organization_id=organization_id,
                execution_id=execution_id,
                pipeline_id=pipeline_id,
                workflow_id=workflow_id,
                pipeline_name=pipeline_name,
                pipeline_type=pipeline_type,
                error_message=None,
            )

            callback_result = {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "pipeline_id": pipeline_id,
                "status": "completed",
                "total_files_processed": aggregated_results.get(
                    "total_files_processed", 0
                ),
                "total_execution_time": aggregated_results.get("total_execution_time", 0),
                "batches_processed": len(file_batch_results),
                "task_id": task_id,
                "expected_files": expected_files,  # Include expected files for debugging
                "execution_update": execution_update_result,
                "pipeline_update": pipeline_result,
                "notifications": notification_result,
                "subscription_tracking_result": subscription_tracking_result,
                "optimization": {
                    "method": "unified_callback_functions",
                    "eliminated_code_duplication": True,
                    "shared_timeout_detection": True,
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
                # Create organization-scoped API client for error handling
                api_client = create_api_client(schema_name)
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


def _publish_final_workflow_ui_logs(
    context: "CallbackContext",
    aggregated_results: dict[str, Any],
    execution_status: str,
) -> None:
    """Publish final workflow UI logs for cost and execution summary.

    This matches the backend's file_execution_tasks.py:361-371 behavior to provide
    consistent UI feedback for workflow completion including cost tracking.

    Args:
        context: Callback context with execution details
        aggregated_results: Aggregated file processing results
        execution_status: Final execution status
    """
    try:
        # Extract file statistics from aggregated results
        total_files = aggregated_results.get("total_files", 0)
        successful_files = aggregated_results.get("successful_files", 0)
        failed_files = aggregated_results.get("failed_files", 0)

        # Get execution data to extract cost information (with cost calculation)
        execution_response = context.api_client.get_workflow_execution(
            context.execution_id, include_cost=True, file_execution=False
        )
        if not execution_response.success:
            logger.warning(
                f"Could not get execution data for UI logging in {context.execution_id}: {execution_response.error}"
            )
            return

        # Cost data is at the top level of response when include_cost=True
        aggregated_usage_cost = execution_response.data.get("aggregated_usage_cost")

        # Create workflow logger for UI feedback
        # Use general workflow logger since this is called from general workflow callback
        workflow_logger = WorkerWorkflowLogger.create_for_general_workflow(
            execution_id=context.execution_id,
            organization_id=context.organization_id,
            pipeline_id=context.pipeline_id,
        )

        if workflow_logger:
            # Publish average cost log (matches backend file_execution_tasks.py:361-366)
            workflow_logger.publish_average_cost_log(
                worker_logger=logger,
                total_files=total_files,
                execution_id=context.execution_id,
                total_cost=aggregated_usage_cost,
            )

            # Publish final workflow logs (matches backend file_execution_tasks.py:367-371)
            workflow_logger.publish_final_workflow_logs(
                total_files=total_files,
                successful_files=successful_files,
                failed_files=failed_files,
            )

            logger.info(
                f"Published final UI logs for execution {context.execution_id}: "
                f"{total_files} total, {successful_files} successful, {failed_files} failed, "
                f"cost: ${aggregated_usage_cost}"
            )
        else:
            logger.warning(
                f"Could not create workflow logger for UI logging in {context.execution_id}"
            )

    except Exception as e:
        logger.error(
            f"Failed to publish final workflow UI logs for {context.execution_id}: {str(e)}"
        )


def _publish_final_workflow_ui_logs_api(
    context: "CallbackContext",
    aggregated_results: dict[str, Any],
    execution_status: str,
) -> None:
    """Publish final workflow UI logs for API workflow cost and execution summary.

    This matches the backend's file_execution_tasks.py:361-371 behavior to provide
    consistent UI feedback for API workflow completion including cost tracking.

    Args:
        context: Callback context with execution details
        aggregated_results: Aggregated file processing results
        execution_status: Final execution status
    """
    try:
        # Extract file statistics from aggregated results
        total_files = aggregated_results.get("total_files", 0)
        successful_files = aggregated_results.get("successful_files", 0)
        failed_files = aggregated_results.get("failed_files", 0)

        # Get execution data to extract cost information (with cost calculation)
        execution_response = context.api_client.get_workflow_execution(
            context.execution_id, include_cost=True, file_execution=False
        )
        if not execution_response.success:
            logger.warning(
                f"Could not get execution data for UI logging in API workflow {context.execution_id}: {execution_response.error}"
            )
            return

        # Cost data is at the top level of response when include_cost=True
        aggregated_usage_cost = execution_response.data.get("aggregated_usage_cost")

        # Create workflow logger for UI feedback
        # Use API workflow logger since this is called from API workflow callback
        workflow_logger = WorkerWorkflowLogger.create_for_api_workflow(
            execution_id=context.execution_id,
            organization_id=context.organization_id,
            pipeline_id=context.pipeline_id,
        )

        if workflow_logger:
            # Publish average cost log (matches backend file_execution_tasks.py:361-366)
            workflow_logger.publish_average_cost_log(
                worker_logger=logger,
                total_files=total_files,
                execution_id=context.execution_id,
                total_cost=aggregated_usage_cost,
            )

            # Publish final workflow logs (matches backend file_execution_tasks.py:367-371)
            workflow_logger.publish_final_workflow_logs(
                total_files=total_files,
                successful_files=successful_files,
                failed_files=failed_files,
            )

            logger.info(
                f"Published final UI logs for API workflow {context.execution_id}: "
                f"{total_files} total, {successful_files} successful, {failed_files} failed, "
                f"cost: ${aggregated_usage_cost}"
            )
        else:
            logger.warning(
                f"Could not create API workflow logger for UI logging in {context.execution_id}"
            )

    except Exception as e:
        logger.error(
            f"Failed to publish final workflow UI logs for API workflow {context.execution_id}: {str(e)}"
        )


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
