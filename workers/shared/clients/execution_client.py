"""Execution API Client for Workflow Operations

This module provides specialized API client for workflow execution operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Workflow execution management
- Execution status updates
- File batch operations
- Pipeline operations
- Execution finalization
"""

import logging
import uuid
from typing import Any
from uuid import UUID

from ..data_models import (
    APIResponse,
    BatchOperationRequest,
    BatchOperationResponse,
    StatusUpdateRequest,
)
from ..enums import BatchOperationType, TaskStatus
from ..retry_utils import CircuitBreakerOpenError, circuit_breaker
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ExecutionAPIClient(BaseAPIClient):
    """Specialized API client for workflow execution operations.

    This client handles all workflow execution related operations including:
    - Getting workflow execution details
    - Updating execution status
    - Creating file batches
    - Managing pipeline status
    - Finalizing executions
    """

    def get_workflow_execution(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get workflow execution with context.

        Args:
            execution_id: Workflow execution ID
            organization_id: Optional organization ID override

        Returns:
            Workflow execution data
        """
        return self.get(
            self._build_url("workflow_execution", f"{str(execution_id)}/"),
            organization_id=organization_id,
        )

    def get_workflow_definition(
        self, workflow_id: str | uuid.UUID, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get workflow definition including workflow_type.

        Args:
            workflow_id: Workflow ID
            organization_id: Optional organization ID override

        Returns:
            Workflow definition data
        """
        try:
            # Use the workflow management internal API to get workflow details
            endpoint = f"workflow-manager/workflow/{str(workflow_id)}/"
            response = self.get(endpoint, organization_id=organization_id)
            logger.info(
                f"Retrieved workflow definition for {workflow_id}: {response.get('workflow_type', 'unknown')}"
            )
            return response
        except Exception as e:
            logger.error(f"Failed to get workflow definition for {workflow_id}: {str(e)}")
            # Return default structure if API call fails
            return {
                "id": str(workflow_id),
                "workflow_type": "ETL",  # Default to ETL
                "workflow_name": "Unknown",
                "error": str(e),
            }

    def get_pipeline_type(
        self, pipeline_id: str | uuid.UUID, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get pipeline type by checking APIDeployment and Pipeline models.

        Args:
            pipeline_id: Pipeline ID
            organization_id: Optional organization ID override

        Returns:
            Pipeline type information
        """
        try:
            # Use the internal API endpoint for pipeline type resolution
            endpoint = f"workflow-manager/pipeline-type/{str(pipeline_id)}/"
            response = self.get(endpoint, organization_id=organization_id)

            pipeline_type = response.get("pipeline_type", "ETL")
            source = response.get("source", "unknown")

            logger.debug(
                f"Retrieved pipeline type for {pipeline_id}: {pipeline_type} (from {source})"
            )
            return response

        except Exception as e:
            # This is expected for non-API deployments - pipeline endpoint doesn't exist
            logger.debug(
                f"Pipeline type API not available for {pipeline_id} (expected for ETL workflows): {str(e)}"
            )
            # Return default structure - this is normal behavior
            return {
                "pipeline_id": str(pipeline_id),
                "pipeline_type": "ETL",  # Default to ETL for non-API workflows
                "source": "fallback",
                "note": "Pipeline type API not available - defaulted to ETL",
            }

    def update_workflow_execution_status(
        self,
        execution_id: str | uuid.UUID,
        status: str | TaskStatus,
        error_message: str | None = None,
        total_files: int | None = None,
        attempts: int | None = None,
        execution_time: float | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Update workflow execution status.

        Args:
            execution_id: Execution ID
            status: New status (TaskStatus enum or string)
            error_message: Optional error message
            total_files: Optional total files count
            attempts: Optional attempts count
            execution_time: Optional execution time
            organization_id: Optional organization ID override

        Returns:
            APIResponse with update result
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        data = {"status": status_str}

        if error_message is not None:
            data["error_message"] = error_message
        if total_files is not None:
            data["total_files"] = total_files
        if attempts is not None:
            data["attempts"] = attempts
        if execution_time is not None:
            data["execution_time"] = execution_time

        response = self.post(
            self._build_url("workflow_execution", f"{str(execution_id)}/update_status/"),
            data,
            organization_id=organization_id,
        )

        return APIResponse(
            success=response.get("success", True),
            data=response,
            status_code=response.get("status_code"),
        )

    def batch_update_execution_status(
        self,
        updates: list[dict[str, Any] | StatusUpdateRequest],
        organization_id: str | None = None,
    ) -> BatchOperationResponse:
        """Update multiple execution statuses in a single request.

        Args:
            updates: List of StatusUpdateRequest objects or dictionaries
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with results
        """
        # Convert updates to dictionaries if they are dataclasses
        update_dicts = []
        for update in updates:
            if isinstance(update, StatusUpdateRequest):
                update_dicts.append(update.to_dict())
            else:
                update_dicts.append(update)

        batch_request = BatchOperationRequest(
            operation_type=BatchOperationType.STATUS_UPDATE,
            items=update_dicts,
            organization_id=organization_id,
        )

        response = self.post(
            "workflow-manager/batch-status-update/",
            batch_request.to_dict(),
            organization_id=organization_id,
        )

        return BatchOperationResponse(
            operation_id=response.get("operation_id", str(uuid.uuid4())),
            total_items=len(updates),
            successful_items=response.get("successful_items", 0),
            failed_items=response.get("failed_items", 0),
            status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
            results=response.get("results", []),
            errors=response.get("errors", []),
            execution_time=response.get("execution_time"),
        )

    def create_file_batch(
        self,
        workflow_execution_id: str | uuid.UUID,
        files: list,
        is_api: bool = False,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Create file execution batch.

        Args:
            workflow_execution_id: Workflow execution ID
            files: List of files to process
            is_api: Whether this is an API execution
            organization_id: Optional organization ID override

        Returns:
            File batch creation response
        """
        data = {
            "workflow_execution_id": str(workflow_execution_id),
            "files": files,
            "is_api": is_api,
        }
        return self.post(
            "workflow-manager/file-batch/", data, organization_id=organization_id
        )

    def get_workflow_endpoints(
        self, workflow_id: str | UUID, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get workflow endpoints for a specific workflow.

        Args:
            workflow_id: Workflow ID to get endpoints for
            organization_id: Optional organization ID override

        Returns:
            Dictionary with endpoint data including 'endpoints' list and 'has_api_endpoints' flag
        """
        # Use the workflow-manager endpoint pattern
        endpoint = f"workflow-manager/{workflow_id}/endpoint/"

        try:
            response = self._make_request(
                method="GET",
                endpoint=endpoint,
                timeout=self.config.api_timeout,
                organization_id=organization_id,
            )

            # The API returns a dict with 'endpoints', 'has_api_endpoints', etc.
            if isinstance(response, dict):
                endpoint_count = len(response.get("endpoints", []))
                logger.debug(
                    f"Retrieved {endpoint_count} endpoints for workflow {workflow_id}"
                )
                return response
            else:
                logger.warning(
                    f"Unexpected response format for workflow endpoints: {type(response)}"
                )
                return {"endpoints": [], "has_api_endpoints": False, "total_endpoints": 0}

        except Exception as e:
            logger.error(f"Failed to get workflow endpoints for {workflow_id}: {str(e)}")
            return {"endpoints": [], "has_api_endpoints": False, "total_endpoints": 0}

    @circuit_breaker(failure_threshold=3, recovery_timeout=60.0)
    def update_pipeline_status(
        self,
        pipeline_id: str | UUID,
        execution_id: str | UUID,
        status: str | TaskStatus,
        organization_id: str | None = None,
        **kwargs,
    ) -> APIResponse:
        """Update pipeline status.

        Args:
            pipeline_id: Pipeline ID
            execution_id: Execution ID
            status: New status
            organization_id: Optional organization ID override

        Returns:
            Update response
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        data = {
            "execution_id": str(execution_id),
            "status": status_str,
            **kwargs,  # Include any additional parameters like last_run_status
        }

        try:
            # Use the workflow-manager pipeline endpoint for status updates
            endpoint = f"workflow-manager/pipeline/{pipeline_id}/status/"

            response = self._make_request(
                method="POST",
                endpoint=endpoint,
                data=data,
                timeout=self.config.api_timeout,
                organization_id=organization_id,
            )

            logger.debug(f"Updated pipeline {pipeline_id} status to {status_str}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to update pipeline {pipeline_id} status: {str(e)}")
            return APIResponse(success=False, error=str(e))

    @circuit_breaker(failure_threshold=3, recovery_timeout=120.0)
    def finalize_workflow_execution(
        self,
        execution_id: str | uuid.UUID,
        final_status: str | TaskStatus = TaskStatus.SUCCESS,
        total_files_processed: int | None = None,
        total_execution_time: float = 0.0,
        results_summary: dict[str, Any] | None = None,
        error_summary: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Finalize workflow execution with organization context.

        Args:
            execution_id: Execution ID to finalize
            final_status: Final execution status
            total_files_processed: Number of files processed
            total_execution_time: Total execution time in seconds
            results_summary: Summary of results
            error_summary: Summary of errors
            organization_id: Optional organization ID override

        Returns:
            Finalization response
        """
        # Convert status to string if it's an enum
        final_status_str = (
            final_status.value if isinstance(final_status, TaskStatus) else final_status
        )

        data = {
            "final_status": final_status_str,
            "total_execution_time": total_execution_time,
            "results_summary": results_summary or {},
            "error_summary": error_summary or {},
        }

        # Only include total_files_processed if explicitly provided and positive
        if total_files_processed is not None and total_files_processed > 0:
            data["total_files_processed"] = total_files_processed

        # Include organization context if provided
        if organization_id:
            data["organization_id"] = organization_id
            logger.debug(
                f"Including organization_id {organization_id} in finalization request"
            )

        try:
            response = self.post(
                self._build_url("execution", f"finalize/{str(execution_id)}/"),
                data,
                organization_id=organization_id,
            )
            logger.debug(f"Finalization API call successful for execution {execution_id}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )
        except CircuitBreakerOpenError:
            logger.warning(
                "Finalization endpoint circuit breaker open - using fallback status update"
            )
            # Circuit breaker is open, use fallback immediately
            return self.update_workflow_execution_status(
                execution_id=str(execution_id), status=final_status_str
            )
        except Exception as e:
            logger.error(
                f"Finalization API call failed for execution {execution_id}: {str(e)}"
            )
            # Check for specific error patterns that require fallback
            error_str = str(e)
            if any(
                pattern in error_str
                for pattern in [
                    "'WorkflowExecution' object has no attribute 'organization_id'",
                    "too many error responses",
                    "500 Internal Server Error",
                    "503 Service Unavailable",
                    "502 Bad Gateway",
                ]
            ):
                logger.warning(
                    f"Known backend error detected - using fallback status update: {error_str[:100]}..."
                )
                # Fallback to simple status update that avoids the problematic backend code path
                return self.update_workflow_execution_status(
                    execution_id=str(execution_id), status=final_status_str
                )
            else:
                raise e

    @circuit_breaker(failure_threshold=2, recovery_timeout=30.0)
    def cleanup_execution_resources(
        self, execution_ids: list[str | uuid.UUID], cleanup_types: list | None = None
    ) -> dict[str, Any]:
        """Cleanup execution resources.

        Args:
            execution_ids: List of execution IDs to cleanup
            cleanup_types: Types of cleanup to perform

        Returns:
            Cleanup response
        """
        data = {
            "execution_ids": [str(eid) for eid in execution_ids],
            "cleanup_types": cleanup_types or ["cache", "temp_files"],
        }
        return self.post(self._build_url("execution", "cleanup/"), data)

    def get_execution_finalization_status(
        self, execution_id: str | uuid.UUID
    ) -> dict[str, Any]:
        """Get execution finalization status.

        Args:
            execution_id: Execution ID

        Returns:
            Finalization status
        """
        return self.get(
            self._build_url("execution", f"finalization-status/{str(execution_id)}/")
        )

    def increment_completed_files(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Increment completed files count for execution.

        Args:
            workflow_id: Workflow ID
            execution_id: Execution ID

        Returns:
            Increment response
        """
        data = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "increment_type": "completed",
        }
        try:
            response = self.post("workflow-manager/increment-files/", data)
            logger.debug(f"Incremented completed files for execution {execution_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to increment completed files: {str(e)}")
            return {"success": False, "error": str(e)}

    def increment_failed_files(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Increment failed files count for execution.

        Args:
            workflow_id: Workflow ID
            execution_id: Execution ID

        Returns:
            Increment response
        """
        data = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "increment_type": "failed",
        }
        try:
            response = self.post("workflow-manager/increment-files/", data)
            logger.debug(f"Incremented failed files for execution {execution_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to increment failed files: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_workflow_destination_config(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any]:
        """Get destination configuration for workflow execution.

        Args:
            workflow_id: Workflow ID
            execution_id: Execution ID

        Returns:
            Destination configuration
        """
        try:
            # Use workflow execution endpoint to get destination config
            response = self.get(f"workflow-manager/{execution_id}/")
            # Extract destination_config from the response
            if isinstance(response, dict) and "destination_config" in response:
                logger.debug(f"Retrieved destination config for workflow {workflow_id}")
                return response["destination_config"]
            # Fallback for backward compatibility
            logger.debug(f"Retrieved full response for workflow {workflow_id}")
            return response
        except Exception as e:
            logger.error(f"Failed to get destination config: {str(e)}")
            return {"type": "none", "error": str(e)}

    def create_file_history_entry(self, history_data: dict[str, Any]) -> dict[str, Any]:
        """Create file history entry for deduplication.

        Args:
            history_data: File history data including workflow_id, cache_key, etc.

        Returns:
            Creation response
        """
        try:
            # Use the internal workflow-manager file-history endpoint
            response = self.post("workflow-manager/file-history/create/", history_data)
            logger.debug(
                f"Created file history entry for {history_data.get('file_name', 'unknown')}"
            )
            return response
        except Exception as e:
            logger.error(f"Failed to create file history entry: {str(e)}")
            return {"created": False, "error": str(e)}

    def check_file_history_batch(
        self, workflow_id: str, file_hashes: list[str], organization_id: str
    ) -> dict[str, Any]:
        """Check file history for multiple files in batch.

        Args:
            workflow_id: Workflow ID
            file_hashes: List of file hashes to check
            organization_id: Organization ID

        Returns:
            Batch check response with processed_file_hashes list
        """
        try:
            data = {
                "workflow_id": workflow_id,
                "file_hashes": file_hashes,
                "organization_id": organization_id,
            }
            response = self.post("workflow-manager/file-history/check-batch/", data)
            logger.debug(f"Checked file history for {len(file_hashes)} files")
            return response
        except Exception as e:
            logger.error(f"Failed to check file history batch: {str(e)}")
            return {"processed_file_hashes": []}
