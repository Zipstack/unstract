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
from datetime import datetime
from typing import Any

import pytz

# Use Celery current_app to avoid circular imports
from celery import current_app as app

# Import shared worker infrastructure
from shared.api_client import InternalAPIClient
from shared.backoff_utils import (
    get_backoff_manager,
    get_retry_manager,
    initialize_backoff_managers,
)
from shared.batch_utils import (
    BatchConfig,
    add_pipeline_update_to_batch,
    add_status_update_to_batch,
    get_batch_processor,
    initialize_batch_processor,
)

# Import performance optimization utilities
from shared.cache_utils import get_cache_manager, initialize_cache_manager
from shared.config import WorkerConfig

# Import from shared worker modules
from shared.constants import Account
from shared.enums import PipelineType
from shared.enums.status_enums import PipelineStatus
from shared.enums.task_enums import TaskName
from shared.execution_context import WorkerExecutionContext
from shared.local_context import StateStore
from shared.logging_utils import WorkerLogger, log_context, monitor_performance
from shared.notification_helper import handle_status_notifications
from shared.retry_utils import CircuitBreakerOpenError, circuit_breaker

from unstract.connectors import ConnectionType

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus, FileHashData

logger = WorkerLogger.get_logger(__name__)

# Initialize performance optimization managers on module load
_performance_managers_initialized = False


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


def _fetch_pipeline_name_from_api(
    pipeline_id: str, organization_id: str, api_client: InternalAPIClient
) -> tuple[str | None, str | None]:
    """Fetch pipeline name from Pipeline or APIDeployment models via internal API.

    DEPRECATED: Use _fetch_pipeline_data instead for complete pipeline information.

    Args:
        pipeline_id: Pipeline or API deployment ID
        organization_id: Organization context
        api_client: API client instance

    Returns:
        Tuple of (pipeline_name, pipeline_type) or (None, None) if not found
    """
    pipeline_data = _fetch_pipeline_data(pipeline_id, organization_id, api_client)

    if pipeline_data:
        pipeline_name = pipeline_data.get("resolved_pipeline_name")
        pipeline_type = pipeline_data.get("resolved_pipeline_type")
        return pipeline_name, pipeline_type

    return None, None


