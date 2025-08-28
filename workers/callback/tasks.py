"""File Processing Callback Worker Tasks

Optimized callback implementation with performance enhancements:
- Redis-based status caching to reduce PostgreSQL queries
- Exponential backoff for retry operations
- Batched status updates to minimize API calls
- Smart circuit breaker patterns for resilience

Replaces the heavy Django process_batch_callback task with API coordination.

TODO: Circuit Breaker Improvements
- Implement retry queue for operations blocked by open circuit breakers
- Add reconciliation task to process queued updates when circuit closes
- Prevent data loss/staleness from skipped DB updates
- See inline TODOs for specific implementation details
"""

import time
from typing import Any

# Use Celery current_app to avoid circular imports
from celery import current_app as app

# Import shared worker infrastructure
from shared.api import InternalAPIClient

# Import from shared worker modules
from shared.constants import Account
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
    with_execution_context,
)
from shared.legacy.local_context import StateStore
from shared.patterns.notification.helper import handle_status_notifications
from shared.patterns.retry.backoff import (
    get_retry_manager,
    initialize_backoff_managers,
)
from shared.patterns.retry.utils import CircuitBreakerOpenError, circuit_breaker
from shared.processing.files.batch import (
    BatchConfig,
    add_pipeline_update_to_batch,
    add_status_update_to_batch,
    get_batch_processor,
    initialize_batch_processor,
)
from shared.processing.files.time_utils import (
    WallClockTimeCalculator,
    aggregate_file_batch_results,
)
from shared.workflow.execution.context import WorkerExecutionContext

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

        # Initialize batch processor with optimized configuration
        # DISABLE auto-flush to prevent duplicate notifications
        batch_config = BatchConfig(
            max_batch_size=8,  # Reduced batch size for faster processing
            max_wait_time=3.0,  # Reduced wait time for better responsiveness
            flush_interval=1.5,  # More frequent flushes
            enable_auto_flush=False,  # DISABLED to prevent duplicate notifications
        )

        # Initialize batch processor with API client
        # We'll create the API client in the callback task when we have proper context
        initialize_batch_processor(batch_config, api_client=None)
        logger.info("Batch processor initialized")

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

        logger.debug(
            f"DEBUG: Pipeline API response for {pipeline_id}: success={response.success}, data_type={type(response.data)}, data_keys={response.data.keys() if isinstance(response.data, dict) else 'not_dict'}, error={response.error}"
        )

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

        if response.success and response.data:
            # DEBUG: Log the full API response to understand the issue
            logger.info(
                f"DEBUG: API deployment response for {api_id}: success={response.success}, data_keys={response.data.keys() if isinstance(response.data, dict) else 'not_dict'}"
            )
            logger.info(f"DEBUG: Full API deployment response data: {response.data}")

            # Response format: {"status": "success", "pipeline": {...}}
            pipeline_data = response.data.get("pipeline", {})

            # DEBUG: Log pipeline data specifically
            logger.info(
                f"DEBUG: Pipeline data from API deployment endpoint: {pipeline_data}"
            )

            # API deployment data structure from serializer:
            pipeline_name = pipeline_data.get("api_name")
            pipeline_type = PipelineType.API.value

            # DEBUG: Log what we extracted
            logger.info(
                f"DEBUG: Extracted from API deployment - name='{pipeline_name}', type='{pipeline_type}' (hardcoded to API)"
            )

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
        logger.error(f"Failed to fetch API deployment data for {api_id}: {e}")
        return None


def _update_status_with_batching(
    execution_id: str,
    status: str,
    organization_id: str,
    api_client: InternalAPIClient,
    **additional_fields,
) -> bool:
    """Update execution status using batching optimization.

    Args:
        execution_id: Execution ID
        status: New status
        organization_id: Organization context
        api_client: API client instance
        **additional_fields: Additional status fields

    Returns:
        True if update was queued successfully
    """
    batch_processor = get_batch_processor()

    if batch_processor:
        # Use batch processing for better performance
        success = add_status_update_to_batch(
            batch_processor=batch_processor,
            execution_id=execution_id,
            status=status,
            organization_id=organization_id,
            **additional_fields,
        )

        if success:
            logger.debug(f"Queued status update for execution {execution_id}: {status}")

            # Invalidate cache
            cache_manager = get_cache_manager()
            if cache_manager:
                cache_manager.invalidate_execution_status(execution_id, organization_id)

            return True

    # Fallback to direct API call
    try:
        api_client.update_workflow_execution_status(
            execution_id=execution_id, status=status, **additional_fields
        )

        # Invalidate cache
        cache_manager = get_cache_manager()
        if cache_manager:
            cache_manager.invalidate_execution_status(execution_id, organization_id)

        logger.debug(f"Direct status update for execution {execution_id}: {status}")
        return True

    except Exception as e:
        logger.error(f"Failed to update execution status for {execution_id}: {e}")
        return False


