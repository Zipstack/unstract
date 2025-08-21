"""Log operations client for internal API communication.

This client handles log history operations through internal APIs to avoid
direct Django ORM dependencies.
"""

import logging
from typing import Any

from ..response_models import APIResponse, BatchOperationResponse
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class LogAPIClient(BaseAPIClient):
    """Client for log-related operations through internal APIs."""

    def create_execution_logs_bulk(
        self, logs_data: list[dict[str, Any]]
    ) -> BatchOperationResponse:
        """Create execution logs in bulk via internal API.

        Args:
            logs_data: List of log data dictionaries containing:
                - execution_id: String ID of the workflow execution
                - file_execution_id: String ID of the file execution (optional)
                - data: Log data dictionary
                - event_time: Timestamp of the log event
                - organization_id: Organization ID for the logs

        Returns:
            BatchOperationResponse containing creation results
        """
        try:
            # Use _make_request directly to specify a longer timeout for bulk operations
            response_data = self._make_request(
                method="POST",
                endpoint="/v1/execution-logs/execution-logs/bulk-create/",
                data={"logs": logs_data},
                timeout=300,  # Longer timeout for bulk operations
            )

            created_count = response_data.get("created_count", 0)
            total_logs = response_data.get("total_logs", len(logs_data))
            failed_count = total_logs - created_count

            logger.info(
                f"Successfully created {created_count}/{total_logs} execution logs"
            )

            return BatchOperationResponse.success_response(
                successful_items=created_count,
                total_items=total_logs,
                failed_items=failed_count,
                message=f"Bulk created {created_count} execution logs",
            )

        except Exception as e:
            logger.error(f"Exception creating execution logs: {e}")
            return BatchOperationResponse.error_response(
                total_items=len(logs_data),
                errors=[str(e)],
                message="Failed to create execution logs",
            )

    def get_workflow_executions(self, execution_ids: list[str]) -> APIResponse:
        """Get workflow execution data for given IDs.

        Args:
            execution_ids: List of workflow execution IDs

        Returns:
            APIResponse containing executions data
        """
        try:
            response_data = self.post(
                endpoint="/v1/execution-logs/workflow-executions/by-ids/",
                data={"execution_ids": execution_ids},
            )

            return APIResponse.success_response(
                data=response_data,
                message=f"Retrieved {len(execution_ids)} workflow executions",
            )

        except Exception as e:
            logger.error(f"Exception getting workflow executions: {e}")
            return APIResponse.error_response(
                error=str(e), message="Failed to get workflow executions"
            )

    def get_file_executions(self, file_execution_ids: list[str]) -> APIResponse:
        """Get file execution data for given IDs.

        Args:
            file_execution_ids: List of file execution IDs

        Returns:
            APIResponse containing file executions data
        """
        try:
            response_data = self.post(
                endpoint="/v1/execution-logs/file-executions/by-ids/",
                data={"file_execution_ids": file_execution_ids},
            )

            return APIResponse.success_response(
                data=response_data,
                message=f"Retrieved {len(file_execution_ids)} file executions",
            )

        except Exception as e:
            logger.error(f"Exception getting file executions: {e}")
            return APIResponse.error_response(
                error=str(e), message="Failed to get file executions"
            )

    def validate_execution_references(
        self, execution_ids: list[str], file_execution_ids: list[str]
    ) -> APIResponse:
        """Validate that execution references exist before creating logs.

        Args:
            execution_ids: List of workflow execution IDs to validate
            file_execution_ids: List of file execution IDs to validate

        Returns:
            APIResponse with validation results:
            - valid_executions: Set of valid execution IDs
            - valid_file_executions: Set of valid file execution IDs
        """
        try:
            response_data = self.post(
                endpoint="/v1/execution-logs/executions/validate/",
                data={
                    "execution_ids": execution_ids,
                    "file_execution_ids": file_execution_ids,
                },
            )

            # Convert lists to sets for easier validation logic
            validation_data = {
                "valid_executions": set(response_data.get("valid_executions", [])),
                "valid_file_executions": set(
                    response_data.get("valid_file_executions", [])
                ),
            }

            return APIResponse.success_response(
                data=validation_data,
                message=f"Validated {len(execution_ids)} executions and {len(file_execution_ids)} file executions",
            )

        except Exception as e:
            logger.error(f"Exception validating execution references: {e}")
            return APIResponse.error_response(
                error=str(e), message="Failed to validate execution references"
            )

    def get_cache_log_batch(self, queue_name: str, batch_limit: int = 100) -> APIResponse:
        """Get a batch of logs from Redis cache via internal API.

        Args:
            queue_name: Name of the Redis queue to retrieve logs from
            batch_limit: Maximum number of logs to retrieve

        Returns:
            APIResponse containing logs data
        """
        try:
            response_data = self.post(
                endpoint="/v1/execution-logs/cache/log-batch/",
                data={
                    "queue_name": queue_name,
                    "batch_limit": batch_limit,
                },
            )

            logs = response_data.get("logs", [])
            logs_count = response_data.get("count", len(logs))

            logger.debug(f"Retrieved {logs_count} logs from cache queue {queue_name}")

            return APIResponse.success_response(
                data=response_data, message=f"Retrieved {logs_count} logs from cache"
            )

        except Exception as e:
            logger.error(f"Exception getting log batch: {e}")
            return APIResponse.error_response(
                error=str(e), message="Failed to get log batch from cache"
            )
