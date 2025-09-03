"""Backward Compatibility Facade for Internal API Client

This facade provides backward compatibility for existing code that imports from
the original api_client.py. It delegates calls to the specialized modular clients
while maintaining the same interface.

This maintains the original InternalAPIClient interface by composing all the
specialized clients (ExecutionAPIClient, FileAPIClient, etc.) into a single
unified interface.
"""

import logging
import uuid
from typing import Any
from uuid import UUID

# Manual review functionality loaded via plugin registry
from client_plugin_registry import get_client_plugin

from ...cache import CachedAPIClientMixin, with_cache
from ...cache.cache_types import CacheType
from ...clients import (
    BaseAPIClient,
    ExecutionAPIClient,
    FileAPIClient,
    OrganizationAPIClient,
    ToolAPIClient,
    WebhookAPIClient,
)

# Import exceptions from base client
# Re-export exceptions for backward compatibility
from ...clients.base_client import (
    APIRequestError,
    AuthenticationError,
    InternalAPIClientError,
)
from ...clients.manual_review_stub import ManualReviewNullClient
from ...data.response_models import APIResponse
from ...enums import HTTPMethod
from ...infrastructure.config.worker_config import WorkerConfig

# Import new API response dataclasses for type safety
from ...models.api_responses import (
    FileBatchResponse,
    FileHistoryResponse,
    ToolInstancesResponse,
    WorkflowDefinitionResponse,
    WorkflowEndpointsResponse,
    WorkflowExecutionResponse,
)

# Import execution models for type-safe execution contexts
# Import notification models for type-safe notifications
from ...models.notification_models import (
    WebhookNotificationRequest,
)
from ...models.scheduler_models import SchedulerExecutionResult

# Re-export shared dataclasses for backward compatibility
# Note: These would be imported from unstract.core.data_models in production
try:
    from unstract.core.data_models import (
        FileExecutionCreateRequest,
        FileExecutionStatusUpdateRequest,
        FileHashData,
        WorkflowFileExecutionData,
    )
except ImportError:
    # Mock classes for testing when unstract.core is not available
    class MockDataClass:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def to_dict(self):
            return dict(self.__dict__.items())

        @classmethod
        def from_dict(cls, data):
            return cls(**data)

        def ensure_hash(self):
            # Mock implementation - no hash computation needed for testing
            pass

        def validate_for_api(self):
            # Mock implementation - no validation needed for testing
            pass

    WorkflowFileExecutionData = MockDataClass
    FileHashData = MockDataClass
    FileExecutionCreateRequest = MockDataClass
    FileExecutionStatusUpdateRequest = MockDataClass

logger = logging.getLogger(__name__)


