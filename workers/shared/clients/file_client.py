"""File API Client for File Operations

This module provides specialized API client for file-related operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- File execution management
- File history operations
- File batch operations
- File status updates
- File metadata management
"""

import logging
import uuid
from typing import Any
from uuid import UUID

from ..constants.api_endpoints import build_internal_endpoint
from ..data.models import (
    APIResponse,
    BatchOperationRequest,
    BatchOperationResponse,
    StatusUpdateRequest,
)
from ..enums import BatchOperationType, TaskStatus
from .base_client import APIRequestError, BaseAPIClient

# Note: These would be imported from unstract.core.data_models in production
# For now, using mock classes for testing
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


class FileAPIClient(BaseAPIClient):
    """Specialized API client for file-related operations.

    This client handles all file-related operations including:
    - File execution management
    - File history operations
    - File metadata management
    - File batch operations
    - File status updates
    """

    def get_workflow_file_execution(
        self, file_execution_id: str | UUID, organization_id: str | None = None
    ) -> WorkflowFileExecutionData:
        """Get an existing workflow file execution by ID.

        Args:
            file_execution_id: File execution ID
            organization_id: Optional organization ID override

        Returns:
            WorkflowFileExecutionData instance
        """
        # Build URL for file execution detail endpoint
        url = build_internal_endpoint(f"file-execution/{file_execution_id}/").lstrip("/")

        # Get the file execution record
        response_data = self.client.get(url, organization_id=organization_id)

        # Convert to WorkflowFileExecutionData
        return WorkflowFileExecutionData.from_dict(response_data)

    def get_or_create_workflow_file_execution(
        self,
        execution_id: str | UUID,
        file_hash: dict[str, Any] | FileHashData,
        workflow_id: str | UUID,
        organization_id: str | None = None,
        force_create: bool = False,
    ) -> WorkflowFileExecutionData:
        """Get or create a workflow file execution record using shared dataclasses.

        Args:
            execution_id: Execution ID
            file_hash: File hash data (dict or FileHashData)
            workflow_id: Workflow ID
            organization_id: Optional organization ID override
            force_create: If True, skip lookup and always create new record

        Returns:
            WorkflowFileExecutionData instance
        """
        # Convert file_hash to FileHashData if it's a dict
        if isinstance(file_hash, dict):
            file_hash_data = FileHashData.from_dict(file_hash)
        else:
            file_hash_data = file_hash

        # Debug logging to understand API file detection
        logger.info(
            f"FileHashData debug: file_name='{file_hash_data.file_name}', "
            f"has_hash={file_hash_data.has_hash()}, "
            f"source_connection_type='{getattr(file_hash_data, 'source_connection_type', None)}'"
        )

        # CRITICAL FIX: For API files with pre-calculated hash, skip hash computation
        # to prevent temporary MD5 path hash generation
        if (
            file_hash_data.has_hash()
            and getattr(file_hash_data, "source_connection_type", None) == "API"
        ):
            logger.info(
                f"API file with pre-calculated hash: {file_hash_data.file_hash[:16]}... - skipping validation"
            )
        else:
            # For non-API files or files without hash, we'd need content/path to compute hash
            # For now, just validate what we have
            logger.info(
                f"Non-API file or file without hash: {file_hash_data.file_name} - proceeding with validation"
            )

            # Enhanced validation with detailed error reporting
            try:
                file_hash_data.validate_for_api()
            except ValueError as e:
                logger.error(f"FileHashData validation failed: {str(e)}")
                logger.error(
                    f"FileHashData details: file_name='{file_hash_data.file_name}', "
                    f"file_path='{file_hash_data.file_path}', "
                    f"file_hash='{file_hash_data.file_hash[:16]}...', "
                    f"provider_file_uuid='{file_hash_data.provider_file_uuid}'"
                )

                # Provide actionable error message based on validation failure
                if not file_hash_data.file_name:
                    raise APIRequestError(
                        "File name is required for WorkflowFileExecution creation"
                    )
                elif not file_hash_data.file_path:
                    raise APIRequestError(
                        "File path is required for WorkflowFileExecution creation"
                    )
                else:
                    raise APIRequestError(
                        f"FileHashData validation failed: {str(e)}. "
                        f"Check file path accessibility and connector configuration."
                    ) from e

        # First try to get existing record - CRITICAL FIX: Match backend manager logic
        params = {
            "execution_id": str(execution_id),
            "workflow_id": str(workflow_id),
            "file_path": file_hash_data.file_path,  # CRITICAL: Include file_path to match unique constraints
        }

        # Match backend manager logic: use file_hash OR provider_file_uuid (not both)
        if file_hash_data.file_hash:
            params["file_hash"] = file_hash_data.file_hash
            logger.info(f"DEBUG: Using file_hash for lookup: {file_hash_data.file_hash}")
        elif file_hash_data.provider_file_uuid:
            params["provider_file_uuid"] = file_hash_data.provider_file_uuid
            logger.info(
                f"DEBUG: Using provider_file_uuid for lookup: {file_hash_data.provider_file_uuid}"
            )
        else:
            logger.warning(
                "No file_hash or provider_file_uuid available for lookup - this may cause issues"
            )

        logger.debug(f"Lookup parameters: {params}")

        if not force_create:
            try:
                # Try to get existing record
                response = self.get(
                    self._build_url("file_execution"),
                    params=params,
                    organization_id=organization_id,
                )
                if response and isinstance(response, list) and len(response) > 0:
                    logger.debug(
                        f"Found existing workflow file execution: {response[0].get('id')}"
                    )
                    return WorkflowFileExecutionData.from_dict(response[0])
            except Exception as e:
                logger.debug(f"Could not get existing workflow file execution: {str(e)}")
                # Continue to create if not found
        else:
            logger.debug("Force create enabled - skipping existing record lookup")

        # Create request using shared dataclass
        create_request = FileExecutionCreateRequest(
            execution_id=execution_id, file_hash=file_hash_data, workflow_id=workflow_id
        )

        data = create_request.to_dict()

        logger.info(
            f"Creating workflow file execution with file_hash: {file_hash_data.file_name}"
        )
        logger.info(
            f"FileHashData key identifiers: provider_file_uuid='{file_hash_data.provider_file_uuid}', "
            f"file_path='{file_hash_data.file_path}', file_hash='{file_hash_data.file_hash}'"
        )
        logger.debug(f"FileHashData: {file_hash_data.to_dict()}")

        try:
            result = self.post(
                self._build_url("file_execution"), data, organization_id=organization_id
            )

            # Handle both list and dict responses (defensive programming)
            if isinstance(result, list):
                logger.warning(
                    f"Backend returned list instead of dict for file execution create: {len(result)} items"
                )
                if len(result) > 0:
                    file_execution_dict = result[0]  # Take first item from list
                    logger.info(
                        f"Successfully created workflow file execution: {file_execution_dict.get('id') if isinstance(file_execution_dict, dict) else 'unknown'}"
                    )
                    return WorkflowFileExecutionData.from_dict(file_execution_dict)
                else:
                    logger.error("Backend returned empty list for file execution create")
                    raise APIRequestError(
                        "Backend returned empty list for file execution create"
                    )
            elif isinstance(result, dict):
                file_execution_id = result.get("id", "unknown")
                logger.info(
                    f"Successfully created workflow file execution: {file_execution_id}"
                )
                logger.info(
                    f"Created for file: {file_hash_data.file_name} with provider_file_uuid: {file_hash_data.provider_file_uuid}"
                )
                return WorkflowFileExecutionData.from_dict(result)
            else:
                logger.error(
                    f"Backend returned unexpected type for file execution create: {type(result)}"
                )
                raise APIRequestError(
                    f"Backend returned unexpected response type: {type(result)}"
                )
        except Exception as e:
            logger.error(
                f"Failed to create workflow file execution: {str(e)}", exc_info=True
            )
            logger.debug(f"Request data was: {data}")
            raise

    def update_workflow_file_execution_hash(
        self,
        file_execution_id: str | UUID,
        file_hash: str,
        fs_metadata: dict[str, Any] | None = None,
        mime_type: str | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Update workflow file execution with computed file hash and mime_type.

        This method should be used when the SHA256 content hash is computed
        after the WorkflowFileExecution record is initially created.

        Args:
            file_execution_id: ID of the WorkflowFileExecution record to update
            file_hash: Computed SHA256 hash of file content
            fs_metadata: Optional filesystem metadata to update
            mime_type: Optional MIME type to update
            organization_id: Optional organization ID override

        Returns:
            Updated WorkflowFileExecution data
        """
        data = {"file_hash": file_hash}
        if fs_metadata:
            data["fs_metadata"] = fs_metadata
        if mime_type:
            data["mime_type"] = mime_type

        logger.info(
            f"Updating file execution {file_execution_id} with computed hash: {file_hash[:16]}..."
        )

        try:
            response = self.patch(
                self._build_url(
                    "file_execution", f"{str(file_execution_id)}/update_hash/"
                ),
                data,
                organization_id=organization_id,
            )

            logger.info(
                f"Successfully updated file execution {file_execution_id} with hash"
            )
            return response

        except Exception as e:
            logger.error(f"Failed to update file execution hash: {str(e)}")
            raise APIRequestError(
                f"Failed to update file execution hash: {str(e)}"
            ) from e

    def update_file_execution_status(
        self,
        file_execution_id: str | UUID,
        status: str | TaskStatus,
        execution_time: float | None = None,
        error_message: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Update workflow file execution status with execution time.

        This method updates the WorkflowFileExecution record with status and execution time,
        matching the Django model's update_status() method behavior.

        Args:
            file_execution_id: ID of the WorkflowFileExecution record to update
            status: New execution status (TaskStatus enum or string)
            execution_time: Execution time in seconds (optional)
            error_message: Error message if status is ERROR (optional)
            organization_id: Optional organization ID override

        Returns:
            APIResponse with update result
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        data = {"status": status_str}

        if execution_time is not None:
            data["execution_time"] = execution_time
        if error_message is not None:
            data["error_message"] = error_message

        # DEBUG: Log what we're sending to the backend
        logger.info(f"DEBUG: FileClient sending data to backend: {data}")

        logger.info(
            f"Updating file execution {file_execution_id} status to {status_str}"
            f"{f' with execution_time {execution_time:.2f}s' if execution_time else ''}"
        )

        try:
            response = self.post(
                self._build_url("file_execution", f"{str(file_execution_id)}/status/"),
                data,
                organization_id=organization_id,
            )

            logger.info(f"Successfully updated file execution {file_execution_id} status")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to update file execution status: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def update_workflow_file_execution_status(
        self,
        file_execution_id: str,
        status: str | TaskStatus,
        result: str | None = None,
        error_message: str | None = None,
    ) -> APIResponse:
        """Update WorkflowFileExecution status via internal API using shared dataclasses.

        Args:
            file_execution_id: File execution ID
            status: New status (TaskStatus enum or string)
            result: Execution result (optional)
            error_message: Error message if any

        Returns:
            APIResponse with update result
        """
        try:
            # Convert status to string if it's an enum
            status_str = status.value if isinstance(status, TaskStatus) else status

            # Create status update request using shared dataclass
            update_request = FileExecutionStatusUpdateRequest(
                status=status_str, error_message=error_message, result=result
            )

            # Use the internal file execution status endpoint
            endpoint = self._build_url("file_execution", f"{file_execution_id}/status/")
            response = self.post(endpoint, update_request.to_dict())

            logger.info(
                f"Successfully updated WorkflowFileExecution {file_execution_id} status to {status_str}"
            )
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(
                f"Failed to update WorkflowFileExecution status for {file_execution_id}: {str(e)}"
            )
            # Don't raise exception to avoid breaking worker flow
            return APIResponse(success=False, error=str(e))

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
        status: str | TaskStatus = TaskStatus.PENDING,
    ) -> APIResponse:
        """Create WorkflowFileExecution record via internal API with complete metadata.

        Uses the existing backend endpoint that expects file_hash object format.
        Now supports all the fields needed for proper file hash generation.

        Args:
            workflow_execution_id: Workflow execution ID
            file_name: File name
            file_path: File path
            file_hash: Actual computed SHA256 file hash (not dummy)
            file_execution_id: Optional unique file execution ID
            file_size: File size in bytes
            mime_type: File MIME type
            provider_file_uuid: Provider-specific file UUID
            fs_metadata: File system metadata
            status: Initial status

        Returns:
            Created WorkflowFileExecution data
        """
        try:
            # Convert status to string if it's an enum
            status_str = status.value if isinstance(status, TaskStatus) else status

            # Format data to match backend WorkflowFileExecutionAPIView expectations
            data = {
                "execution_id": workflow_execution_id,
                "workflow_id": workflow_execution_id,  # Will be extracted from execution
                "file_hash": {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_hash": file_hash,  # Actual computed hash
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "provider_file_uuid": provider_file_uuid,
                    "fs_metadata": fs_metadata or {},
                    "is_executed": False,
                },
                "status": status_str,
            }

            # Include file_execution_id if provided
            if file_execution_id:
                data["file_execution_id"] = file_execution_id

            # Log the actual hash being used
            if file_hash:
                logger.info(
                    f"Creating WorkflowFileExecution with actual hash {file_hash} for {file_name}"
                )
            else:
                logger.warning(
                    f"Creating WorkflowFileExecution with empty hash for {file_name}"
                )

            response = self.post("v1/workflow-manager/file-execution/", data)
            logger.info(
                f"Successfully created WorkflowFileExecution for {file_name} with hash {file_hash[:8] if file_hash else 'empty'}..."
            )
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )
        except Exception as e:
            logger.error(f"Failed to create WorkflowFileExecution: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def batch_create_file_executions(
        self, file_executions: list[dict[str, Any]], organization_id: str | None = None
    ) -> BatchOperationResponse:
        """Create multiple file executions in a single batch request.

        Args:
            file_executions: List of file execution data dictionaries
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with results
        """
        batch_request = BatchOperationRequest(
            operation_type=BatchOperationType.CREATE,
            items=file_executions,
            organization_id=organization_id,
        )

        response = self.post(
            "v1/workflow-manager/file-execution/batch-create/",
            batch_request.to_dict(),
            organization_id=organization_id,
        )

        return BatchOperationResponse(
            operation_id=response.get("operation_id", str(uuid.uuid4())),
            total_items=len(file_executions),
            successful_items=response.get("successful_items", 0),
            failed_items=response.get("failed_items", 0),
            status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
            results=response.get("results", []),
            errors=response.get("errors", []),
            execution_time=response.get("execution_time"),
        )

    def batch_update_file_execution_status(
        self,
        status_updates: list[dict[str, Any] | StatusUpdateRequest],
        organization_id: str | None = None,
    ) -> BatchOperationResponse:
        """Update multiple file execution statuses in a single batch request.

        Args:
            status_updates: List of StatusUpdateRequest objects or dictionaries
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with results
        """
        # Convert updates to dictionaries if they are dataclasses
        update_dicts = []
        for update in status_updates:
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
            "v1/workflow-manager/file-execution/batch-status-update/",
            batch_request.to_dict(),
            organization_id=organization_id,
        )

        return BatchOperationResponse(
            operation_id=response.get("operation_id", str(uuid.uuid4())),
            total_items=len(status_updates),
            successful_items=response.get("successful_items", 0),
            failed_items=response.get("failed_items", 0),
            status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
            results=response.get("results", []),
            errors=response.get("errors", []),
            execution_time=response.get("execution_time"),
        )

    # File History API methods
    def get_file_history_by_cache_key(
        self, cache_key: str, workflow_id: str | uuid.UUID, file_path: str | None = None
    ) -> dict[str, Any]:
        """Get file history by cache key.

        Args:
            cache_key: Cache key to look up
            workflow_id: Workflow ID
            file_path: Optional file path

        Returns:
            File history data
        """
        params = {"workflow_id": str(workflow_id)}
        if file_path:
            params["file_path"] = file_path
        return self.get(
            self._build_url("file_history", f"cache-key/{cache_key}/"), params=params
        )

    def reserve_file_processing(
        self,
        workflow_id: str | UUID,
        cache_key: str,
        provider_file_uuid: str | None = None,
        file_path: str | None = None,
        worker_id: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Atomic check-and-reserve operation for file processing deduplication.

        This method handles race conditions by atomically checking if a file
        should be processed and reserving it if not already processed/reserved.

        Args:
            workflow_id: Workflow ID
            cache_key: File cache key (usually file hash or provider UUID)
            provider_file_uuid: Provider file UUID (optional)
            file_path: File path (optional)
            worker_id: Unique worker identifier (optional)
            organization_id: Optional organization ID override

        Returns:
            APIResponse with reservation result containing:
            - reserved: bool - Whether file was reserved for this worker
            - already_processed: bool - Whether file was already processed
            - already_reserved: bool - Whether file was already reserved by another worker
            - file_history: dict - Existing file history if already processed
        """
        data = {"workflow_id": str(workflow_id), "cache_key": cache_key}

        if provider_file_uuid:
            data["provider_file_uuid"] = provider_file_uuid
        if file_path:
            data["file_path"] = file_path
        if worker_id:
            data["worker_id"] = worker_id

        logger.info(
            f"Reserving file processing for workflow {workflow_id}, cache_key: {cache_key[:16]}..."
        )

        try:
            response = self.post(
                self._build_url("file_history", "reserve/"),
                data,
                organization_id=organization_id,
            )

            return APIResponse(
                success=response.get("reserved", False)
                or response.get("already_processed", False),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to reserve file processing: {str(e)}")
            raise APIRequestError(f"Failed to reserve file processing: {str(e)}") from e

    def create_file_history(
        self,
        workflow_id: str | uuid.UUID,
        file_name: str,
        file_path: str,
        result: str | None = None,
        metadata: str | None = None,
        status: str | TaskStatus = TaskStatus.SUCCESS,
        error: str | None = None,
        provider_file_uuid: str | None = None,
        is_api: bool = False,
        file_size: int = 0,
        file_hash: str = "",
        mime_type: str = "",
    ) -> APIResponse:
        """Create file history record matching backend expected format.

        Args:
            workflow_id: Workflow ID
            file_name: File name
            file_path: File path
            result: Execution result
            metadata: File metadata
            status: Execution status
            error: Error message if any
            provider_file_uuid: Provider-specific file UUID
            is_api: Whether this is an API execution
            file_size: File size in bytes
            file_hash: File hash
            mime_type: File MIME type

        Returns:
            Created file history data
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        # Build file_hash object as expected by backend
        file_hash_data = {
            "file_name": file_name,
            "file_path": file_path,
            "file_size": file_size,
            "file_hash": file_hash,
            "provider_file_uuid": provider_file_uuid,
            "mime_type": mime_type,
            "fs_metadata": {},
        }

        # Remove None values
        file_hash_data = {k: v for k, v in file_hash_data.items() if v is not None}

        data = {
            "workflow_id": str(workflow_id),
            "file_hash": file_hash_data,
            "is_api": is_api,
            "status": status_str,
        }

        # Add optional fields if provided
        if result is not None:
            data["result"] = result
        if metadata is not None:
            data["metadata"] = metadata
        if error is not None:
            data["error"] = error

        logger.info(
            f"Creating file history record for {file_name} with status: {status_str}"
        )
        # DEBUG: Log file_hash parameter being sent
        logger.info(f"DEBUG: Sending file_hash='{file_hash}' in request data")
        logger.info(f"DEBUG: file_hash_data contains: {file_hash_data}")
        logger.debug(f"File history data: {data}")

        try:
            response = self.post(self._build_url("file_history", "create/"), data)
            logger.info(
                f"Successfully created file history record: {response.get('id') if response else 'unknown'}"
            )
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )
        except Exception as e:
            logger.error(f"Failed to create file history record: {str(e)}")
            logger.debug(f"Request data was: {data}")
            return APIResponse(success=False, error=str(e))

    def get_file_history_status(self, file_history_id: str | uuid.UUID) -> dict[str, Any]:
        """Get file history status.

        Args:
            file_history_id: File history ID

        Returns:
            File history status data
        """
        return self.get(
            self._build_url("file_history", f"status/{str(file_history_id)}/")
        )

    def batch_create_file_history(
        self, file_histories: list[dict[str, Any]], organization_id: str | None = None
    ) -> BatchOperationResponse:
        """Create multiple file history records in a single batch request.

        Args:
            file_histories: List of file history data dictionaries
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with results
        """
        batch_request = BatchOperationRequest(
            operation_type=BatchOperationType.CREATE,
            items=file_histories,
            organization_id=organization_id,
        )

        # Note: No batch endpoint exists, would need individual creation calls
        # For now, this will return an error indicating batch operations not supported
        response = self.post(
            "v1/file-history/create/",  # Use individual create endpoint
            batch_request.to_dict(),
            organization_id=organization_id,
        )

        return BatchOperationResponse(
            operation_id=response.get("operation_id", str(uuid.uuid4())),
            total_items=len(file_histories),
            successful_items=response.get("successful_items", 0),
            failed_items=response.get("failed_items", 0),
            status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
            results=response.get("results", []),
            errors=response.get("errors", []),
            execution_time=response.get("execution_time"),
        )
