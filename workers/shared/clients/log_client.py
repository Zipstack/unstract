"""Log operations client for internal API communication.

This client handles log history operations through internal APIs to avoid
direct Django ORM dependencies.
"""

import logging

from ..data.response_models import APIResponse
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class LogAPIClient(BaseAPIClient):
    """Client for log-related operations through internal APIs."""

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