class InternalAPIClient(CachedAPIClientMixin):
    """Backward compatibility facade for the original monolithic InternalAPIClient.

    This class provides the same interface as the original InternalAPIClient
    but delegates all operations to the specialized modular clients with caching support.
    This ensures existing code continues to work without modification while benefiting from
    both the improved modular architecture and caching for better performance.
    """

    # Class-level shared base client for singleton pattern
    _shared_base_client = None
    _shared_session = None
    _initialization_count = 0

    def __init__(self, config: WorkerConfig | None = None):
        """Initialize the facade with all specialized clients and caching.

        Args:
            config: Worker configuration. If None, uses default config.
        """
        self.config = config or WorkerConfig()

        # Initialize caching (parent class)
        super().__init__()

        # Initialize core clients
        self._initialize_core_clients()

        # Initialize plugin clients
        self._initialize_plugin_clients()

        # Setup direct access references
        self._setup_direct_access_references()

        logger.info(
            "Initialized InternalAPIClient facade with modular architecture and caching"
        )

    def _initialize_core_clients(self) -> None:
        """Initialize all core API clients with performance optimizations."""
        if self.config.enable_api_client_singleton:
            self._initialize_core_clients_optimized()
        else:
            self._initialize_core_clients_traditional()

    def _initialize_core_clients_optimized(self) -> None:
        """Initialize clients using singleton pattern for better performance."""
        InternalAPIClient._initialization_count += 1

        # Create or reuse shared session and configuration
        if InternalAPIClient._shared_session is None:
            if self.config.debug_api_client_init:
                logger.info("Creating shared HTTP session (singleton pattern)")
            # Create the first base client to establish the session
            self.base_client = BaseAPIClient(self.config)
            # Share the session for reuse
            InternalAPIClient._shared_session = self.base_client.session
            InternalAPIClient._shared_base_client = self.base_client
        else:
            if self.config.debug_api_client_init:
                logger.info(
                    f"Reusing shared HTTP session (#{InternalAPIClient._initialization_count})"
                )
            # Create base client and replace its session with shared one
            self.base_client = BaseAPIClient(self.config)
            self.base_client.session.close()  # Close the new session
            self.base_client.session = (
                InternalAPIClient._shared_session
            )  # Use shared session

        # Create specialized clients with shared session
        self.execution_client = ExecutionAPIClient(self.config)
        self.execution_client.session.close()
        self.execution_client.session = InternalAPIClient._shared_session

        self.file_client = FileAPIClient(self.config)
        self.file_client.session.close()
        self.file_client.session = InternalAPIClient._shared_session

        self.webhook_client = WebhookAPIClient(self.config)
        self.webhook_client.session.close()
        self.webhook_client.session = InternalAPIClient._shared_session

        self.organization_client = OrganizationAPIClient(self.config)
        self.organization_client.session.close()
        self.organization_client.session = InternalAPIClient._shared_session

        self.tool_client = ToolAPIClient(self.config)
        self.tool_client.session.close()
        self.tool_client.session = InternalAPIClient._shared_session

    def _initialize_core_clients_traditional(self) -> None:
        """Initialize clients the traditional way (for backward compatibility)."""
        if self.config.debug_api_client_init:
            logger.info(
                "Using traditional API client initialization (6 separate instances)"
            )
        self.base_client = BaseAPIClient(self.config)
        self.execution_client = ExecutionAPIClient(self.config)
        self.file_client = FileAPIClient(self.config)
        self.webhook_client = WebhookAPIClient(self.config)
        self.organization_client = OrganizationAPIClient(self.config)
        self.tool_client = ToolAPIClient(self.config)

    def _initialize_plugin_clients(self) -> None:
        """Initialize plugin-based clients with error handling."""
        self.manual_review_client = self._load_manual_review_client()
        logger.debug(
            f"Manual review client type: {type(self.manual_review_client).__name__}"
        )

    def _load_manual_review_client(self) -> Any:
        """Load manual review client via plugin registry with fallback.

        Returns:
            ManualReviewClient or ManualReviewNullClient
        """
        try:
            plugin_instance = get_client_plugin("manual_review", self.config)
            if plugin_instance:
                logger.debug("Using manual review plugin from registry")
                return plugin_instance
            else:
                logger.debug("Manual review plugin not available, using null client")
                return ManualReviewNullClient(self.config)
        except Exception as e:
            logger.warning(f"Failed to load manual review plugin, using null client: {e}")
            return ManualReviewNullClient(self.config)

    def _setup_direct_access_references(self) -> None:
        """Setup direct access references for backward compatibility."""
        self.base_url = self.base_client.base_url
        self.api_key = self.base_client.api_key
        self.organization_id = self.base_client.organization_id
        self.session = self.base_client.session

    # Delegate base client methods
    def health_check(self) -> dict[str, Any]:
        """Check API health status."""
        return self.base_client.health_check()

    def close(self):
        """Close all HTTP sessions."""
        self.base_client.close()
        self.execution_client.close()
        self.file_client.close()
        self.webhook_client.close()
        self.organization_client.close()
        self.tool_client.close()

        # Close manual review client (plugin or null client)
        if hasattr(self.manual_review_client, "close"):
            self.manual_review_client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # Delegate execution client methods
    def get_workflow_executions_by_status(
        self,
        workflow_id: str | uuid.UUID,
        statuses: list[str],
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get workflow executions by status for a specific workflow.

        This gets ALL executions for a workflow that match the given statuses,
        matching the backend logic in source.py _get_active_workflow_executions().

        Args:
            workflow_id: Workflow ID
            statuses: List of status values (e.g., ['PENDING', 'EXECUTING'])
            organization_id: Optional organization ID override

        Returns:
            APIResponse with workflow executions data
        """
        try:
            # Use workflow execution endpoint with status filtering (trailing slash required by Django)
            response_data = self._make_request(
                method=HTTPMethod.GET,
                endpoint="v1/workflow-execution/",
                params={
                    "workflow_id": str(workflow_id),
                    "status__in": ",".join(statuses),  # Multiple status filter
                },
                organization_id=organization_id,
            )

            # Backend now properly filters by workflow_id and status parameters
            if isinstance(response_data, list):
                logger.info(
                    f"DEBUG: Backend returned {len(response_data)} executions for workflow {workflow_id} with statuses {statuses}"
                )
            else:
                logger.warning(
                    f"DEBUG: Expected list response but got {type(response_data)}"
                )

            # Wrap filtered response data in APIResponse
            return APIResponse(
                success=True,
                data=response_data,
            )

        except Exception as e:
            logger.error(f"Error getting workflow executions by status: {e}")
            return APIResponse(
                success=False,
                error=str(e),
            )

    def check_files_active_processing(
        self,
        workflow_id: str | uuid.UUID,
        provider_file_uuids: list[str],
        current_execution_id: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Check if specific files are being processed in PENDING/EXECUTING workflow executions.

        Optimized single API call instead of querying all executions and their file executions.

        Args:
            workflow_id: Workflow ID to check
            provider_file_uuids: List of provider file UUIDs to check
            current_execution_id: Current execution ID to exclude from active check
            organization_id: Optional organization ID override

        Returns:
            APIResponse with {provider_uuid: is_active} mapping
        """
        try:
            # Single optimized API call to check multiple files at once
            response_data = self._make_request(
                method=HTTPMethod.POST,
                endpoint="v1/workflow-manager/file-execution/check-active",
                data={
                    "workflow_id": str(workflow_id),
                    "provider_file_uuids": provider_file_uuids,
                    "statuses": ["PENDING", "EXECUTING"],
                    "exclude_execution_id": str(current_execution_id)
                    if current_execution_id
                    else None,
                },
                organization_id=organization_id,
            )

            return APIResponse(
                success=True,
                data=response_data,
            )

        except Exception as e:
            logger.error(f"Error checking files active processing: {e}")
            # Fallback: assume no files are active to avoid blocking
            return APIResponse(
                success=True,
                data={"active_uuids": []},
            )

    def get_workflow_file_executions_by_execution(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get WorkflowFileExecutions for a specific execution using internal API.

        This uses the existing /internal/api/v1/file-execution/?execution_id=<id> endpoint
        to get all file executions for a workflow execution.

        Args:
            execution_id: Workflow execution ID
            organization_id: Optional organization ID override

        Returns:
            APIResponse with file executions data
        """
        try:
            response = self._make_request(
                method=HTTPMethod.GET,
                url=f"{self.base_url}/v1/file-execution/",
                params={"execution_id": str(execution_id)},
                organization_id=organization_id,
            )

            return response

        except Exception as e:
            logger.error(f"Error getting workflow file executions: {e}")
            return APIResponse(
                success=False,
                error=str(e),
            )

    def get_workflow_execution(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> WorkflowExecutionResponse:
        """Get workflow execution with context."""
        response = self.execution_client.get_workflow_execution(
            execution_id, organization_id
        )
        # Convert ExecutionResponse to WorkflowExecutionResponse for type safety
        if hasattr(response, "to_dict"):
            response_dict = response.to_dict()
        else:
            response_dict = response
        return WorkflowExecutionResponse.from_api_response(response_dict)

    @with_cache(
        CacheType.WORKFLOW,
        lambda self, workflow_id, organization_id=None: str(workflow_id),
    )
    def get_workflow_definition(
        self, workflow_id: str | uuid.UUID, organization_id: str | None = None
    ) -> WorkflowDefinitionResponse:
        """Get workflow definition including workflow_type.

        This method automatically uses caching through the @with_cache decorator.
        """
        # Direct API call - caching is handled by decorator
        response = self.execution_client.get_workflow_definition(
            workflow_id, organization_id
        )
        # Convert to WorkflowDefinitionResponse for type safety
        if hasattr(response, "to_dict"):
            response_dict = response.to_dict()
        else:
            response_dict = response
        return WorkflowDefinitionResponse.from_api_response(response_dict)

    def get_pipeline_type(
        self, pipeline_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get pipeline type by checking APIDeployment and Pipeline models."""
        return self.execution_client.get_pipeline_type(pipeline_id, organization_id)

    def get_pipeline_data(
        self,
        pipeline_id: str | uuid.UUID,
        check_active: bool = True,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get pipeline data by checking APIDeployment and Pipeline models.

        Args:
            pipeline_id: Pipeline ID
            check_active: Whether to check if pipeline is active (default: True)
            organization_id: Optional organization ID override

        Returns:
            APIResponse containing pipeline data
        """
        return self.execution_client.get_pipeline_data(
            pipeline_id=pipeline_id,
            check_active=check_active,
            organization_id=organization_id,
        )

    @with_cache(
        CacheType.API_DEPLOYMENT, lambda self, api_id, organization_id=None: str(api_id)
    )
    def get_api_deployment_data(
        self, api_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get APIDeployment data directly from v1 API deployment endpoint.

        This method is optimized for callback workers that know they're dealing
        with API deployments. It queries APIDeployment model directly.
        Caching is handled automatically through the @with_cache decorator.
        """
        # Direct API call - caching is handled by decorator
        return self.execution_client.get_api_deployment_data(api_id, organization_id)

    def update_workflow_execution_status(
        self,
        execution_id: str | uuid.UUID,
        status: str,
        error_message: str | None = None,
        total_files: int | None = None,
        attempts: int | None = None,
        execution_time: float | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update workflow execution status."""
        return self.execution_client.update_workflow_execution_status(
            execution_id,
            status,
            error_message,
            total_files,
            attempts,
            execution_time,
            organization_id,
        )

    def create_workflow_execution(self, execution_data: dict[str, Any]) -> dict[str, Any]:
        """Create workflow execution."""
        return self.execution_client.create_workflow_execution(execution_data)

    @with_cache(
        CacheType.TOOL_INSTANCES, lambda self, workflow_id, organization_id: workflow_id
    )
    def get_tool_instances_by_workflow(
        self, workflow_id: str, organization_id: str
    ) -> ToolInstancesResponse:
        """Get tool instances for a workflow.

        Caching is handled automatically through the @with_cache decorator.
        """
        # Direct API call - caching is handled by decorator
        response = self.execution_client.get_tool_instances_by_workflow(
            workflow_id, organization_id
        )
        # Convert to ToolInstancesResponse for type safety
        return ToolInstancesResponse.from_api_response(response)

    def compile_workflow(
        self, workflow_id: str, execution_id: str, organization_id: str
    ) -> dict[str, Any]:
        """Compile workflow."""
        return self.execution_client.compile_workflow(
            workflow_id, execution_id, organization_id
        )

    def submit_file_batch_for_processing(
        self, batch_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit file batch for processing."""
        return self.execution_client.submit_file_batch_for_processing(batch_data)

    def execute_workflow_async(self, execution_data: dict[str, Any]) -> dict[str, Any]:
        """Execute workflow asynchronously for scheduler.

        This method triggers async workflow execution by dispatching to the
        appropriate Celery task via internal API.

        Args:
            execution_data: Execution parameters including workflow_id, execution_id, etc.

        Returns:
            Dictionary with execution results
        """
        try:
            # Use the internal API to trigger async workflow execution
            # This replaces the Celery send_task("async_execute_bin") call from backend
            response = self.execution_client.post(
                "v1/workflow-manager/execute-async/",
                execution_data,
                organization_id=execution_data.get("organization_id"),
            )

            if isinstance(response, dict) and response.get("success"):
                return {
                    "success": True,
                    "execution_id": response.get("execution_id"),
                    "task_id": response.get("task_id"),
                    "message": "Async workflow execution started",
                }
            else:
                return {
                    "success": False,
                    "error": response.get("error", "Failed to start async execution"),
                }
        except Exception as e:
            logger.error(f"Error starting async workflow execution: {e}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
            }

    def execute_workflow_async_typed(
        self, async_request: Any
    ) -> SchedulerExecutionResult:
        """Type-safe async workflow execution for scheduler using dataclasses.

        Args:
            async_request: AsyncExecutionRequest dataclass with execution parameters

        Returns:
            SchedulerExecutionResult with execution status and details
        """
        try:
            # Convert dataclass to dict for API call
            execution_data = async_request.to_dict()

            # Use the internal API to trigger async workflow execution
            response = self.execution_client.post(
                "v1/workflow-manager/execute-async/",
                execution_data,
                organization_id=async_request.organization_id,
            )

            if isinstance(response, dict) and response.get("success"):
                return SchedulerExecutionResult.success(
                    execution_id=async_request.execution_id,
                    workflow_id=async_request.workflow_id,
                    pipeline_id=async_request.pipeline_id,
                    task_id=response.get("task_id"),
                    message="Async workflow execution started successfully",
                )
            else:
                return SchedulerExecutionResult.error(
                    error=response.get("error", "Failed to start async execution"),
                    execution_id=async_request.execution_id,
                    workflow_id=async_request.workflow_id,
                    pipeline_id=async_request.pipeline_id,
                )
        except Exception as e:
            logger.error(f"Error starting async workflow execution: {e}")
            return SchedulerExecutionResult.error(
                error=f"API error: {str(e)}",
                execution_id=async_request.execution_id,
                workflow_id=async_request.workflow_id,
                pipeline_id=async_request.pipeline_id,
            )

    def batch_update_execution_status(
        self, updates: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Update multiple execution statuses in a single request."""
        # Validate that we have updates to process
        if not updates:
            return {
                "success": True,
                "message": "No updates provided",
                "total_items": 0,
                "successful_items": 0,
                "failed_items": 0,
            }

        result = self.execution_client.batch_update_execution_status(
            updates, organization_id
        )

        # Convert BatchOperationResponse to dict for consistency
        if hasattr(result, "to_dict"):
            response_dict = result.to_dict()
            # Add success field for backward compatibility
            response_dict["success"] = (
                result.status == "SUCCESS" or result.successful_items > 0
            )
            return response_dict
        else:
            return result

    def create_file_batch(
        self,
        workflow_execution_id: str | uuid.UUID,
        files: list,
        is_api: bool = False,
        organization_id: str | None = None,
    ) -> FileBatchResponse:
        """Create file execution batch."""
        response = self.execution_client.create_file_batch(
            workflow_execution_id, files, is_api, organization_id
        )
        # Convert to FileBatchResponse for type safety
        return FileBatchResponse.from_api_response(response)

    @with_cache(
        CacheType.WORKFLOW_ENDPOINTS,
        lambda self, workflow_id, organization_id=None: str(workflow_id),
    )
    def get_workflow_endpoints(
        self, workflow_id: str | UUID, organization_id: str | None = None
    ) -> WorkflowEndpointsResponse:
        """Get workflow endpoints for a specific workflow.

        Caching is handled automatically through the @with_cache decorator.
        """
        # Direct API call - caching is handled by decorator
        response = self.execution_client.get_workflow_endpoints(
            workflow_id, organization_id
        )
        # Convert to WorkflowEndpointsResponse for type safety
        return WorkflowEndpointsResponse.from_api_response(response)

    def update_pipeline_status(
        self,
        pipeline_id: str | UUID,
        status: str,
        organization_id: str | None = None,
        execution_id: str | UUID | None = None,  # Optional for backward compatibility
        **kwargs,
    ) -> dict[str, Any]:
        """Update pipeline status with flexible parameters."""
        return self.execution_client.update_pipeline_status(
            pipeline_id, status, organization_id, execution_id, **kwargs
        ).data

    def batch_update_pipeline_status(
        self, updates: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Update multiple pipeline statuses in a single request.

        For now, this processes updates individually until a batch endpoint is available.
        """
        results = {"success": True, "updated": 0, "errors": []}

        for update in updates:
            try:
                pipeline_id = update.pop("pipeline_id")
                execution_id = update.pop("execution_id")
                status = update.pop("status")

                # Call individual update with remaining kwargs (last_run_time, last_run_status, etc)
                self.update_pipeline_status(
                    pipeline_id=pipeline_id,
                    status=status,
                    organization_id=organization_id,
                    execution_id=execution_id,  # Pass as optional parameter
                    **update,
                )
                results["updated"] += 1
            except Exception as e:
                results["errors"].append({"pipeline_id": pipeline_id, "error": str(e)})
                results["success"] = False

        return results

    def finalize_workflow_execution(
        self,
        execution_id: str | uuid.UUID,
        final_status: str = "COMPLETED",
        total_files_processed: int | None = None,
        total_execution_time: float = 0.0,
        results_summary: dict[str, Any] | None = None,
        error_summary: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Finalize workflow execution with organization context."""
        return self.execution_client.finalize_workflow_execution(
            execution_id,
            final_status,
            total_files_processed,
            total_execution_time,
            results_summary,
            error_summary,
            organization_id,
        )

    def cleanup_execution_resources(
        self, execution_ids: list[str | uuid.UUID], cleanup_types: list | None = None
    ) -> dict[str, Any]:
        """Cleanup execution resources."""
        return self.execution_client.cleanup_execution_resources(
            execution_ids, cleanup_types
        )

    def get_execution_finalization_status(
        self, execution_id: str | uuid.UUID
    ) -> dict[str, Any]:
        """Get execution finalization status."""
        return self.execution_client.get_execution_finalization_status(execution_id)

    def increment_completed_files(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Increment completed files count for execution."""
        return self.execution_client.increment_completed_files(workflow_id, execution_id)

    def increment_failed_files(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Increment failed files count for execution."""
        return self.execution_client.increment_failed_files(workflow_id, execution_id)

    def get_workflow_destination_config(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Get destination configuration for workflow execution."""
        return self.execution_client.get_workflow_destination_config(
            workflow_id, execution_id
        )

    # Delegate file client methods
    def get_workflow_file_execution(
        self, file_execution_id: str | UUID, organization_id: str | None = None
    ) -> WorkflowFileExecutionData:
        """Get an existing workflow file execution by ID."""
        return self.file_client.get_workflow_file_execution(
            file_execution_id, organization_id
        )

    def get_or_create_workflow_file_execution(
        self,
        execution_id: str | UUID,
        file_hash: dict[str, Any] | FileHashData,
        workflow_id: str | UUID,
        organization_id: str | None = None,
        force_create: bool = False,
    ) -> WorkflowFileExecutionData:
        """Get or create a workflow file execution record using shared dataclasses."""
        return self.file_client.get_or_create_workflow_file_execution(
            execution_id, file_hash, workflow_id, organization_id, force_create
        )

    def update_workflow_file_execution_hash(
        self,
        file_execution_id: str | UUID,
        file_hash: str,
        fs_metadata: dict[str, Any] | None = None,
        mime_type: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update workflow file execution with computed file hash and mime_type."""
        return self.file_client.update_workflow_file_execution_hash(
            file_execution_id, file_hash, fs_metadata, mime_type, organization_id
        )

    def update_file_execution_status(
        self,
        file_execution_id: str | UUID,
        status: str,
        execution_time: float | None = None,
        error_message: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update workflow file execution status with execution time."""
        return self.file_client.update_file_execution_status(
            file_execution_id, status, execution_time, error_message, organization_id
        )

    def update_workflow_file_execution_status(
        self,
        file_execution_id: str,
        status: str,
        result: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update WorkflowFileExecution status via internal API using shared dataclasses."""
        return self.file_client.update_workflow_file_execution_status(
            file_execution_id, status, result, error_message
        )

    def update_file_status_to_executing(
        self,
        file_execution_id: str | UUID | None,
        file_name: str,
        organization_id: str | None = None,
    ) -> bool:
        """Common method to update file execution status to EXECUTING with proper error handling.

        This method provides consistent logging and error handling for updating file execution
        status to EXECUTING across all workflow types (ETL, TASK, API).

        Args:
            file_execution_id: File execution ID to update
            file_name: File name for logging purposes
            organization_id: Optional organization ID override

        Returns:
            bool: True if update successful, False otherwise
        """
        if not file_execution_id:
            logger.warning(
                f"DEBUG: No file_execution_id for file {file_name}, cannot update status to EXECUTING"
            )
            return False

        try:
            from unstract.core.data_models import ExecutionStatus

            logger.info(
                f"DEBUG: About to update file {file_name} (ID: {file_execution_id}) status to EXECUTING"
            )
            result = self.update_file_execution_status(
                file_execution_id=file_execution_id,
                status=ExecutionStatus.EXECUTING.value,
                organization_id=organization_id,
            )
            logger.info(
                f"DEBUG: Updated file {file_name} status to EXECUTING - API result: {result}"
            )
            return True

        except Exception as status_error:
            logger.error(
                f"CRITICAL: Failed to update file {file_name} (ID: {file_execution_id}) status to EXECUTING: {status_error}"
            )
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def create_workflow_file_execution(
        self,
        workflow_execution_id: str,
        file_name: str,
        file_path: str,
        file_hash: str,
        file_execution_id: str | None = None,
        file_size: int = 0,
        mime_type: str = "",
        provider_file_uuid: str | None = None,
        fs_metadata: dict[str, Any] | None = None,
        status: str = "QUEUED",
    ) -> dict[str, Any]:
        """Create WorkflowFileExecution record via internal API with complete metadata."""
        return self.file_client.create_workflow_file_execution(
            workflow_execution_id,
            file_name,
            file_path,
            file_hash,
            file_execution_id,
            file_size,
            mime_type,
            provider_file_uuid,
            fs_metadata,
            status,
        )

    def batch_create_file_executions(
        self, file_executions: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Create multiple file executions in a single batch request."""
        return self.file_client.batch_create_file_executions(
            file_executions, organization_id
        )

    def batch_update_file_execution_status(
        self, status_updates: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Update multiple file execution statuses in a single batch request."""
        return self.file_client.batch_update_file_execution_status(
            status_updates, organization_id
        )

    def get_file_history_by_cache_key(
        self, cache_key: str, workflow_id: str | uuid.UUID, file_path: str | None = None
    ) -> dict[str, Any]:
        """Get file history by cache key."""
        return self.file_client.get_file_history_by_cache_key(
            cache_key, workflow_id, file_path
        )

    def reserve_file_processing(
        self,
        workflow_id: str | uuid.UUID,
        cache_key: str,
        provider_file_uuid: str | None = None,
        file_path: str | None = None,
        worker_id: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomic check-and-reserve operation for file processing deduplication."""
        result = self.file_client.reserve_file_processing(
            workflow_id,
            cache_key,
            provider_file_uuid,
            file_path,
            worker_id,
            organization_id,
        )
        return (
            result.data if result.success else {"reserved": False, "error": result.error}
        )

    def create_file_history(
        self,
        workflow_id: str | uuid.UUID,
        file_name: str,
        file_path: str,
        result: str | None = None,
        metadata: str | None = None,
        status: str = "COMPLETED",
        error: str | None = None,
        provider_file_uuid: str | None = None,
        is_api: bool = False,
        file_size: int = 0,
        file_hash: str = "",
        mime_type: str = "",
    ) -> dict[str, Any]:
        """Create file history record matching backend expected format."""
        return self.file_client.create_file_history(
            workflow_id,
            file_name,
            file_path,
            result,
            metadata,
            status,
            error,
            provider_file_uuid,
            is_api,
            file_size,
            file_hash,
            mime_type,
        )

    def get_file_history_status(self, file_history_id: str | uuid.UUID) -> dict[str, Any]:
        """Get file history status."""
        return self.file_client.get_file_history_status(file_history_id)

    def get_file_history(
        self,
        workflow_id: str | uuid.UUID,
        provider_file_uuid: str | None = None,
        file_hash: str | None = None,
        file_path: str | None = None,
        organization_id: str | None = None,
    ) -> FileHistoryResponse:
        """Get file history by provider_file_uuid or file_hash.

        This unified method handles both lookup patterns:
        1. By provider_file_uuid (for cloud storage files with unique IDs)
        2. By file_hash (content-based deduplication)

        Args:
            workflow_id: Workflow ID to check file history for
            provider_file_uuid: Provider file UUID to search for (cloud storage)
            file_hash: File content hash to search for (content-based)
            file_path: Optional file path for additional filtering
            organization_id: Organization ID for context

        Returns:
            FileHistoryResponse with file_history data
        """
        # If file_hash is provided, use the existing cache key lookup
        if file_hash and not provider_file_uuid:
            response = self.get_file_history_by_cache_key(
                cache_key=file_hash, workflow_id=workflow_id, file_path=file_path
            )
            return FileHistoryResponse.from_api_response(response)

        # Otherwise, use provider_file_uuid lookup
        endpoint = "v1/file-history/get/"

        payload = {
            "workflow_id": str(workflow_id),
            "provider_file_uuid": provider_file_uuid,
            "file_path": file_path,
            "organization_id": organization_id or self.organization_id,
        }

        try:
            response = self.base_client._make_request(
                method="POST",
                endpoint=endpoint,
                data=payload,
                timeout=self.base_client.config.api_timeout,
                organization_id=organization_id,
            )

            logger.debug(
                f"File history lookup for provider_file_uuid {provider_file_uuid}: "
                f"{'found' if response.get('file_history') else 'not found'}"
            )
            return FileHistoryResponse.from_api_response(response)

        except Exception as e:
            logger.error(
                f"Failed to get file history for workflow {workflow_id}, "
                f"provider_file_uuid {provider_file_uuid}: {str(e)}"
            )
            # Return empty result to continue without breaking the flow
            return FileHistoryResponse(success=False, error=str(e))

    def batch_create_file_history(
        self, file_histories: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Create multiple file history records in a single batch request."""
        return self.file_client.batch_create_file_history(file_histories, organization_id)

    # Delegate webhook client methods
    def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        notification_id: str | None = None,
        authorization_type: str = "NONE",
        authorization_key: str | None = None,
        authorization_header: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send webhook notification to external endpoint."""
        return self.webhook_client.send_webhook(
            url,
            payload,
            notification_id,
            authorization_type,
            authorization_key,
            authorization_header,
            timeout,
            max_retries,
            retry_delay,
            headers,
        )

    def send_webhook_notification(
        self,
        notification_request: WebhookNotificationRequest,
    ) -> dict[str, Any]:
        """Send webhook notification using type-safe NotificationRequest dataclass.

        Args:
            notification_request: WebhookNotificationRequest dataclass with notification details

        Returns:
            Dictionary with webhook response data
        """
        return self.webhook_client.send_webhook(
            url=notification_request.url,
            payload=notification_request.payload,
            notification_id=notification_request.notification_id,
            authorization_type=notification_request.authorization_type,
            authorization_key=notification_request.authorization_key,
            authorization_header=notification_request.authorization_header,
            timeout=notification_request.timeout,
            max_retries=notification_request.max_retries,
            retry_delay=notification_request.retry_delay,
            headers=notification_request.headers,
        )

    def get_webhook_status(self, task_id: str) -> dict[str, Any]:
        """Get webhook delivery status by task ID."""
        return self.webhook_client.get_webhook_status(task_id)

    def test_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        authorization_type: str = "NONE",
        authorization_key: str | None = None,
        authorization_header: str | None = None,
        timeout: int = 10,
    ) -> dict[str, Any]:
        """Test webhook configuration and connectivity."""
        return self.webhook_client.test_webhook(
            url,
            payload,
            authorization_type,
            authorization_key,
            authorization_header,
            timeout,
        )

    # Delegate tool client methods (removing duplicates)
    def get_tool_instances_by_workflow_tool_client(
        self, workflow_id: str | uuid.UUID
    ) -> dict[str, Any]:
        """Get tool instances for a workflow using tool client."""
        # Use the tool client for consistency
        result = self.tool_client.get_tool_instances_by_workflow(workflow_id)
        return result.data if hasattr(result, "data") else result

    # File history methods
    def check_file_history_batch(
        self,
        workflow_id: str | uuid.UUID,
        file_hashes: list[str],
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Check file history for a batch of file hashes.

        Args:
            workflow_id: Workflow ID to check file history for
            file_hashes: List of file hashes to check
            organization_id: Organization ID for context (optional)

        Returns:
            Dictionary with 'processed_file_hashes' list
        """
        endpoint = "v1/workflow-manager/file-history/check-batch/"

        payload = {
            "workflow_id": str(workflow_id),
            "file_hashes": file_hashes,
            "organization_id": organization_id or self.organization_id,
        }

        try:
            response = self.base_client._make_request(
                method="POST",
                endpoint=endpoint,
                data=payload,
                timeout=self.base_client.config.api_timeout,
                organization_id=organization_id,
            )

            logger.debug(
                f"File history batch check for {len(file_hashes)} hashes: {len(response.get('processed_file_hashes', []))} already processed"
            )
            return response

        except Exception as e:
            logger.error(
                f"Failed to check file history batch for workflow {workflow_id}: {str(e)}"
            )
            # Return empty result to continue without file history filtering
            return {"processed_file_hashes": []}

    # Delegate organization client methods
    def get_organization_context(self, org_id: str) -> dict[str, Any]:
        """Get organization context and metadata."""
        return self.organization_client.get_organization_context(org_id)

    def set_organization_context(self, org_id: str):
        """Set organization context for subsequent requests."""
        # Update context on all clients
        self.base_client.set_organization_context(org_id)
        self.execution_client.set_organization_context(org_id)
        self.file_client.set_organization_context(org_id)
        self.webhook_client.set_organization_context(org_id)
        self.organization_client.set_organization_context(org_id)
        self.tool_client.set_organization_context(org_id)

        # Note: Manual review org context handled by plugins

        # Update facade attributes
        self.organization_id = org_id

        logger.debug(f"Set organization context to {org_id} on all clients")

    def clear_organization_context(self):
        """Clear organization context."""
        # Clear context on all clients
        self.base_client.clear_organization_context()
        self.execution_client.clear_organization_context()
        self.file_client.clear_organization_context()
        self.webhook_client.clear_organization_context()
        self.organization_client.clear_organization_context()
        self.tool_client.clear_organization_context()

        # Note: Manual review org context clearing handled by plugins

        # Update facade attributes
        self.organization_id = None

        logger.debug("Cleared organization context on all clients")

    # Manual review functionality is handled by enterprise plugins, not exposed in OSS API client

    # Delegate tool client methods (consolidated)
    def execute_tool(
        self,
        tool_instance_id: str | uuid.UUID,
        input_data: dict[str, Any],
        file_data: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool instance with provided data."""
        result = self.tool_client.execute_tool(
            tool_instance_id, input_data, file_data, execution_context
        )
        return result.data if hasattr(result, "data") else result

    def get_tool_execution_status(self, execution_id: str | uuid.UUID) -> dict[str, Any]:
        """Get tool execution status by execution ID."""
        result = self.tool_client.get_tool_execution_status(execution_id)
        return result.data if hasattr(result, "data") else result

    def get_tool_by_id(self, tool_id: str | uuid.UUID) -> dict[str, Any]:
        """Get tool information by tool ID."""
        return self.base_client.get(
            self.base_client._build_url("tool_execution", f"tool/{str(tool_id)}/")
        )

    # HTTP method helpers (delegate to base client)
    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Make GET request."""
        return self.base_client.get(endpoint, params, organization_id)

    def post(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make POST request."""
        return self.base_client.post(endpoint, data, organization_id)

    def put(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make PUT request."""
        return self.base_client.put(endpoint, data, organization_id)

    def patch(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make PATCH request."""
        return self.base_client.patch(endpoint, data, organization_id)

    def delete(self, endpoint: str, organization_id: str | None = None) -> dict[str, Any]:
        """Make DELETE request."""
        return self.base_client.delete(endpoint, organization_id)

    # Private helpers for internal access
    def _build_url(self, endpoint_key: str, path: str = "") -> str:
        """Build consistent API URL using endpoint patterns."""
        return self.base_client._build_url(endpoint_key, path)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Enhanced HTTP request with robust error handling and retry logic."""
        return self.base_client._make_request(
            method,
            endpoint,
            data,
            params,
            timeout,
            max_retries,
            backoff_factor,
            organization_id,
        )

    def get_endpoint_config(self) -> dict[str, str]:
        """Get current API endpoint configuration for debugging."""
        return self.base_client.get_endpoint_config()

    # Manual Review API methods (delegated to ManualReviewAPIClient)
    def validate_manual_review_db_rule(
        self,
        execution_result: Any,
        workflow_id: str | UUID,
        file_destination: str | None = None,
        organization_id: str | None = None,
    ) -> bool:
        """Validate if document should go to manual review based on DB rules."""
        return self.manual_review_client.validate_manual_review_db_rule(
            execution_result=execution_result,
            workflow_id=workflow_id,
            file_destination=file_destination,
            organization_id=organization_id,
        )

    def enqueue_manual_review(
        self,
        queue_name: str,
        message: dict[str, Any],
        organization_id: str | None = None,
    ) -> bool:
        """Enqueue document for manual review."""
        return self.manual_review_client.enqueue_manual_review(
            queue_name=queue_name,
            message=message,
            organization_id=organization_id,
        )

    def route_to_manual_review(
        self,
        file_execution_id: str,
        file_data: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Route file to manual review queue (delegates to manual review client)."""
        return self.manual_review_client.route_to_manual_review(
            file_execution_id=file_execution_id,
            file_data=file_data,
            workflow_id=workflow_id,
            execution_id=execution_id,
            organization_id=organization_id or self.organization_id,
        )

    def route_to_manual_review_with_results(
        self,
        file_execution_id: str,
        file_data: dict[str, Any],
        workflow_result: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        organization_id: str | None = None,
        file_name: str = "unknown",
    ) -> dict[str, Any]:
        """Route file to manual review with tool execution results (delegates to manual review client)."""
        return self.manual_review_client.route_with_results(
            file_execution_id=file_execution_id,
            file_data=file_data,
            workflow_result=workflow_result,
            workflow_id=workflow_id,
            execution_id=execution_id,
            organization_id=organization_id or self.organization_id,
            file_name=file_name,
        )

    # Configuration client methods
    def get_configuration(
        self,
        config_key: str,
        organization_id: str | None = None,
    ) -> "APIResponse":
        """Get organization configuration value.

        Args:
            config_key: Configuration key name (e.g., "MAX_PARALLEL_FILE_BATCHES")
            organization_id: Organization ID (uses client default if not provided)

        Returns:
            APIResponse with configuration data
        """
        try:
            response = self._make_request(
                method=HTTPMethod.GET,
                endpoint=f"v1/configuration/{config_key}/",
                params={"organization_id": organization_id or self.organization_id},
            )

            return response

        except Exception as e:
            logger.error(f"Error getting configuration {config_key}: {e}")
            from .data.models import APIResponse

            return APIResponse(
                success=False,
                error=str(e),
            )

    # Export all classes and exceptions for backward compatibility
    # =============================
    # CACHE MANAGEMENT UTILITIES
    # =============================
    # These methods provide cache management without overriding existing methods
    # The caching happens transparently in the execution client methods

    def get_api_cache_stats(self) -> dict[str, Any]:
        """Get API client cache statistics."""
        if hasattr(self, "_cache") and self._cache.backend.available:
            return self.get_cache_stats()
        return {"available": False, "message": "Cache not available"}

    def clear_api_cache_stats(self):
        """Clear API client cache statistics."""
        if hasattr(self, "_cache") and self._cache.backend.available:
            self.clear_cache_stats()

    def invalidate_workflow_related_cache(self, workflow_id: str):
        """Invalidate all cache entries related to a workflow."""
        if hasattr(self, "_cache") and self._cache.backend.available:
            self.invalidate_workflow_cache(workflow_id)
            logger.info(f"Invalidated all cache entries for workflow {workflow_id}")
        else:
            logger.debug(
                f"Cache not available, skipping invalidation for workflow {workflow_id}"
            )


__all__ = [
    # Main facade class
    "InternalAPIClient",
    # Exceptions
    "InternalAPIClientError",
    "APIRequestError",
    "AuthenticationError",
    # Data models
    "WorkflowFileExecutionData",
    "FileHashData",
    "FileExecutionCreateRequest",
    "FileExecutionStatusUpdateRequest",
]
