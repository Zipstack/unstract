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

from .clients import (
    BaseAPIClient,
    ExecutionAPIClient,
    FileAPIClient,
    OrganizationAPIClient,
    ToolAPIClient,
    WebhookAPIClient,
)

# Import exceptions from base client
# Re-export exceptions for backward compatibility
from .clients.base_client import (
    APIRequestError,
    AuthenticationError,
    InternalAPIClientError,
)
from .clients.manual_review_stub import ManualReviewNullClient
from .config import WorkerConfig
from .response_models import APIResponse, ExecutionResponse

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
            return {k: v for k, v in self.__dict__.items()}

        @classmethod
        def from_dict(cls, data):
            return cls(**data)

        def ensure_hash(self):
            pass

        def validate_for_api(self):
            pass

    WorkflowFileExecutionData = MockDataClass
    FileHashData = MockDataClass
    FileExecutionCreateRequest = MockDataClass
    FileExecutionStatusUpdateRequest = MockDataClass

logger = logging.getLogger(__name__)


class InternalAPIClient:
    """Backward compatibility facade for the original monolithic InternalAPIClient.

    This class provides the same interface as the original InternalAPIClient
    but delegates all operations to the specialized modular clients. This ensures
    existing code continues to work without modification while benefiting from
    the improved modular architecture.
    """

    def __init__(self, config: WorkerConfig | None = None):
        """Initialize the facade with all specialized clients.

        Args:
            config: Worker configuration. If None, uses default config.
        """
        self.config = config or WorkerConfig()

        # Initialize all specialized clients
        self.base_client = BaseAPIClient(config)
        self.execution_client = ExecutionAPIClient(config)
        self.file_client = FileAPIClient(config)
        self.webhook_client = WebhookAPIClient(config)
        self.organization_client = OrganizationAPIClient(config)
        self.tool_client = ToolAPIClient(config)

        # Initialize manual review client via plugin registry
        # The registry handles both Django settings and worker-specific plugin loading
        try:
            plugin_instance = get_client_plugin("manual_review", config)
            if plugin_instance:
                self.manual_review_client = plugin_instance
                logger.debug("Using manual review plugin from registry")
            else:
                self.manual_review_client = ManualReviewNullClient(config)
                logger.debug("Manual review plugin not available, using null client")
        except Exception as e:
            logger.warning(f"Failed to load manual review plugin, using null client: {e}")
            self.manual_review_client = ManualReviewNullClient(config)

        logger.debug(
            f"Manual review client type: {type(self.manual_review_client).__name__}"
        )

        # Store references for direct access if needed
        self.base_url = self.base_client.base_url
        self.api_key = self.base_client.api_key
        self.organization_id = self.base_client.organization_id
        self.session = self.base_client.session

        logger.info("Initialized InternalAPIClient facade with modular architecture")

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
    def get_workflow_execution(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> ExecutionResponse:
        """Get workflow execution with context."""
        return self.execution_client.get_workflow_execution(execution_id, organization_id)

    def get_workflow_definition(
        self, workflow_id: str | uuid.UUID, organization_id: str | None = None
    ) -> ExecutionResponse:
        """Get workflow definition including workflow_type."""
        return self.execution_client.get_workflow_definition(workflow_id, organization_id)

    def get_pipeline_type(
        self, pipeline_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get pipeline type by checking APIDeployment and Pipeline models."""
        return self.execution_client.get_pipeline_type(pipeline_id, organization_id)

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

    def get_tool_instances_by_workflow(
        self, workflow_id: str, organization_id: str
    ) -> dict[str, Any]:
        """Get tool instances for a workflow."""
        return self.execution_client.get_tool_instances_by_workflow(
            workflow_id, organization_id
        )

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
    ) -> dict[str, Any]:
        """Create file execution batch."""
        return self.execution_client.create_file_batch(
            workflow_execution_id, files, is_api, organization_id
        )

    def get_workflow_endpoints(
        self, workflow_id: str | UUID, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get workflow endpoints for a specific workflow."""
        return self.execution_client.get_workflow_endpoints(workflow_id, organization_id)

    def update_pipeline_status(
        self,
        pipeline_id: str | UUID,
        execution_id: str | UUID,
        status: str,
        organization_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Update pipeline status with flexible parameters."""
        return self.execution_client.update_pipeline_status(
            pipeline_id, execution_id, status, organization_id, **kwargs
        )

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
                    execution_id=execution_id,
                    status=status,
                    organization_id=organization_id,
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
    ) -> WorkflowFileExecutionData:
        """Get or create a workflow file execution record using shared dataclasses."""
        return self.file_client.get_or_create_workflow_file_execution(
            execution_id, file_hash, workflow_id, organization_id
        )

    def update_workflow_file_execution_hash(
        self,
        file_execution_id: str | UUID,
        file_hash: str,
        fs_metadata: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update workflow file execution with computed file hash."""
        return self.file_client.update_workflow_file_execution_hash(
            file_execution_id, file_hash, fs_metadata, organization_id
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
    ) -> dict[str, Any]:
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
            Dictionary with file_history data or empty dict if not found
        """
        # If file_hash is provided, use the existing cache key lookup
        if file_hash and not provider_file_uuid:
            return self.get_file_history_by_cache_key(
                cache_key=file_hash, workflow_id=workflow_id, file_path=file_path
            )

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
            return response

        except Exception as e:
            logger.error(
                f"Failed to get file history for workflow {workflow_id}, "
                f"provider_file_uuid {provider_file_uuid}: {str(e)}"
            )
            # Return empty result to continue without breaking the flow
            return {}

    def batch_create_file_history(
        self, file_histories: list[dict[str, Any]], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Create multiple file history records in a single batch request."""
        return self.file_client.batch_create_file_history(file_histories, organization_id)

    def create_file_history_entry(self, history_data: dict[str, Any]) -> dict[str, Any]:
        """Create a file history entry via internal API.

        Args:
            history_data: Dictionary containing file history data

        Returns:
            Creation result dictionary
        """
        endpoint = "workflow-manager/file-history/create/"

        try:
            response = self.base_client._make_request(
                method="POST",
                endpoint=endpoint,
                data=history_data,
                timeout=self.base_client.config.api_timeout,
            )

            logger.debug(
                f"Created file history entry for file {history_data.get('file_name', 'unknown')}"
            )
            return response

        except Exception as e:
            logger.error(f"Failed to create file history entry: {str(e)}")
            # Return empty result to continue without breaking the flow
            return {"created": False, "error": str(e)}

    # Delegate webhook client methods
    def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        notification_id: str | None = None,
        authorization_type: str = "none",
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
        endpoint = "workflow-manager/file-history/check-batch/"

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


# Export all classes and exceptions for backward compatibility
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
