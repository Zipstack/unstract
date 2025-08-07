"""File History Manager for Workers

This module provides file history management functionality for workers,
matching the backend FileHistoryHelper logic.
"""

import logging
from typing import Any

from unstract.core.data_models import FileHash

from .api_client import InternalAPIClient

logger = logging.getLogger(__name__)


class WorkerFileHistoryManager:
    """Worker-compatible file history manager.

    This handles creating FileHistory entries after successful processing
    to enable deduplication for future runs. It matches the backend
    FileHistoryHelper logic but uses API calls instead of direct DB access.
    """

    def __init__(self, api_client: InternalAPIClient):
        """Initialize the file history manager.

        Args:
            api_client: Internal API client for backend communication
        """
        self.api_client = api_client
        self.logger = logger

    def create_file_history_entry(
        self,
        workflow_id: str,
        file_data: FileHash,
        execution_result: dict[str, Any],
        organization_id: str,
    ) -> bool:
        """Create file history entry after successful processing.

        This matches backend FileHistoryHelper.create_file_history() logic.
        For FILESYSTEM workflows, file_hash is used as the unique identifier.

        Args:
            workflow_id: Workflow ID
            file_data: FileHash object with file information
            execution_result: Result from file processing
            organization_id: Organization ID

        Returns:
            bool: True if history entry was created successfully
        """
        try:
            if not file_data.file_hash:
                logger.warning(
                    f"No file hash available for {file_data.file_name} - skipping history creation"
                )
                return False

            # Determine status from execution result
            status = execution_result.get("status", "SUCCESS")
            if status not in ["SUCCESS", "ERROR", "PARTIAL"]:
                status = "SUCCESS"  # Default to success

            # Build history data matching backend expectations
            history_data = {
                "workflow_id": workflow_id,
                "cache_key": file_data.file_hash,  # Backend expects cache_key instead of file_hash
                "file_name": file_data.file_name,
                "file_path": file_data.file_path,
                "file_size": file_data.file_size,
                "provider_file_uuid": file_data.provider_file_uuid,
                "mime_type": file_data.mime_type,
                "status": status,
                "is_completed": status == "SUCCESS",
                "execution_id": execution_result.get("execution_id"),
                "result": execution_result.get("result", {}),
                "metadata": execution_result.get("metadata", {}),
                "organization_id": organization_id,
                "source_connection_type": file_data.source_connection_type,
                "use_file_history": getattr(
                    file_data, "use_file_history", True
                ),  # Pass the flag
            }

            response = self.api_client.create_file_history_entry(history_data)

            if response.get("created"):
                logger.info(
                    f"Created file history entry for {file_data.file_name} (status: {status})"
                )
                return True
            else:
                logger.warning(
                    f"Failed to create file history entry for {file_data.file_name}: {response}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Failed to create file history entry for {file_data.file_name}: {e}"
            )
            return False

    def create_batch_file_history_entries(
        self,
        workflow_id: str,
        execution_results: list[dict[str, Any]],
        organization_id: str,
    ) -> dict[str, bool]:
        """Create file history entries for a batch of files.

        Args:
            workflow_id: Workflow ID
            execution_results: List of execution results with file_data
            organization_id: Organization ID

        Returns:
            dict: Mapping of file names to creation success status
        """
        results = {}

        for execution_result in execution_results:
            file_data = execution_result.get("file_data")
            if file_data and isinstance(file_data, (FileHash, dict)):
                if isinstance(file_data, dict):
                    file_data = FileHash.from_json(file_data)

                file_name = file_data.file_name
                success = self.create_file_history_entry(
                    workflow_id=workflow_id,
                    file_data=file_data,
                    execution_result=execution_result,
                    organization_id=organization_id,
                )
                results[file_name] = success
            else:
                logger.warning(
                    f"No file_data found in execution result: {execution_result.get('id')}"
                )

        return results

    def check_file_already_processed(
        self,
        workflow_id: str,
        file_hash: str,
        organization_id: str,
    ) -> bool:
        """Check if a file has already been processed.

        Args:
            workflow_id: Workflow ID
            file_hash: File content hash
            organization_id: Organization ID

        Returns:
            bool: True if file has been processed successfully
        """
        try:
            response = self.api_client.check_file_history_batch(
                workflow_id=workflow_id,
                file_hashes=[file_hash],
                organization_id=organization_id,
            )

            processed_hashes = response.get("processed_file_hashes", [])
            return file_hash in processed_hashes

        except Exception as e:
            logger.warning(f"Failed to check file history: {e}")
            # On error, assume file has not been processed
            return False
