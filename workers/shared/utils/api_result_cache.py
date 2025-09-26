"""API Result Caching Utilities

This module provides utilities for caching API deployment results,
extracted from destination connector to provide reusable caching functionality
across worker components.
"""

import logging
from typing import Any

from shared.utils.api_hub_factory import APIHubUsageUtil

from unstract.core.data_models import FileHashData
from unstract.core.worker_models import (
    ApiDeploymentResultStatus,
    FileExecutionResult,
    FileProcessingResult,
)
from unstract.workflow_execution.api_deployment.cache_utils import WorkerResultCacheUtils

from .api_metadata import ApiMetadataBuilder

logger = logging.getLogger(__name__)


class APIResultCacheManager:
    """Manages caching of API deployment results for worker components.

    This class provides a centralized way to cache API results from various
    worker components without requiring a full destination connector instance.
    """

    def __init__(self):
        """Initialize the API result cache manager."""
        self._cache_utils = None

    @property
    def cache_utils(self) -> WorkerResultCacheUtils:
        """Get cache utils instance (lazy initialization)."""
        if self._cache_utils is None:
            self._cache_utils = WorkerResultCacheUtils()
        return self._cache_utils

    def _track_api_hub_usage(
        self, organization_id: str, execution_id: str, file_execution_id: str
    ):
        """Track API Hub usage."""
        # Track usage for API Hub deployments (graceful fallback for OSS)
        try:
            logger.info(
                f"_track_api_hub_usage: Tracking API Hub usage for {execution_id} : {file_execution_id}"
            )
            APIHubUsageUtil.track_api_hub_usage(
                workflow_execution_id=execution_id,
                workflow_file_execution_id=file_execution_id,
                organization_id=organization_id,
            )
        except Exception as e:
            # Log but don't fail the main execution for usage tracking issues
            logger.warning(
                f"Could not track API hub usage for {execution_id} : {file_execution_id}: {e}"
            )

    def cache_file_processing_result(
        self,
        file_processing_result: FileProcessingResult,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        file_hash: FileHashData,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Cache a FileProcessingResult as an API deployment result.

        Args:
            file_processing_result: The file processing result to cache
            workflow_id: Workflow ID for caching key
            execution_id: Execution ID for caching key
            organization_id: Organization ID for context
            file_hash: File hash data for file info
            metadata: Optional additional metadata

        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Convert FileProcessingResult to FileExecutionResult for API caching
            api_result = self._convert_to_file_execution_result(
                file_processing_result=file_processing_result,
                file_hash=file_hash,
                metadata=metadata,
            )

            # Cache the result using WorkerResultCacheUtils
            self.cache_utils.update_api_results(
                workflow_id=workflow_id, execution_id=execution_id, api_result=api_result
            )

            logger.info(
                f"Successfully cached API result for file {file_hash.file_name} "
                f"in execution {execution_id}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to cache API result for file {file_hash.file_name} "
                f"in execution {execution_id}: {str(e)}"
            )
            # Return False but don't re-raise - caching failures shouldn't stop execution
            return False

    def _convert_to_file_execution_result(
        self,
        file_processing_result: FileProcessingResult,
        file_hash: FileHashData,
        metadata: dict[str, Any] | None = None,
    ) -> FileExecutionResult:
        """Convert FileProcessingResult to FileExecutionResult for API caching.

        Args:
            file_processing_result: Source result to convert
            file_hash: File hash data for file info
            metadata: Optional additional metadata

        Returns:
            FileExecutionResult ready for API caching
        """
        # Determine status based on result success and error
        if file_processing_result.success and not file_processing_result.error:
            status = ApiDeploymentResultStatus.SUCCESS
        else:
            status = ApiDeploymentResultStatus.FAILED

        # Merge metadata from result and additional metadata
        result_metadata = file_processing_result.metadata or {}
        additional_metadata = metadata or {}

        # Add processing context to metadata
        combined_metadata = {
            **result_metadata,
            **additional_metadata,
            "from_cache": getattr(file_processing_result, "from_cache", False),
            "from_file_history": getattr(
                file_processing_result, "from_file_history", False
            ),
            "manual_review": getattr(file_processing_result, "manual_review", False),
            "execution_time": getattr(file_processing_result, "execution_time", 0.0),
        }

        # Create FileExecutionResult matching destination connector pattern
        return FileExecutionResult(
            file=file_hash.file_name,
            status=status,
            file_execution_id=file_processing_result.file_execution_id,
            result=file_processing_result.result,
            error=file_processing_result.error,
            metadata=combined_metadata,
        )

    def cache_file_history_result_for_api(
        self,
        file_processing_result: FileProcessingResult,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        file_hash: FileHashData,
    ) -> bool:
        """Cache file history result as API result with clean metadata format.

        This method specifically handles file history results and formats them
        with the clean metadata structure expected by API deployments.

        Args:
            file_processing_result: The cached file processing result
            workflow_id: Workflow ID for caching key
            execution_id: Execution ID for caching key
            organization_id: Organization ID for context
            file_hash: File hash data for file info

        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Create clean metadata using structured builder
            clean_metadata = ApiMetadataBuilder.build_file_history_metadata(
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_processing_result=file_processing_result,
                file_hash=file_hash,
            )

            # Use direct caching with clean metadata
            return self.cache_api_result_direct(
                file_name=file_hash.file_name,
                file_execution_id=file_processing_result.file_execution_id,
                workflow_id=workflow_id,
                execution_id=execution_id,
                result=file_processing_result.result,
                error=file_processing_result.error,
                organization_id=organization_id,
                metadata=clean_metadata,
            )

        except Exception as e:
            logger.error(
                f"Failed to cache file history result for API for file {file_hash.file_name}: {str(e)}"
            )
            return False

    def cache_error_result_for_api(
        self,
        file_processing_result: FileProcessingResult,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        file_hash: FileHashData,
    ) -> bool:
        """Cache error result as API result with clean metadata format.

        This method specifically handles error/exception results and formats them
        with the clean metadata structure expected by API deployments.

        Args:
            file_processing_result: The error file processing result
            workflow_id: Workflow ID for caching key
            execution_id: Execution ID for caching key
            organization_id: Organization ID for context
            file_hash: File hash data for file info

        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Create clean metadata using structured builder
            clean_metadata = ApiMetadataBuilder.build_error_metadata(
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_processing_result=file_processing_result,
                file_hash=file_hash,
            )

            # Use direct caching with clean metadata
            return self.cache_api_result_direct(
                file_name=file_hash.file_name,
                file_execution_id=file_processing_result.file_execution_id,
                workflow_id=workflow_id,
                execution_id=execution_id,
                result=file_processing_result.result,
                error=file_processing_result.error,
                organization_id=organization_id,
                metadata=clean_metadata,
            )

        except Exception as e:
            logger.error(
                f"Failed to cache error result for API for file {file_hash.file_name}: {str(e)}"
            )
            return False

    def cache_api_result_direct(
        self,
        file_name: str,
        file_execution_id: str,
        workflow_id: str,
        execution_id: str,
        result: dict[str, Any] | None,
        error: str | None = None,
        organization_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Cache API result directly without FileProcessingResult conversion.

        This method provides a direct interface for caching API results
        when you already have the raw result data.

        Args:
            file_name: Name of the file
            file_execution_id: File execution ID
            workflow_id: Workflow ID for caching key
            execution_id: Execution ID for caching key
            organization_id: Organization ID for context
            result: Result data to cache
            error: Optional error message
            metadata: Optional metadata

        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Determine status
            status = (
                ApiDeploymentResultStatus.FAILED
                if error
                else ApiDeploymentResultStatus.SUCCESS
            )

            # Create FileExecutionResult
            api_result = FileExecutionResult(
                file=file_name,
                status=status,
                file_execution_id=file_execution_id,
                result=result,
                error=error,
                metadata=metadata or {},
            )

            # Cache the result
            self.cache_utils.update_api_results(
                workflow_id=workflow_id, execution_id=execution_id, api_result=api_result
            )

            logger.info(
                f"Successfully cached direct API result for file {file_name} "
                f"in execution {execution_id} for organization {organization_id}"
            )

            if organization_id:
                self._track_api_hub_usage(
                    organization_id=organization_id,
                    execution_id=execution_id,
                    file_execution_id=file_execution_id,
                )

            return True

        except Exception as e:
            logger.error(
                f"Failed to cache direct API result for file {file_name} "
                f"in execution {execution_id}: {str(e)}"
            )
            return False


# Singleton instance for easy access
_api_cache_manager = None


def get_api_cache_manager() -> APIResultCacheManager:
    """Get singleton instance of APIResultCacheManager."""
    global _api_cache_manager
    if _api_cache_manager is None:
        _api_cache_manager = APIResultCacheManager()
    return _api_cache_manager