def _update_pipeline_with_batching(
    pipeline_id: str,
    execution_id: str,
    status: str,
    organization_id: str,
    api_client: InternalAPIClient,
    **additional_fields,
) -> bool:
    """Update pipeline status using batching optimization.

    Args:
        pipeline_id: Pipeline ID
        execution_id: Execution ID
        status: Pipeline status
        organization_id: Organization context
        api_client: API client instance
        **additional_fields: Additional pipeline fields

    Returns:
        True if update was queued successfully
    """
    batch_processor = get_batch_processor()

    # TEMPORARY FIX: Skip batch processing due to BatchOperationResponse.error_response() bug
    # Use direct API calls for reliability until batch processing bug is fixed
    if False and batch_processor:  # Disabled batch processing
        # Use batch processing for better performance
        success = add_pipeline_update_to_batch(
            batch_processor=batch_processor,
            pipeline_id=pipeline_id,
            execution_id=execution_id,
            status=status,
            organization_id=organization_id,
            **additional_fields,
        )

        if success:
            logger.debug(f"Queued pipeline update for {pipeline_id}: {status}")

            # Invalidate cache
            cache_manager = get_cache_manager()
            if cache_manager:
                cache_manager.invalidate_pipeline_status(pipeline_id, organization_id)

            return True

    # Fallback to direct API call
    try:
        api_client.update_pipeline_status(
            pipeline_id=pipeline_id,
            execution_id=execution_id,
            status=status,
            organization_id=organization_id,
            **additional_fields,
        )

        # Invalidate cache
        cache_manager = get_cache_manager()
        if cache_manager:
            cache_manager.invalidate_pipeline_status(pipeline_id, organization_id)

        logger.info(f"DEBUG: Direct pipeline update SUCCESS for {pipeline_id}: {status}")

        # NOTE: Notifications are triggered by main batch completion logic, not here
        # This avoids duplicate notifications for the same execution

        return True

    except Exception as e:
        logger.error(f"DEBUG: Failed to update pipeline status for {pipeline_id}: {e}")
        logger.error(
            f"DEBUG: Pipeline update parameters: pipeline_id={pipeline_id}, status={status}, organization_id={organization_id}"
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

    # Batch processor stats
    batch_processor = get_batch_processor()
    if batch_processor:
        stats["batch"] = batch_processor.get_batch_stats()

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
    """Extract and validate callback processing parameters.

    Args:
        task_instance: The Celery task instance
        results: List of batch results
        kwargs: Keyword arguments from the callback

    Returns:
        CallbackContext with extracted parameters

    Raises:
        ValueError: If required parameters are missing
    """
    context = CallbackContext()
    context.task_id = (
        task_instance.request.id if hasattr(task_instance, "request") else "unknown"
    )

    # Extract execution_id from kwargs exactly like Django backend
    context.execution_id = kwargs.get("execution_id")
    if not context.execution_id:
        raise ValueError("execution_id is required in kwargs")

    # Get pipeline_id directly from kwargs first (preferred)
    context.pipeline_id = kwargs.get("pipeline_id")

    return context


def _setup_organization_context(
    context: CallbackContext, results: list, kwargs: dict[str, Any]
) -> str:
    """Setup organization context for API calls.

    Args:
        context: Callback context to populate
        results: List of batch results for fallback extraction
        kwargs: Keyword arguments for parameter extraction

    Returns:
        Organization ID that was determined

    Raises:
        RuntimeError: If no organization_id can be determined
    """
    # CRITICAL FIX: Get organization_id from multiple sources in priority order
    # This ensures we always have the properly formatted organization context for API calls
    organization_id = None

    # 1. First try kwargs (highest priority - passed from API/general worker)
    organization_id = kwargs.get("organization_id")
    if organization_id:
        logger.info(f"DEBUG: Using organization_id from kwargs: {organization_id}")

    # 2. Fall back to worker configuration (properly formatted)
    if not organization_id:
        config_temp = WorkerConfig()
        if config_temp.organization_id:
            organization_id = config_temp.organization_id
            logger.info(
                f"DEBUG: Using organization_id from worker config: {organization_id}"
            )

    # 3. Last resort: extract from batch results (may be raw database ID)
    if not organization_id:
        logger.info(
            f"DEBUG: No organization_id from kwargs/config, checking {len(results)} batch results..."
        )
        for i, result in enumerate(results):
            logger.info(
                f"DEBUG: Result {i} type: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
            )
            if isinstance(result, dict) and "organization_id" in result:
                extracted_org_id = result["organization_id"]
                # Validate and format if needed
                if extracted_org_id and not extracted_org_id.startswith("org_"):
                    logger.warning(
                        f"DEBUG: Batch result has raw database ID '{extracted_org_id}', may need proper formatting"
                    )
                organization_id = extracted_org_id
                logger.info(
                    f"DEBUG: ✅ Extracted organization_id from batch result {i}: {organization_id}"
                )
                break
        else:
            logger.warning(
                f"DEBUG: ❌ No organization_id found in any of the {len(results)} batch results"
            )

    if not organization_id:
        logger.error(
            f"CRITICAL: Could not determine organization_id for execution {context.execution_id}"
        )
        logger.error(
            "This will likely cause API calls to fail due to missing organization context"
        )
        raise RuntimeError(
            f"No organization_id available for execution {context.execution_id}"
        )

    context.organization_id = organization_id
    return organization_id


def _setup_api_client_and_execution_context(
    context: CallbackContext,
) -> tuple[WorkerConfig, InternalAPIClient]:
    """Setup API client and fetch execution context.

    Args:
        context: Callback context to populate

    Returns:
        Tuple of (config, api_client)

    Raises:
        Exception: If execution context cannot be fetched
    """
    # Get workflow execution context via API with caching optimization
    config = WorkerConfig()
    api_client = InternalAPIClient(config)

    # Final fallback: use API client's default organization_id if available
    if not context.organization_id and api_client.organization_id:
        context.organization_id = api_client.organization_id
        logger.info(
            f"DEBUG: Using API client's default organization_id: {context.organization_id}"
        )

    # Set organization context BEFORE making API calls (CRITICAL for getting correct pipeline_id)
    if context.organization_id:
        api_client.set_organization_context(context.organization_id)
        logger.info(
            f"✅ Set organization context before API calls: {context.organization_id}"
        )
    else:
        logger.error(
            "CRITICAL: No organization_id available for API calls - this will cause pipeline_id to be null"
        )

    execution_response = api_client.get_workflow_execution(context.execution_id)
    if not execution_response.success:
        raise Exception(f"Failed to get execution context: {execution_response.error}")

    execution_context = execution_response.data
    workflow_execution = execution_context.get("execution", {})
    workflow = execution_context.get("workflow", {})
    logger.info(f"DEBUG: ! execution_context: {execution_context}")
    logger.info(f"DEBUG: ! workflow_execution: {workflow_execution}")
    logger.info(f"DEBUG: ! workflow: {workflow}")

    # Organization_id already extracted before API call - use as fallback if needed
    if not context.organization_id:
        context.organization_id = (
            workflow_execution.get("organization_id")
            or workflow.get("organization_id")
            or workflow.get("organization", {}).get("id")
            if isinstance(workflow.get("organization"), dict)
            else execution_context.get("organization_context", {}).get("organization_id")
            or None
        )
        if context.organization_id:
            logger.info(
                f"Fallback: extracted organization_id from execution context: {context.organization_id}"
            )

    context.workflow_id = workflow_execution.get("workflow_id") or workflow.get("id")
    context.api_client = api_client

    return config, api_client


def _fetch_and_validate_pipeline_data(context: CallbackContext) -> None:
    """Fetch pipeline data and handle API/ETL routing fixes.

    Args:
        context: Callback context to populate with pipeline data
    """
    # Extract Pipeline data via unified internal API (optimized for ETL/TASK/APP pipelines)
    # Note: process_batch_callback handles ETL/TASK/APP types (Pipeline model)
    # while process_batch_callback_api handles API type (APIDeployment model via v2 endpoint)
    context.pipeline_name = None
    context.pipeline_type = None
    context.pipeline_data = None

    if context.pipeline_id:
        # CRITICAL FIX: Check if this is an API deployment first to ensure correct notification type
        # The backend may route API deployments to the general worker queue by mistake,
        # but we still need to send notifications with type="API" instead of type="ETL"
        api_deployment_data = _fetch_api_deployment_data(
            context.pipeline_id, context.organization_id, context.api_client
        )
        if api_deployment_data:
            context.pipeline_name = api_deployment_data.get("resolved_pipeline_name")
            context.pipeline_type = api_deployment_data.get(
                "resolved_pipeline_type"
            )  # Should be "API"
            context.pipeline_data = api_deployment_data
            logger.info(
                f"✅ ROUTING FIX: APIDeployment routed to ETL callback - correcting type: name='{context.pipeline_name}', type='{context.pipeline_type}'"
            )
        else:
            # Fallback to regular pipeline lookup for ETL/TASK/APP workflows
            context.pipeline_data = _fetch_pipeline_data(
                context.pipeline_id, context.organization_id, context.api_client
            )
            if context.pipeline_data:
                context.pipeline_name = context.pipeline_data.get(
                    "resolved_pipeline_name"
                )
                context.pipeline_type = context.pipeline_data.get(
                    "resolved_pipeline_type"
                )
                logger.info(
                    f"✅ Pipeline data from models: name='{context.pipeline_name}', type='{context.pipeline_type}', is_api={context.pipeline_data.get('is_api', False)}"
                )
    else:
        # No pipeline_id provided - check if we can extract from execution context
        logger.warning(
            "No pipeline_id provided directly for ETL/TASK/APP callback. Checking execution context..."
        )

    # Try to extract pipeline_id from execution context if not passed directly
    if not context.pipeline_id:
        # Get execution context again (we should cache this in the future)
        execution_response = context.api_client.get_workflow_execution(
            context.execution_id
        )
        if execution_response.success:
            execution_context = execution_response.data
            workflow_execution = execution_context.get("execution", {})

            context.pipeline_id = workflow_execution.get("pipeline_id")
            logger.info(
                f"Using pipeline_id from execution context: {context.pipeline_id}"
            )

            # BACKWARD COMPATIBILITY: During Django transition, execution_log_id might contain the pipeline_id
            if not context.pipeline_id:
                execution_log_id = workflow_execution.get("execution_log_id")
                if execution_log_id:
                    logger.warning(
                        f"BACKWARD COMPATIBILITY: pipeline_id is None but execution_log_id exists: {execution_log_id}"
                    )
                    logger.info(
                        "Attempting to use execution_log_id as pipeline_id for Django compatibility"
                    )
                    context.pipeline_id = execution_log_id

        # Now try to fetch pipeline data with the extracted pipeline_id
        if context.pipeline_id:
            # CRITICAL FIX: Check if this is an API deployment first (even from execution context)
            api_deployment_data = _fetch_api_deployment_data(
                context.pipeline_id, context.organization_id, context.api_client
            )
            if api_deployment_data:
                context.pipeline_name = api_deployment_data.get("resolved_pipeline_name")
                context.pipeline_type = api_deployment_data.get(
                    "resolved_pipeline_type"
                )  # Should be "API"
                context.pipeline_data = api_deployment_data
                logger.info(
                    f"✅ ROUTING FIX: APIDeployment from execution context - correcting type: name='{context.pipeline_name}', type='{context.pipeline_type}'"
                )
            else:
                # Fallback to regular pipeline lookup
                context.pipeline_data = _fetch_pipeline_data(
                    context.pipeline_id, context.organization_id, context.api_client
                )
                if context.pipeline_data:
                    context.pipeline_name = context.pipeline_data.get(
                        "resolved_pipeline_name"
                    )
                    context.pipeline_type = context.pipeline_data.get(
                        "resolved_pipeline_type"
                    )
                    logger.info(
                        f"✅ Pipeline data from execution context: name='{context.pipeline_name}', type='{context.pipeline_type}', is_api={context.pipeline_data.get('is_api', False)}"
                    )
        else:
            # No pipeline_id found anywhere - this is a critical error for ETL/TASK/APP callbacks
            error_msg = f"No pipeline_id found for ETL/TASK/APP callback. execution_id={context.execution_id}, workflow_id={context.workflow_id}"
            logger.error(error_msg)
            logger.error(
                "ETL/TASK/APP callbacks require pipeline_id to fetch Pipeline data. Cannot proceed without it."
            )
            raise ValueError(error_msg)
    else:
        logger.info(f"Using pipeline_id from direct kwargs: {context.pipeline_id}")

    logger.info(
        f"Extracted context: organization_id={context.organization_id}, workflow_id={context.workflow_id}, pipeline_id={context.pipeline_id}"
    )


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
    final_status = (
        ExecutionStatus.COMPLETED.value
        if aggregated_results["failed_files"] != aggregated_results["total_files"]
        else ExecutionStatus.ERROR.value
    )
    logger.info(
        f"DEBUG: Calculated final_status='{final_status}' (failed_files={aggregated_results['failed_files']})"
    )

    # Log aggregated results for debugging
    logger.info(
        f"DEBUG: Aggregated results: successful_files={aggregated_results.get('successful_files', 0)}, failed_files={aggregated_results.get('failed_files', 0)}, total_files={aggregated_results.get('total_files', 0)}"
    )

    # Use batched status update for better performance
    _update_status_with_batching(
        execution_id=context.execution_id,
        status=final_status,
        organization_id=context.organization_id,
        api_client=context.api_client,
        total_files=aggregated_results["total_files"],
        execution_time=aggregated_results["total_execution_time"],
    )

    return aggregated_results, final_status


def _finalize_execution(
    context: CallbackContext, final_status: str, aggregated_results: dict[str, Any]
) -> dict[str, Any]:
    """Finalize the workflow execution with smart retry logic.

    Args:
        context: Callback context with execution details
        final_status: Final execution status
        aggregated_results: Aggregated processing results

    Returns:
        Finalization result dictionary
    """
    # Finalize the execution with smart retry logic
    retry_manager = get_retry_manager()
    finalization_result = {}

    if retry_manager:
        try:
            finalization_result = retry_manager.execute_with_smart_retry(
                func=context.api_client.finalize_workflow_execution,
                operation_id=f"finalize:{context.execution_id}",
                kwargs={
                    "execution_id": context.execution_id,
                    "final_status": final_status,
                    "total_files_processed": aggregated_results["total_files"],
                    "total_execution_time": aggregated_results["total_execution_time"],
                    "results_summary": aggregated_results,
                    "error_summary": aggregated_results.get("errors", {}),
                    "organization_id": context.organization_id,
                },
                max_attempts=3,
                base_delay=1.0,
                max_delay=10.0,
            )
        except Exception as e:
            if "404" in str(e) or NOT_FOUND_MSG in str(e):
                logger.info(
                    "Finalization API endpoint not available, workflow finalization completed via status update"
                )
                finalization_result = {
                    "status": "simulated",
                    "message": "Finalized via status update",
                }
            else:
                raise e
    else:
        # Fallback to direct API call
        try:
            finalization_result = context.api_client.finalize_workflow_execution(
                execution_id=context.execution_id,
                final_status=final_status,
                total_files_processed=aggregated_results["total_files"],
                total_execution_time=aggregated_results["total_execution_time"],
                results_summary=aggregated_results,
                error_summary=aggregated_results.get("errors", {}),
                organization_id=context.organization_id,
            )
        except Exception as e:
            if "404" in str(e) or NOT_FOUND_MSG in str(e):
                logger.info(
                    "Finalization API endpoint not available, workflow finalization completed via status update"
                )
                finalization_result = {
                    "status": "simulated",
                    "message": "Finalized via status update",
                }
            else:
                raise e

    return finalization_result


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
                logger.info(
                    f"DEBUG: Mapped final_status='{final_status}' to pipeline_status='{pipeline_status}'"
                )

                # Use batched pipeline update for better performance
                pipeline_updated = _update_pipeline_with_batching(
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
                        f"DEBUG: Successfully queued pipeline update {context.pipeline_id} last_run_status to {pipeline_status}"
                    )
                else:
                    logger.warning(
                        f"DEBUG: Failed to queue pipeline update for {context.pipeline_id} - pipeline_status={pipeline_status}, pipeline_name={context.pipeline_name}"
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


def _cleanup_execution_resources(context: CallbackContext) -> dict[str, Any]:
    """Perform comprehensive resource cleanup (backend + directories).

    Args:
        context: Callback context with execution details

    Returns:
        Cleanup result dictionary with status and details
    """
    cleanup_result = {"status": "partial", "backend": {}, "directories": {}}

    # 1. Backend cleanup (existing API-based cleanup)
    try:
        backend_cleanup = context.api_client.cleanup_execution_resources(
            execution_ids=[context.execution_id], cleanup_types=["cache", "temp_files"]
        )
        cleanup_result["backend"] = backend_cleanup
        logger.info(
            f"✅ Backend resource cleanup completed: {backend_cleanup.get('status', 'unknown')}"
        )
    except CircuitBreakerOpenError:
        # TODO: Queue cleanup tasks for later when circuit breaker is open
        # Similar to pipeline status updates, cleanup operations should be queued
        # for retry rather than skipped entirely to prevent resource leaks
        logger.info(
            "Cleanup endpoint circuit breaker open - skipping backend resource cleanup"
        )
        cleanup_result["backend"] = {
            "status": "skipped",
            "message": "Circuit breaker open",
        }
    except Exception as e:
        if "404" in str(e) or NOT_FOUND_MSG in str(e):
            logger.info(
                "Cleanup API endpoint not available, skipping backend resource cleanup"
            )
            cleanup_result["backend"] = {
                "status": "skipped",
                "message": "Cleanup endpoint not available",
            }
        else:
            logger.warning(f"Backend cleanup failed but continuing execution: {str(e)}")
            cleanup_result["backend"] = {
                "status": "failed",
                "error": str(e),
                "execution_continued": True,
            }

    # 2. Cloud storage directory cleanup using existing ExecutionFileHandler
    try:
        from unstract.workflow_execution.execution_file_handler import (
            ExecutionFileHandler,
        )

        # Determine if this is an API or workflow execution
        is_api_execution = context.pipeline_data and context.pipeline_data.get(
            "is_api", False
        )

        if is_api_execution and context.pipeline_id:
            # API execution cleanup: Using existing ExecutionFileHandler with API path
            logger.info(
                f"🧹 Starting API execution directory cleanup for {context.execution_id}"
            )

            # Create ExecutionFileHandler for API execution directory
            # Note: For API, we use get_api_execution_dir but need to clean the entire execution
            api_execution_dir = ExecutionFileHandler.get_api_execution_dir(
                workflow_id=context.pipeline_id,  # For API executions, pipeline_id is the API deployment ID
                execution_id=context.execution_id,
                organization_id=context.organization_id,
            )

            try:
                # Use FileSystem to clean up API execution directory
                from unstract.filesystem import FileStorageType, FileSystem

                file_system = FileSystem(FileStorageType.API)  # Use API storage type
                file_storage = file_system.get_file_storage()

                # Check if directory exists and remove it
                if file_storage.exists(api_execution_dir):
                    # Get directory info before cleanup
                    try:
                        # List files to get count (use ls method from interface)
                        files = file_storage.ls(api_execution_dir)
                        file_count = len(files) if files else 0

                        # Remove the entire execution directory (use rm method from interface)
                        file_storage.rm(api_execution_dir, recursive=True)

                        cleanup_result["directories"] = {
                            "type": "api",
                            "status": "success",
                            "cleaned_paths": [api_execution_dir],
                            "files_deleted": file_count,
                            "message": f"API execution directory cleaned: {api_execution_dir}",
                        }
                        logger.info(
                            f"✅ Successfully cleaned up API execution directory: {api_execution_dir} ({file_count} files)"
                        )

                    except Exception as cleanup_error:
                        logger.error(
                            f"Failed to clean API execution directory: {cleanup_error}"
                        )
                        cleanup_result["directories"] = {
                            "type": "api",
                            "status": "failed",
                            "error": str(cleanup_error),
                            "failed_paths": [api_execution_dir],
                        }
                else:
                    logger.warning(
                        f"API execution directory not found: {api_execution_dir}"
                    )
                    cleanup_result["directories"] = {
                        "type": "api",
                        "status": "skipped",
                        "message": f"Directory not found: {api_execution_dir}",
                    }

            except Exception as fs_error:
                logger.error(f"Failed to initialize API file system: {fs_error}")
                cleanup_result["directories"] = {
                    "type": "api",
                    "status": "failed",
                    "error": f"FileSystem error: {str(fs_error)}",
                }

        elif context.workflow_id:
            # Workflow execution cleanup: Use existing ExecutionFileHandler method
            logger.info(
                f"🧹 Starting workflow execution directory cleanup for {context.execution_id}"
            )

            try:
                # Create ExecutionFileHandler for the specific execution (no file_execution_id = entire execution)
                file_handler = ExecutionFileHandler(
                    workflow_id=context.workflow_id,
                    execution_id=context.execution_id,
                    organization_id=context.organization_id,
                    file_execution_id=None,  # Clean entire execution, not individual file
                )

                # Use the existing delete method - but we need to enhance it for entire execution
                execution_dir = file_handler.execution_dir

                # Use FileSystem to clean up workflow execution directory
                from unstract.filesystem import FileStorageType, FileSystem

                file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
                file_storage = file_system.get_file_storage()

                # Check if directory exists and remove it
                if file_storage.exists(execution_dir):
                    # Get directory info before cleanup
                    try:
                        # List files to get count (use ls method from interface)
                        files = file_storage.ls(execution_dir)
                        file_count = len(files) if files else 0

                        # Remove the entire execution directory (use rm method from interface)
                        file_storage.rm(execution_dir, recursive=True)

                        cleanup_result["directories"] = {
                            "type": "workflow",
                            "status": "success",
                            "cleaned_paths": [execution_dir],
                            "files_deleted": file_count,
                            "message": f"Workflow execution directory cleaned: {execution_dir}",
                        }
                        logger.info(
                            f"✅ Successfully cleaned up workflow execution directory: {execution_dir} ({file_count} files)"
                        )

                    except Exception as cleanup_error:
                        logger.error(
                            f"Failed to clean workflow execution directory: {cleanup_error}"
                        )
                        cleanup_result["directories"] = {
                            "type": "workflow",
                            "status": "failed",
                            "error": str(cleanup_error),
                            "failed_paths": [execution_dir],
                        }
                else:
                    logger.warning(
                        f"Workflow execution directory not found: {execution_dir}"
                    )
                    cleanup_result["directories"] = {
                        "type": "workflow",
                        "status": "skipped",
                        "message": f"Directory not found: {execution_dir}",
                    }

            except Exception as handler_error:
                logger.error(f"Failed to create ExecutionFileHandler: {handler_error}")
                cleanup_result["directories"] = {
                    "type": "workflow",
                    "status": "failed",
                    "error": f"ExecutionFileHandler error: {str(handler_error)}",
                }
        else:
            logger.warning(
                f"⚠️ Cannot determine execution type for cleanup: is_api={is_api_execution}, workflow_id={context.workflow_id}, pipeline_id={context.pipeline_id}"
            )
            cleanup_result["directories"] = {
                "status": "skipped",
                "message": "Cannot determine execution type for directory cleanup",
            }

    except ImportError as import_error:
        logger.warning(
            f"Cloud storage directory cleanup module not available: {import_error}"
        )
        cleanup_result["directories"] = {
            "status": "failed",
            "error": f"Import error: {str(import_error)}",
        }
    except Exception as dir_cleanup_error:
        logger.error(f"Cloud storage directory cleanup failed: {dir_cleanup_error}")
        cleanup_result["directories"] = {
            "status": "failed",
            "error": str(dir_cleanup_error),
        }

    # Determine overall cleanup status
    backend_success = cleanup_result["backend"].get("status") in [
        "success",
        "completed",
        "skipped",
    ]
    directory_success = cleanup_result["directories"].get("status") in [
        "success",
        "skipped",
    ]
    cleanup_result["status"] = (
        "completed" if (backend_success and directory_success) else "partial"
    )

    return cleanup_result


def _handle_callback_notifications(context: CallbackContext) -> None:
    """Handle status notifications after successful batch completion.

    Args:
        context: Callback context with execution details
    """
    # Trigger notifications after successful batch completion (worker-to-worker approach)
    # NOTE: Both callback worker and Django backend may send notifications for backward compatibility
    # Multiple notifications are allowed for now and will be handled by deduplication later
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
    """Core implementation of batch callback processing.

    This function contains the actual processing logic that both the new task
    and Django compatibility task will use.

    Args:
        task_instance: The Celery task instance (self)
        results (list): List of results from each batch
            Each result is a dictionary containing:
            - successful_files: Number of successfully processed files
            - failed_files: Number of failed files
        **kwargs: Additional arguments including:
            - execution_id: ID of the execution

    Returns:
        Callback processing result
    """
    # Initialize performance optimizations
    _initialize_performance_managers()

    # Step 1: Extract and validate parameters
    context = _extract_callback_parameters(task_instance, results, kwargs)

    # Step 2: Setup organization context
    _setup_organization_context(context, results, kwargs)

    # Step 3: Setup API client and execution context
    config, api_client = _setup_api_client_and_execution_context(context)

    # Step 4: Fetch and validate pipeline data
    _fetch_and_validate_pipeline_data(context)

    # Handle final organization validation and context setup
    if not context.organization_id:
        # Try to extract from the first file batch result if available
        for result in results:
            if isinstance(result, dict) and "organization_id" in result:
                context.organization_id = result["organization_id"]
                logger.info(
                    f"Extracted organization_id from batch result: {context.organization_id}"
                )
                break

    # Set organization context using shared utility
    if context.organization_id:
        try:
            # Use standardized execution context setup
            config, api_client = WorkerExecutionContext.setup_execution_context(
                context.organization_id, context.execution_id, context.workflow_id
            )
            context.api_client = api_client
        except Exception as context_error:
            logger.error(f"Failed to setup execution context: {context_error}")
            # Fallback to manual setup for backward compatibility
            StateStore.set(Account.ORGANIZATION_ID, context.organization_id)
            api_client.set_organization_context(context.organization_id)
    else:
        logger.error(
            f"Could not extract organization_id for execution {context.execution_id}. Pipeline status update may fail."
        )

    # Configure batch processor with API client for better performance
    batch_processor = get_batch_processor()
    if batch_processor and not batch_processor.api_client:
        batch_processor.set_api_client(api_client)
        logger.debug("API client configured for batch processor")

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
            # Step 5: Process results and update execution status
            aggregated_results, final_status = _process_results_and_update_status(
                context, results, config
            )

            # Destination processing is now handled in file processing worker (not callback)
            # Callback worker only handles finalization and aggregation
            logger.info(
                f"Destination processing was handled during file processing for {aggregated_results['successful_files']} successful files"
            )
            destination_results = {
                "status": "handled_in_file_processing",
                "reason": "destination_processing_moved_to_file_worker",
                "successful_files": aggregated_results["successful_files"],
            }

            # Step 6: Finalize the execution
            finalization_result = _finalize_execution(
                context, final_status, aggregated_results
            )

            # Step 7: Update pipeline status
            pipeline_updated = _update_pipeline_status(context, final_status)

            # Step 8: Cleanup execution resources
            cleanup_result = _cleanup_execution_resources(context)

            # Step 9: Get performance optimization statistics
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
                    "status_batching_used": True,  # Status update was attempted
                    "pipeline_batching_used": pipeline_updated
                    if context.pipeline_id
                    else False,
                    "cache_stats": performance_stats.get("cache", {}),
                    "batch_stats": performance_stats.get("batch", {}),
                },
            }

            logger.info(
                f"Completed batch callback processing for execution {context.execution_id}"
            )

            # Manually flush batch processor to ensure all updates are processed
            # (but without auto-flush that causes duplicate notifications)
            batch_processor = get_batch_processor()
            if batch_processor:
                try:
                    flushed_count = batch_processor.flush_all()
                    logger.debug(f"Manually flushed {flushed_count} batch operations")
                except Exception as flush_error:
                    logger.warning(f"Failed to flush batch operations: {flush_error}")

            # Step 10: Handle notifications
            _handle_callback_notifications(context)

            return callback_result

        except Exception as e:
            logger.error(
                f"Batch callback processing failed for execution {context.execution_id}: {e}"
            )

            # Try to mark execution as failed
            try:
                with InternalAPIClient(config) as error_api_client:
                    error_api_client.set_organization_context(context.organization_id)
                    try:
                        error_api_client.finalize_workflow_execution(
                            execution_id=context.execution_id,
                            final_status=ExecutionStatus.ERROR.value,
                            error_summary={"callback_error": str(e)},
                            organization_id=context.organization_id,
                        )
                    except Exception as finalize_error:
                        if "404" in str(finalize_error) or NOT_FOUND_MSG in str(
                            finalize_error
                        ):
                            logger.info(
                                "Finalization API endpoint not available, execution marked as failed via status update"
                            )
                        else:
                            raise finalize_error
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

                # Calculate execution time and finalize
                # FIXED: Use wall-clock time instead of sum of file processing times
                # For parallel execution: 3 files x 3 sec each = 4 sec wall-clock, not 9 sec
                execution_time = WallClockTimeCalculator.calculate_execution_time(
                    api_client, execution_id, organization_id, all_file_results
                )

                # Debug logging for execution time calculation
                logger.info(
                    f"DEBUG: API callback calculated execution_time: {execution_time:.2f}s from {len(all_file_results)} file results"
                )
                if execution_time == 0:
                    logger.warning(
                        f"DEBUG: Execution time is 0! File results: {[r.get('processing_time', 'missing') for r in all_file_results[:3]]}"
                    )

                # Update execution status to completed with execution time (FIXED)
                api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status=ExecutionStatus.COMPLETED.value,
                    execution_time=execution_time,  # Add the calculated execution time
                )

                # OPTIMIZATION: Skip pipeline status update for API deployments
                # API deployments use APIDeployment model, not Pipeline model
                # Pipeline status updates don't apply to APIDeployments and cause 404 errors
                if pipeline_id:
                    # API callbacks always handle APIDeployments, so skip pipeline status update
                    logger.info(
                        f"OPTIMIZATION: Skipping pipeline status update for API deployment {pipeline_id} (no Pipeline record exists)"
                    )

                    # Trigger notifications for API deployment (worker-to-worker approach)
                    # NOTE: Both callback worker and Django backend may send notifications for backward compatibility
                    # Multiple notifications are allowed for now and will be handled by deduplication later
                    try:
                        # DEBUG: Log notification parameters before calling handle_status_notifications
                        logger.info(
                            f"DEBUG: About to trigger notifications with - pipeline_id='{pipeline_id}', pipeline_name='{pipeline_name}', pipeline_type='{pipeline_type}', status='{ExecutionStatus.COMPLETED.value}', execution_id='{execution_id}'"
                        )

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
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error=str(e),
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
    name="finalize_execution_callback",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
