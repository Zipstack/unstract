"""API Result Metadata Structures

This module provides structured dataclasses for creating clean, type-safe
metadata for API deployment results, eliminating hardcoded dictionary creation.
"""

import logging
from dataclasses import asdict, dataclass
from typing import Any

from unstract.core.data_models import FileHashData
from unstract.core.worker_models import FileProcessingResult

logger = logging.getLogger(__name__)


@dataclass
class BaseApiMetadata:
    """Base metadata structure for all API results.

    Contains common fields that appear in all API result metadata.
    """

    workflow_id: str
    execution_id: str
    execution_time: float
    source_name: str
    source_hash: str
    organization_id: str | None = None
    total_elapsed_time: float | None = None
    tool_metadata: dict[str, Any] | None = None

    @classmethod
    def from_context(
        cls,
        workflow_id: str,
        execution_id: str,
        file_processing_result: FileProcessingResult,
        file_hash: FileHashData,
    ) -> "BaseApiMetadata":
        """Create base metadata from processing context.

        Args:
            workflow_id: Workflow identifier
            execution_id: Execution identifier
            file_processing_result: Source processing result
            file_hash: File hash information

        Returns:
            BaseApiMetadata instance with populated common fields
        """
        metadata = file_processing_result.metadata or {}
        return cls(
            workflow_id=metadata.get("workflow_id", workflow_id),
            execution_id=metadata.get("execution_id", execution_id),
            execution_time=metadata.get(
                "execution_time", getattr(file_processing_result, "execution_time", 0.0)
            ),
            source_name=metadata.get("source_name", file_hash.file_name),
            source_hash=metadata.get("source_hash", file_hash.file_hash),
            organization_id=metadata.get("organization_id"),
            total_elapsed_time=metadata.get("total_elapsed_time"),
            tool_metadata=metadata.get("tool_metadata"),
        )


@dataclass
class FileHistoryApiMetadata(BaseApiMetadata):
    """Metadata structure for file history API results.

    Used when API results come from cached file processing history.
    """

    from_file_history: bool = True
    tool_count: int | None = None


@dataclass
class ErrorApiMetadata(BaseApiMetadata):
    """Metadata structure for error API results.

    Used when API results represent processing errors or exceptions.
    """

    error_occurred: bool = True
    workflow_execution_failed: bool | None = None
    processing_failed: bool | None = None


class ApiMetadataBuilder:
    """Helper class for building structured API metadata dictionaries.

    Provides static methods to create clean, consistent metadata structures
    for different types of API results while avoiding code duplication.
    """

    @staticmethod
    def build_file_history_metadata(
        workflow_id: str,
        execution_id: str,
        file_processing_result: FileProcessingResult,
        file_hash: FileHashData,
    ) -> dict[str, Any]:
        """Build metadata for file history API results.

        Args:
            workflow_id: Workflow identifier
            execution_id: Execution identifier
            file_processing_result: Source processing result
            file_hash: File hash information

        Returns:
            Dictionary with clean file history metadata structure
        """
        try:
            metadata = FileHistoryApiMetadata.from_context(
                workflow_id, execution_id, file_processing_result, file_hash
            )

            return asdict(metadata)

        except Exception as e:
            logger.error(f"Failed to build file history metadata: {e}")
            # Fallback to minimal structure
            return {
                "workflow_id": workflow_id,
                "execution_id": execution_id,
                "from_file_history": True,
                "source_name": file_hash.file_name,
                "source_hash": file_hash.file_hash,
            }

    @staticmethod
    def build_error_metadata(
        workflow_id: str,
        execution_id: str,
        file_processing_result: FileProcessingResult,
        file_hash: FileHashData,
    ) -> dict[str, Any]:
        """Build metadata for error API results.

        Args:
            workflow_id: Workflow identifier
            execution_id: Execution identifier
            file_processing_result: Source processing result with error
            file_hash: File hash information

        Returns:
            Dictionary with clean error metadata structure
        """
        try:
            metadata = ErrorApiMetadata.from_context(
                workflow_id, execution_id, file_processing_result, file_hash
            )

            # Add optional error context from original metadata if available
            original_metadata = file_processing_result.metadata or {}
            if "workflow_execution_failed" in original_metadata:
                metadata.workflow_execution_failed = original_metadata[
                    "workflow_execution_failed"
                ]
            if "processing_failed" in original_metadata:
                metadata.processing_failed = original_metadata["processing_failed"]

            return asdict(metadata)

        except Exception as e:
            logger.error(f"Failed to build error metadata: {e}", exc_info=True)
            # Fallback to minimal structure
            return {
                "workflow_id": workflow_id,
                "execution_id": execution_id,
                "error_occurred": True,
                "source_name": file_hash.file_name,
                "source_hash": file_hash.file_hash,
            }

    @staticmethod
    def build_base_metadata(
        workflow_id: str,
        execution_id: str,
        file_processing_result: FileProcessingResult,
        file_hash: FileHashData,
        additional_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build base metadata with optional additional fields.

        Args:
            workflow_id: Workflow identifier
            execution_id: Execution identifier
            file_processing_result: Source processing result
            file_hash: File hash information
            additional_fields: Optional additional metadata fields

        Returns:
            Dictionary with base metadata structure plus additional fields
        """
        try:
            metadata = BaseApiMetadata.from_context(
                workflow_id, execution_id, file_processing_result, file_hash
            )

            result = asdict(metadata)

            # Add additional fields if provided
            if additional_fields:
                result.update(additional_fields)

            return result

        except Exception as e:
            logger.error(f"Failed to build base metadata: {e}")
            # Fallback to minimal structure
            result = {
                "workflow_id": workflow_id,
                "execution_id": execution_id,
                "source_name": file_hash.file_name,
                "source_hash": file_hash.file_hash,
            }
            if additional_fields:
                result.update(additional_fields)
            return result