def _get_cached_execution_status(
    execution_id: str, organization_id: str, api_client: InternalAPIClient
) -> dict:
    """Get execution status with caching optimization.

    Args:
        execution_id: Execution ID
        organization_id: Organization context
        api_client: API client instance

    Returns:
        Execution status data
    """
    cache_manager = get_cache_manager()
    backoff_manager = get_backoff_manager()

    # Try cache first
    if cache_manager and cache_manager.is_available:
        cached_status = cache_manager.get_execution_status(execution_id, organization_id)
        if cached_status:
            logger.debug(f"Using cached status for execution {execution_id}")
            return cached_status

    # Cache miss - fetch from API with backoff
    try:
        if backoff_manager:
            # Apply exponential backoff if this operation has been failing
            if not backoff_manager.should_retry(
                "status_check", execution_id, organization_id
            ):
                logger.warning(
                    f"Status check retry limit exceeded for execution {execution_id}"
                )
                # Return minimal status to prevent infinite retries
                return {
                    "status": "ERROR",
                    "error_message": "Status check retry limit exceeded",
                    "cached_fallback": True,
                }

            delay = backoff_manager.get_delay(
                "status_check", execution_id, organization_id
            )
            if delay > 0:
                logger.debug(f"Applying backoff delay {delay:.2f}s for status check")
                time.sleep(delay)

        # Fetch status from API
        execution_response = api_client.get_workflow_execution(execution_id)
        if not execution_response.success:
            raise Exception(
                f"Failed to get execution context: {execution_response.error}"
            )
        execution_context = execution_response.data
        status_data = execution_context.get("execution", {})

        # Cache the result
        if cache_manager and cache_manager.is_available:
            cache_manager.set_execution_status(execution_id, organization_id, status_data)

        # Clear backoff on success
        if backoff_manager:
            backoff_manager.clear_attempts("status_check", execution_id, organization_id)

        return status_data

    except Exception as e:
        logger.warning(f"Failed to get execution status for {execution_id}: {e}")
        # Don't re-raise - return error status to prevent infinite retries
        return {
            "status": "ERROR",
            "error_message": f"Status fetch failed: {str(e)}",
            "api_error": True,
        }


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
    pipeline_name: str | None = None,
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
    task_id = task_instance.request.id if hasattr(task_instance, "request") else "unknown"

    # Initialize performance optimizations
    _initialize_performance_managers()

    # Extract execution_id from kwargs exactly like Django backend
    execution_id = kwargs.get("execution_id")
    if not execution_id:
        raise ValueError("execution_id is required in kwargs")

    # CRITICAL FIX: Get pipeline_id directly from kwargs first (preferred)
    pipeline_id = kwargs.get("pipeline_id")

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
            f"CRITICAL: Could not determine organization_id for execution {execution_id}"
        )
        logger.error(
            "This will likely cause API calls to fail due to missing organization context"
        )

    # Get workflow execution context via API with caching optimization
    config = WorkerConfig()
    with InternalAPIClient(config) as api_client:
        # Final fallback: use API client's default organization_id if available
        if not organization_id and api_client.organization_id:
            organization_id = api_client.organization_id
            logger.info(
                f"DEBUG: Using API client's default organization_id: {organization_id}"
            )

        # Set organization context BEFORE making API calls (CRITICAL for getting correct pipeline_id)
        if organization_id:
            api_client.set_organization_context(organization_id)
            logger.info(
                f"✅ Set organization context before API calls: {organization_id}"
            )
        else:
            logger.error(
                "CRITICAL: No organization_id available for API calls - this will cause pipeline_id to be null"
            )

        execution_response = api_client.get_workflow_execution(execution_id)
        if not execution_response.success:
            raise Exception(
                f"Failed to get execution context: {execution_response.error}"
            )
        execution_context = execution_response.data
        workflow_execution = execution_context.get("execution", {})
        workflow = execution_context.get("workflow", {})
        logger.info(f"DEBUG: ! execution_context: {execution_context}")
        logger.info(f"DEBUG: ! workflow_execution: {workflow_execution}")
        logger.info(f"DEBUG: ! workflow: {workflow}")

        # Organization_id already extracted before API call - use as fallback if needed
        if not organization_id:
            organization_id = (
                workflow_execution.get("organization_id")
                or workflow.get("organization_id")
                or workflow.get("organization", {}).get("id")
                if isinstance(workflow.get("organization"), dict)
                else execution_context.get("organization_context", {}).get(
                    "organization_id"
                )
                or None
            )
            if organization_id:
                logger.info(
                    f"Fallback: extracted organization_id from execution context: {organization_id}"
                )

        workflow_id = workflow_execution.get("workflow_id") or workflow.get("id")

        # Extract Pipeline data via unified internal API (optimized for ETL/TASK/APP pipelines)
        # Note: process_batch_callback handles ETL/TASK/APP types (Pipeline model)
        # while process_batch_callback_api handles API type (APIDeployment model via v2 endpoint)
        pipeline_name = None
        pipeline_type = None
        pipeline_data = None

        if pipeline_id:
            # CRITICAL FIX: Check if this is an API deployment first to ensure correct notification type
            # The backend may route API deployments to the general worker queue by mistake,
            # but we still need to send notifications with type="API" instead of type="ETL"
            api_deployment_data = _fetch_api_deployment_data(
                pipeline_id, organization_id, api_client
            )
            if api_deployment_data:
                pipeline_name = api_deployment_data.get("resolved_pipeline_name")
                pipeline_type = api_deployment_data.get(
                    "resolved_pipeline_type"
                )  # Should be "API"
                pipeline_data = api_deployment_data
                logger.info(
                    f"✅ ROUTING FIX: APIDeployment routed to ETL callback - correcting type: name='{pipeline_name}', type='{pipeline_type}'"
                )
            else:
                # Fallback to regular pipeline lookup for ETL/TASK/APP workflows
                pipeline_data = _fetch_pipeline_data(
                    pipeline_id, organization_id, api_client
                )
                if pipeline_data:
                    pipeline_name = pipeline_data.get("resolved_pipeline_name")
                    pipeline_type = pipeline_data.get("resolved_pipeline_type")
                    logger.info(
                        f"✅ Pipeline data from models: name='{pipeline_name}', type='{pipeline_type}', is_api={pipeline_data.get('is_api', False)}"
                    )
        else:
            # No pipeline_id provided - check if we can extract from execution context
            logger.warning(
                "No pipeline_id provided directly for ETL/TASK/APP callback. Checking execution context..."
            )

        # Try to extract pipeline_id from execution context if not passed directly
        if not pipeline_id:
            pipeline_id = workflow_execution.get("pipeline_id")
            logger.info(f"Using pipeline_id from execution context: {pipeline_id}")

            # BACKWARD COMPATIBILITY: During Django transition, execution_log_id might contain the pipeline_id
            if not pipeline_id:
                execution_log_id = workflow_execution.get("execution_log_id")
                if execution_log_id:
                    logger.warning(
                        f"BACKWARD COMPATIBILITY: pipeline_id is None but execution_log_id exists: {execution_log_id}"
                    )
                    logger.info(
                        "Attempting to use execution_log_id as pipeline_id for Django compatibility"
                    )
                    pipeline_id = execution_log_id

            # Now try to fetch pipeline data with the extracted pipeline_id
            if pipeline_id:
                # CRITICAL FIX: Check if this is an API deployment first (even from execution context)
                api_deployment_data = _fetch_api_deployment_data(
                    pipeline_id, organization_id, api_client
                )
                if api_deployment_data:
                    pipeline_name = api_deployment_data.get("resolved_pipeline_name")
                    pipeline_type = api_deployment_data.get(
                        "resolved_pipeline_type"
                    )  # Should be "API"
                    pipeline_data = api_deployment_data
                    logger.info(
                        f"✅ ROUTING FIX: APIDeployment from execution context - correcting type: name='{pipeline_name}', type='{pipeline_type}'"
                    )
                else:
                    # Fallback to regular pipeline lookup
                    pipeline_data = _fetch_pipeline_data(
                        pipeline_id, organization_id, api_client
                    )
                    if pipeline_data:
                        pipeline_name = pipeline_data.get("resolved_pipeline_name")
                        pipeline_type = pipeline_data.get("resolved_pipeline_type")
                        logger.info(
                            f"✅ Pipeline data from execution context: name='{pipeline_name}', type='{pipeline_type}', is_api={pipeline_data.get('is_api', False)}"
                        )
            else:
                # No pipeline_id found anywhere - this is a critical error for ETL/TASK/APP callbacks
                error_msg = f"No pipeline_id found for ETL/TASK/APP callback. execution_id={execution_id}, workflow_id={workflow_id}"
                logger.error(error_msg)
                logger.error(
                    "ETL/TASK/APP callbacks require pipeline_id to fetch Pipeline data. Cannot proceed without it."
                )
                raise ValueError(error_msg)
        else:
            logger.info(f"Using pipeline_id from direct kwargs: {pipeline_id}")

        logger.info(
            f"Extracted context: organization_id={organization_id}, workflow_id={workflow_id}, pipeline_id={pipeline_id}"
        )

        if not organization_id:
            logger.warning(
                f"Organization ID not found in execution context: {execution_context}"
            )
            # Try to extract from the first file batch result if available
            for result in results:
                if isinstance(result, dict) and "organization_id" in result:
                    organization_id = result["organization_id"]
                    logger.info(
                        f"Extracted organization_id from batch result: {organization_id}"
                    )
                    break

        # Set organization context using shared utility
        if organization_id:
            try:
                # Use standardized execution context setup
                config, api_client = WorkerExecutionContext.setup_execution_context(
                    organization_id, execution_id, workflow_id
                )
            except Exception as context_error:
                logger.error(f"Failed to setup execution context: {context_error}")
                # Fallback to manual setup for backward compatibility
                StateStore.set(Account.ORGANIZATION_ID, organization_id)
                api_client.set_organization_context(organization_id)
        else:
            logger.error(
                f"Could not extract organization_id for execution {execution_id}. Pipeline status update may fail."
            )

        # Configure batch processor with API client for better performance
        batch_processor = get_batch_processor()
        if batch_processor and not batch_processor.api_client:
            batch_processor.set_api_client(api_client)
            logger.debug("API client configured for batch processor")

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=organization_id,
        pipeline_id=pipeline_id,
    ):
        logger.info(f"Starting batch callback processing for execution {execution_id}")

        try:
            # Aggregate results from all file batches (exactly like Django backend)
            aggregated_results = _aggregate_file_batch_results(results)

            # FIXED: Use wall-clock execution time instead of summed file processing times
            # For parallel execution: 3 files x 3 sec each = 4 sec wall-clock, not 9 sec
            wall_clock_time = WallClockTimeCalculator.calculate_execution_time(
                api_client, execution_id, organization_id
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
            status_updated = _update_status_with_batching(
                execution_id=execution_id,
                status=final_status,
                organization_id=organization_id,
                api_client=api_client,
                total_files=aggregated_results["total_files"],
                execution_time=aggregated_results["total_execution_time"],
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

            # Finalize the execution with smart retry logic
            retry_manager = get_retry_manager()
            finalization_result = {}

            if retry_manager:
                try:
                    finalization_result = retry_manager.execute_with_smart_retry(
                        func=api_client.finalize_workflow_execution,
                        operation_id=f"finalize:{execution_id}",
                        kwargs={
                            "execution_id": execution_id,
                            "final_status": final_status,
                            "total_files_processed": aggregated_results["total_files"],
                            "total_execution_time": aggregated_results[
                                "total_execution_time"
                            ],
                            "results_summary": aggregated_results,
                            "error_summary": aggregated_results.get("errors", {}),
                            "organization_id": organization_id,
                        },
                        max_attempts=3,
                        base_delay=1.0,
                        max_delay=10.0,
                    )
                except Exception as e:
                    if "404" in str(e) or "Not Found" in str(e):
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
                    finalization_result = api_client.finalize_workflow_execution(
                        execution_id=execution_id,
                        final_status=final_status,
                        total_files_processed=aggregated_results["total_files"],
                        total_execution_time=aggregated_results["total_execution_time"],
                        results_summary=aggregated_results,
                        error_summary=aggregated_results.get("errors", {}),
                        organization_id=organization_id,
                    )
                except Exception as e:
                    if "404" in str(e) or "Not Found" in str(e):
                        logger.info(
                            "Finalization API endpoint not available, workflow finalization completed via status update"
                        )
                        finalization_result = {
                            "status": "simulated",
                            "message": "Finalized via status update",
                        }
                    else:
                        raise e

            # Update pipeline status using optimized batching
            # OPTIMIZATION: Skip pipeline status update for API deployments to avoid 404 errors
            pipeline_updated = False
            if pipeline_id:
                # Check if this is an API deployment (has pipeline_data with is_api=True)
                is_api_deployment = pipeline_data and pipeline_data.get("is_api", False)

                if is_api_deployment:
                    logger.info(
                        f"OPTIMIZATION: Skipping pipeline status update for API deployment {pipeline_id} (no Pipeline record exists)"
                    )
                    pipeline_updated = True  # Mark as "updated" to avoid warnings
                else:
                    try:
                        logger.info(
                            f"Updating pipeline {pipeline_id} status with organization_id: {organization_id}"
                        )

                        # Map execution status to pipeline status
                        pipeline_status = _map_execution_status_to_pipeline_status(
                            final_status
                        )
                        logger.info(
                            f"DEBUG: Mapped final_status='{final_status}' to pipeline_status='{pipeline_status}'"
                        )

                        # Use batched pipeline update for better performance
                        pipeline_updated = _update_pipeline_with_batching(
                            pipeline_id=pipeline_id,
                            execution_id=execution_id,
                            status=pipeline_status,
                            organization_id=organization_id,
                            api_client=api_client,
                            pipeline_name=pipeline_name,
                            last_run_status=pipeline_status,
                            last_run_time=time.time(),
                            increment_run_count=True,
                        )

                        if pipeline_updated:
                            logger.info(
                                f"DEBUG: Successfully queued pipeline update {pipeline_id} last_run_status to {pipeline_status}"
                            )
                        else:
                            logger.warning(
                                f"DEBUG: Failed to queue pipeline update for {pipeline_id} - pipeline_status={pipeline_status}, pipeline_name={pipeline_name}"
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
                            or "Not Found" in str(e)
                        ):
                            logger.info(
                                f"Pipeline {pipeline_id} not found - likely using stale reference, skipping update"
                            )
                            pass
                        else:
                            logger.warning(f"Failed to update pipeline status: {str(e)}")

            # Cleanup resources (gracefully handle missing endpoint)
            try:
                cleanup_result = api_client.cleanup_execution_resources(
                    execution_ids=[execution_id], cleanup_types=["cache", "temp_files"]
                )
            except CircuitBreakerOpenError:
                # TODO: Queue cleanup tasks for later when circuit breaker is open
                # Similar to pipeline status updates, cleanup operations should be queued
                # for retry rather than skipped entirely to prevent resource leaks
                logger.info(
                    "Cleanup endpoint circuit breaker open - skipping resource cleanup"
                )
                cleanup_result = {"status": "skipped", "message": "Circuit breaker open"}
            except Exception as e:
                if "404" in str(e) or "Not Found" in str(e):
                    logger.info(
                        "Cleanup API endpoint not available, skipping resource cleanup"
                    )
                    cleanup_result = {
                        "status": "skipped",
                        "message": "Cleanup endpoint not available",
                    }
                else:
                    logger.warning(f"Cleanup failed but continuing execution: {str(e)}")
                    cleanup_result = {
                        "status": "failed",
                        "error": str(e),
                        "execution_continued": True,
                    }

            # Get performance optimization statistics
            performance_stats = _get_performance_stats()

            callback_result = {
                "status": "completed",
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "task_id": task_id,
                "aggregated_results": aggregated_results,
                "destination_results": destination_results,
                "finalization_result": finalization_result,
                "cleanup_result": cleanup_result,
                "pipeline_id": pipeline_id,
                "performance_optimizations": {
                    "status_batching_used": status_updated,
                    "pipeline_batching_used": pipeline_updated if pipeline_id else False,
                    "cache_stats": performance_stats.get("cache", {}),
                    "batch_stats": performance_stats.get("batch", {}),
                },
            }

            logger.info(
                f"Completed batch callback processing for execution {execution_id}"
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

            # Trigger notifications after successful batch completion (worker-to-worker approach)
            # NOTE: Both callback worker and Django backend may send notifications for backward compatibility
            # Multiple notifications are allowed for now and will be handled by deduplication later
            try:
                # Try to trigger notifications using workflow_id if pipeline_id is None
                notification_target_id = pipeline_id if pipeline_id else workflow_id
                if notification_target_id:
                    logger.info(
                        f"Triggering notifications for target_id={notification_target_id} (execution completed)"
                    )
                    # Ensure organization context is set for notification requests
                    api_client.set_organization_context(organization_id)
                    handle_status_notifications(
                        api_client=api_client,
                        pipeline_id=notification_target_id,
                        status="COMPLETED",
                        execution_id=execution_id,
                        error_message=None,
                        pipeline_name=pipeline_name,
                        pipeline_type=pipeline_type,
                        organization_id=organization_id,
                    )
                else:
                    logger.info("No target ID available for notifications")
            except Exception as notif_error:
                logger.warning(
                    f"Failed to trigger completion notifications: {notif_error}"
                )
                # Continue execution - notifications are not critical for callback success

            return callback_result

        except Exception as e:
            logger.error(
                f"Batch callback processing failed for execution {execution_id}: {e}"
            )

            # Try to mark execution as failed
            try:
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(organization_id)
                    try:
                        api_client.finalize_workflow_execution(
                            execution_id=execution_id,
                            final_status="ERROR",
                            error_summary={"callback_error": str(e)},
                            organization_id=organization_id,
                        )
                    except Exception as finalize_error:
                        if "404" in str(finalize_error) or "Not Found" in str(
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


def _aggregate_file_batch_results(
    file_batch_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate results from multiple file batches.

    Args:
        file_batch_results: List of file batch processing results

    Returns:
        Aggregated results summary
    """
    start_time = time.time()

    total_files = 0
    successful_files = 0
    failed_files = 0
    skipped_files = 0
    total_execution_time = 0.0
    all_file_results = []
    errors = {}

    for batch_result in file_batch_results:
        if isinstance(batch_result, dict):
            # Aggregate file counts - now total_files should be included from FileBatchResult.to_dict()
            batch_total = batch_result.get("total_files", 0)
            batch_successful = batch_result.get("successful_files", 0)
            batch_failed = batch_result.get("failed_files", 0)
            batch_skipped = batch_result.get("skipped_files", 0)

            # If total_files is missing but we have successful+failed, calculate it
            if batch_total == 0 and (batch_successful > 0 or batch_failed > 0):
                batch_total = batch_successful + batch_failed + batch_skipped

            total_files += batch_total
            successful_files += batch_successful
            failed_files += batch_failed
            skipped_files += batch_skipped

            # Aggregate execution times - now get from batch result directly
            batch_time = batch_result.get("execution_time", 0)
            file_results = batch_result.get("file_results", [])

            # Fallback to individual file processing times if batch time not available
            if batch_time == 0:
                for file_result in file_results:
                    if isinstance(file_result, dict):
                        batch_time += file_result.get("processing_time", 0)

            # Collect error information from file results
            for file_result in file_results:
                if isinstance(file_result, dict) and file_result.get("status") == "error":
                    file_name = file_result.get("file_name", "unknown")
                    error_msg = file_result.get("error", "Unknown error")
                    errors[file_name] = error_msg

            total_execution_time += batch_time
            all_file_results.extend(file_results)

    aggregation_time = time.time() - start_time

    aggregated_results = {
        "total_files": total_files,
        "successful_files": successful_files,
        "failed_files": failed_files,
        "skipped_files": skipped_files,
        "total_execution_time": total_execution_time,
        "aggregation_time": aggregation_time,
        "success_rate": (successful_files / total_files) * 100 if total_files > 0 else 0,
        "file_results": all_file_results,
        "errors": errors,
        "batches_processed": len(file_batch_results),
    }

    logger.info(
        f"Aggregated {len(file_batch_results)} batches: {successful_files}/{total_files} successful files"
    )

    return aggregated_results


def _update_execution_with_results(
    api_client: InternalAPIClient,
    execution_id: str,
    aggregated_results: dict[str, Any],
    organization_id: str,
) -> dict[str, Any]:
    """Update workflow execution with aggregated results."""
    try:
        # Determine final status
        if aggregated_results["failed_files"] == 0:
            final_status = "COMPLETED"
        elif aggregated_results["successful_files"] > 0:
            final_status = "COMPLETED"
        else:
            final_status = "ERROR"

        # Update execution status
        update_result = api_client.update_workflow_execution_status(
            execution_id=execution_id, status=final_status
        )

        logger.info(f"Updated execution {execution_id} status to {final_status}")

        return update_result

    except Exception as e:
        logger.error(f"Failed to update execution with results: {e}")
        raise


# DEPRECATED: Destination processing moved to file processing worker
# This function is kept for reference but is no longer called
def _handle_destination_delivery_deprecated(
    api_client: InternalAPIClient,
    workflow_id: str,
    execution_id: str,
    aggregated_results: dict[str, Any],
) -> dict[str, Any]:
    """Handle delivery of results to destination connectors.

    This coordinates actual destination processing by calling the backend
    destination processing API for all successfully processed files.
    """
    try:
        logger.info(f"Handling destination delivery for execution {execution_id}")

        # Get successful file results that need destination processing
        successful_files = [
            fr
            for fr in aggregated_results["file_results"]
            if fr.get("status") == "success"
        ]

        if not successful_files:
            logger.info("No successful files to deliver to destination")
            return {
                "status": "skipped",
                "reason": "no_successful_files",
                "files_delivered": 0,
            }

        logger.info(
            f"Processing destination delivery for {len(successful_files)} successful files"
        )

        # Get workflow execution context for destination configuration
        try:
            execution_response = api_client.get_workflow_execution(execution_id)
            if not execution_response.success:
                raise Exception(
                    f"Failed to get execution context: {execution_response.error}"
                )
            execution_context = execution_response.data
            workflow = execution_context.get("workflow", {})
            destination_config = execution_context.get("destination_config", {})

            if not destination_config:
                logger.warning(
                    f"No destination configuration found for workflow {workflow_id} - creating default config for graceful handling"
                )
                # Create default destination config to allow workflow completion
                destination_config = {
                    "connection_type": ConnectionType.FILESYSTEM.value,
                    "settings": {},
                    "is_api": workflow.get("deployment_type") == PipelineType.API.value,
                    "use_file_history": True,
                }
                logger.info(
                    f"Created default destination config for graceful handling: {destination_config['connection_type']}"
                )

        except Exception as e:
            logger.error(f"Failed to get workflow execution context: {str(e)}")
            return {
                "status": "failed",
                "error": f"Could not get workflow context: {str(e)}",
                "files_delivered": 0,
            }

        # Process each successful file through destination connector
        delivered_files = 0
        failed_deliveries = 0
        delivery_details = []

        # Import worker-compatible destination connector components
        from shared.workflow.destination_connector import WorkerDestinationConnector

        from unstract.core.data_models import DestinationConfig

        try:
            # Handle parameter transformation for backward compatibility
            if (
                "destination_settings" in destination_config
                and "settings" not in destination_config
            ):
                logger.info(
                    "Transforming legacy destination_settings to settings format in callback"
                )
                # Preserve all existing fields and only transform the settings field
                transformed_config = dict(destination_config)  # Copy all existing fields
                transformed_config["settings"] = destination_config.get(
                    "destination_settings", {}
                )
                # Remove the old field to avoid confusion
                if "destination_settings" in transformed_config:
                    del transformed_config["destination_settings"]
                destination_config = transformed_config
                logger.info(
                    f"Transformed destination config, preserved connector fields: {list(destination_config.keys())}"
                )

            # Validate required fields
            if "connection_type" not in destination_config:
                logger.warning(
                    "Missing connection_type in destination config, defaulting to FILESYSTEM"
                )
                destination_config["connection_type"] = ConnectionType.FILESYSTEM.value

            # Log what connector instance data we received
            connector_fields = ["connector_id", "connector_settings", "connector_name"]
            available_connector_fields = [
                field for field in connector_fields if field in destination_config
            ]
            if available_connector_fields:
                logger.info(
                    f"Received connector instance fields: {available_connector_fields}"
                )
            else:
                logger.warning("No connector instance fields found in destination config")

            # Create destination connector using from_dict to handle string-to-enum conversion
            dest_config = DestinationConfig.from_dict(destination_config)
            destination = WorkerDestinationConnector.from_config(None, dest_config)
            logger.info(
                f"Created destination connector: {dest_config.connection_type} (API: {dest_config.is_api})"
            )

            for file_result in successful_files:
                try:
                    file_name = file_result.get("file_name", "unknown")
                    file_execution_id = file_result.get("file_execution_id")

                    if not file_name or file_name == "unknown":
                        logger.warning(f"File result missing name: {file_result}")
                        file_name = f"unknown_file_{int(time.time())}"

                    if not file_execution_id:
                        logger.warning(f"File result missing execution ID: {file_result}")
                        # Skip files without execution ID as they can't be tracked
                        failed_deliveries += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": None,
                                "status": "failed",
                                "error": "Missing file_execution_id",
                            }
                        )
                        continue

                    # Create file hash object for destination processing with fallback values
                    file_hash_data = {
                        "file_name": file_name,
                        "file_path": file_result.get("file_path", ""),
                        "file_hash": file_result.get("file_hash", ""),
                        "file_size": file_result.get("file_size", 0),
                        "mime_type": file_result.get(
                            "mime_type", "application/octet-stream"
                        ),
                        "provider_file_uuid": file_result.get("provider_file_uuid"),
                        "fs_metadata": file_result.get("fs_metadata", {}),
                    }

                    # Log if file_hash is missing
                    if not file_result.get("file_hash"):
                        logger.info(
                            f"File hash not provided for {file_name} - will be computed if needed"
                        )

                    file_hash = FileHashData.from_dict(file_hash_data)

                    # Process file through destination with database persistence
                    output_result = destination.handle_output(
                        file_name=file_name,
                        file_hash=file_hash,
                        file_history=None,  # Will be checked internally
                        workflow=workflow,
                        input_file_path=file_hash.file_path,
                        file_execution_id=file_execution_id,
                        api_client=api_client,  # Pass API client for database operations
                        tool_execution_result=file_result.get("tool_result")
                        or file_result.get("result"),  # Pass tool execution results
                    )

                    if output_result:
                        delivered_files += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": file_execution_id,
                                "status": "delivered",
                                "result": output_result,
                            }
                        )
                        logger.info(f"Successfully delivered {file_name} to destination")
                    else:
                        failed_deliveries += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": file_execution_id,
                                "status": "failed",
                                "error": "Destination handler returned None",
                            }
                        )
                        logger.warning(
                            f"Destination delivery returned None for {file_name}"
                        )

                except Exception as file_error:
                    failed_deliveries += 1
                    delivery_details.append(
                        {
                            "file_name": file_result.get("file_name", "unknown"),
                            "file_execution_id": file_result.get("file_execution_id"),
                            "status": "failed",
                            "error": str(file_error),
                        }
                    )
                    logger.error(
                        f"Failed to deliver file {file_result.get('file_name')}: {str(file_error)}"
                    )

        except Exception as connector_error:
            logger.error(
                f"Failed to create destination connector: {str(connector_error)}"
            )
            return {
                "status": "failed",
                "error": f"Destination connector creation failed: {str(connector_error)}",
                "files_delivered": 0,
            }

        # Determine overall delivery status
        if delivered_files > 0 and failed_deliveries == 0:
            status = "success"
        elif delivered_files > 0 and failed_deliveries > 0:
            status = "partial"
        elif failed_deliveries > 0:
            status = "failed"
        else:
            status = "unknown"

        delivery_result = {
            "status": status,
            "destination_type": dest_config.connection_type,
            "files_delivered": delivered_files,
            "failed_deliveries": failed_deliveries,
            "total_files": len(successful_files),
            "delivery_time": time.time(),
            "details": delivery_details,
        }

        logger.info(
            f"Destination delivery completed: {delivered_files}/{len(successful_files)} files delivered successfully"
        )

        return delivery_result

    except Exception as e:
        logger.error(f"Failed to handle destination delivery: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "files_delivered": 0}


@app.task(
    bind=True,
    name="finalize_execution_callback",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
@monitor_performance
def finalize_execution_callback(
    self, schema_name: str, execution_id: str, cleanup_resources: bool = True
) -> dict[str, Any]:
    """Finalize execution and cleanup resources.

    This is a standalone task for execution finalization that can be
    called independently or as part of the callback processing.
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id, execution_id=execution_id, organization_id=schema_name
    ):
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

                # Perform cleanup if requested
                cleanup_result = None
                if cleanup_resources:
                    cleanup_result = api_client.cleanup_execution_resources(
                        execution_ids=[execution_id],
                        cleanup_types=["cache", "temp_files", "logs"],
                    )

                finalization_result = {
                    "status": "finalized",
                    "execution_id": execution_id,
                    "task_id": task_id,
                    "cleanup_result": cleanup_result,
                    "finalized_at": time.time(),
                }

                logger.info(f"Successfully finalized execution {execution_id}")

                return finalization_result

        except Exception as e:
            logger.error(f"Failed to finalize execution {execution_id}: {e}")
            raise


# Simple resilient executor decorator (placeholder)
def resilient_executor(func):
    """Simple resilient executor decorator."""
    return func


# Resilient callback processor
@app.task(bind=True)
@resilient_executor
def process_batch_callback_resilient(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    file_batch_results: list[dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    """Resilient batch callback processing with advanced error handling."""
    task_id = self.request.id

    with log_context(task_id=task_id, execution_id=execution_id, workflow_id=workflow_id):
        logger.info(
            f"Starting resilient batch callback processing for execution {execution_id}"
        )

        try:
            # Use the main callback processing function
            result = process_batch_callback(
                schema_name=schema_name,
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_batch_results=file_batch_results,
                **kwargs,
            )

            return result

        except Exception as e:
            logger.error(f"Resilient batch callback processing failed: {e}")
            raise


class WallClockTimeCalculator:
    """Utility class to calculate wall-clock execution time with fallback strategies."""

    @staticmethod
    def calculate_execution_time(
        api_client: InternalAPIClient,
        execution_id: str,
        organization_id: str,
        fallback_results: list[dict[str, Any]] = None,
    ) -> float:
        """Calculate wall-clock execution time with multiple fallback strategies.

        Args:
            api_client: API client instance
            execution_id: Workflow execution ID
            organization_id: Organization context
            fallback_results: List of file results for summing as fallback

        Returns:
            Execution time in seconds
        """
        try:
            # Primary: Get workflow execution start time from backend
            return WallClockTimeCalculator._get_wall_clock_time(
                api_client, execution_id, organization_id
            )
        except Exception as e:
            logger.error(f"Error calculating wall-clock time: {e}")
            # Fallback: Sum individual file processing times
            return WallClockTimeCalculator._get_fallback_time(fallback_results or [])

    @staticmethod
    def _get_wall_clock_time(
        api_client: InternalAPIClient, execution_id: str, organization_id: str
    ) -> float:
        """Get wall-clock time from execution created_at timestamp."""
        execution_response = api_client.get_workflow_execution(
            execution_id, organization_id
        )

        if not (execution_response.success and execution_response.data):
            raise ValueError("Failed to get execution data from API")

        # DEBUG: Log the full API response to understand the issue
        logger.info(
            f"DEBUG: API response keys: {list(execution_response.data.keys()) if execution_response.data else 'None'}"
        )

        # Extract execution data from the nested structure
        execution_data = execution_response.data.get("execution", {})
        if not execution_data:
            logger.error(
                f"No 'execution' key in API response. Available keys: {list(execution_response.data.keys())}"
            )
            raise ValueError("No execution data found in API response")

        # Get created_at from the execution data
        created_at_str = execution_data.get("created_at")

        logger.info(
            f"DEBUG: Execution data keys: {list(execution_data.keys()) if execution_data else 'None'}"
        )
        logger.info(f"DEBUG: created_at value: {created_at_str}")

        if not created_at_str:
            logger.error(
                f"Missing timestamp field in API response. Available fields: {list(execution_response.data.keys())}"
            )
            # Don't raise error, let it fall back to file timing calculation
            raise ValueError("No created_at timestamp found in execution data")

        # Parse Django timestamp format
        created_at = WallClockTimeCalculator._parse_django_timestamp(created_at_str)

        # Calculate wall-clock execution time
        now = datetime.now(pytz.UTC)
        wall_clock_time = (now - created_at).total_seconds()

        logger.info(f"✅ Wall-clock execution time: {wall_clock_time:.2f}s")
        return wall_clock_time

    @staticmethod
    def _parse_django_timestamp(timestamp_str: str) -> datetime:
        """Parse Django timestamp format with timezone handling."""
        if timestamp_str.endswith("Z"):
            # UTC format: "2024-01-01T12:00:00.123456Z"
            return datetime.fromisoformat(timestamp_str[:-1]).replace(tzinfo=pytz.UTC)
        else:
            # Local format: "2024-01-01T12:00:00.123456"
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt

    @staticmethod
    def _get_fallback_time(file_results: list[dict[str, Any]]) -> float:
        """Calculate fallback time by summing individual file processing times."""
        if not file_results:
            logger.warning(
                "⚠️ No file results available for timing calculation, using default 30s"
            )
            return 30.0  # Reasonable default for pipeline execution

        # Try different possible field names for processing time
        fallback_time = 0.0
        for file_result in file_results:
            processing_time = (
                file_result.get("processing_time", 0)
                or file_result.get("execution_time", 0)
                or file_result.get("duration", 0)
                or file_result.get("time_taken", 0)
            )
            fallback_time += processing_time

        if fallback_time == 0.0:
            # If still no timing data, use reasonable estimate based on file count
            estimated_time = len(file_results) * 15.0  # ~15s per file estimate
            logger.warning(
                f"⚠️ No timing data in file results, estimating {estimated_time:.2f}s for {len(file_results)} files"
            )
            return estimated_time

        logger.warning(f"⚠️ Using fallback sum of file times: {fallback_time:.2f}s")
        return fallback_time


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