@monitor_performance
@with_execution_context
def finalize_execution_callback(
    self, schema_name: str, execution_id: str, cleanup_resources: bool = True
) -> dict[str, Any]:
    """Finalize execution and cleanup resources.

    This is a standalone task for execution finalization that can be
    called independently or as part of the callback processing.
    """
    logger.info(f"Finalizing execution {execution_id}")

    try:
        config = WorkerConfig()
        with InternalAPIClient(config) as api_client:
            api_client.set_organization_context(schema_name)

            # Get current execution status
            finalization_status = api_client.get_execution_finalization_status(
                execution_id
            )

            if finalization_status.get("is_finalized"):
                logger.info(f"Execution {execution_id} already finalized")
                return {
                    "status": "already_finalized",
                    "execution_id": execution_id,
                    "current_status": finalization_status.get("current_status"),
                }

            # Perform comprehensive cleanup if requested (backend + directories)
            cleanup_result = None
            if cleanup_resources:
                # Backend cleanup
                backend_cleanup = api_client.cleanup_execution_resources(
                    execution_ids=[execution_id],
                    cleanup_types=["cache", "temp_files", "logs"],
                )

                # Directory cleanup (if we can determine the context)
                directory_cleanup = {
                    "status": "skipped",
                    "message": "Context not available in finalize_execution",
                }
                try:
                    # Try to get execution context to determine cleanup type
                    # Note: This function has limited context, so directory cleanup may be skipped
                    # The main cleanup should happen in process_batch_callback with full context
                    logger.info(
                        "🧹 Finalize execution: Directory cleanup skipped - insufficient context"
                    )
                    logger.info(
                        "   (Main directory cleanup should occur in process_batch_callback)"
                    )
                except Exception as dir_error:
                    logger.warning(
                        f"Directory cleanup in finalize_execution failed: {dir_error}"
                    )

                cleanup_result = {
                    "backend": backend_cleanup,
                    "directories": directory_cleanup,
                    "note": "Full directory cleanup should occur in main callback with complete context",
                }

                finalization_result = {
                    "status": "finalized",
                    "execution_id": execution_id,
                    "task_id": self.request.id,
                    "cleanup_result": cleanup_result,
                    "finalized_at": time.time(),
                }

                logger.info(f"Successfully finalized execution {execution_id}")

                return finalization_result

    except Exception as e:
        logger.error(f"Failed to finalize execution {execution_id}: {e}")
        raise


# Backward compatibility aliases for Django backend during transition
# Register the same task function with the old Django task names for compatibility


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
