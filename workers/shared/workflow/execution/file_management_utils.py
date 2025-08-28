"""File Management Utilities

This module provides utility methods for file processing, filtering, and management
that can be used across different worker types (general, api-deployment, etc.).

Each utility method has a single responsibility and can be composed as needed.
"""

from typing import Any, Protocol

from ...infrastructure.logging import WorkerLogger
from .active_file_manager import ActiveFileManager

logger = WorkerLogger.get_logger(__name__)


class LoggerProtocol(Protocol):
    """Protocol for logger objects to provide proper type hints."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class FileFilterResult:
    """Result of file filtering operations."""

    def __init__(
        self,
        filtered_files: dict[str, Any],
        filtered_count: int,
        filtering_stats: dict[str, Any],
    ):
        self.filtered_files = filtered_files
        self.filtered_count = filtered_count
        self.filtering_stats = filtering_stats
        self.original_count = filtering_stats.get("original_count", 0)
        self.skipped_files = filtering_stats.get("skipped_files", [])
        self.cache_active_count = len(filtering_stats.get("cache_active", []))
        self.db_active_count = len(filtering_stats.get("db_active", []))

    def has_files(self) -> bool:
        """Check if any files remain after filtering."""
        return self.filtered_count > 0

    def all_files_active(self) -> bool:
        """Check if all files were filtered out due to being active."""
        return self.original_count > 0 and self.filtered_count == 0


class FileLimitResult:
    """Result of applying file limits."""

    def __init__(
        self, limited_files: dict[str, Any], final_count: int, limit_applied: bool
    ):
        self.limited_files = limited_files
        self.final_count = final_count
        self.limit_applied = limit_applied


class FileManagementUtils:
    """Utility methods for file processing and management across workers."""

    @staticmethod
    def apply_active_file_filtering(
        source_files: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        api_client: Any,
        logger_instance: LoggerProtocol | None = None,
        final_files_to_process: dict[str, Any] | None = None,
    ) -> FileFilterResult:
        """Apply active file filtering to remove files being processed by other executions.

        Use this for ETL/TASK workflows that need to avoid duplicate processing.
        API workflows typically skip this filtering.

        Args:
            source_files: Dictionary of source files to filter
            workflow_id: Workflow ID
            execution_id: Current execution ID
            api_client: API client for database checks
            logger_instance: Optional logger instance
            final_files_to_process: Optional dict of files that will actually be processed
                                    If provided, cache entries are created only for these files

        Returns:
            FileFilterResult with filtered files and statistics
        """
        log = logger_instance or logger

        if not source_files:
            return FileFilterResult(
                filtered_files={},
                filtered_count=0,
                filtering_stats={
                    "original_count": 0,
                    "filtered_count": 0,
                    "skipped_files": [],
                },
            )

        log.info(f"🔍 Applying active file filtering for {len(source_files)} files")

        filtered_files, filtered_count, filtering_stats = (
            ActiveFileManager.filter_and_cache_files(
                source_files=source_files,
                workflow_id=workflow_id,
                execution_id=execution_id,
                api_client=api_client,
                logger_instance=log,
                final_files_to_process=final_files_to_process,
            )
        )

        result = FileFilterResult(filtered_files, filtered_count, filtering_stats)

        if result.all_files_active():
            log.warning(
                "⚠️ All discovered files are currently being processed by other executions"
            )
            log.info(
                "💡 Tip: Wait for current executions to complete or discover more files"
            )
        elif result.has_files():
            log.info(
                f"✅ {result.filtered_count} files available for processing after filtering"
            )

        return result

    @staticmethod
    def apply_file_limit(
        files: dict[str, Any],
        max_limit: int,
        logger_instance: LoggerProtocol | None = None,
    ) -> FileLimitResult:
        """Apply maximum file limit to a collection of files.

        Args:
            files: Dictionary of files to limit
            max_limit: Maximum number of files to allow
            logger_instance: Optional logger instance

        Returns:
            FileLimitResult with limited files
        """
        log = logger_instance or logger

        if len(files) <= max_limit:
            return FileLimitResult(
                limited_files=files, final_count=len(files), limit_applied=False
            )

        log.info(
            f"📏 Applying max files limit: taking {max_limit} files from {len(files)} available"
        )

        # Convert to list, take first N files, convert back to dict
        limited_files = dict(list(files.items())[:max_limit])

        return FileLimitResult(
            limited_files=limited_files, final_count=max_limit, limit_applied=True
        )

    @staticmethod
    def cleanup_active_file_cache(
        provider_file_uuids: list[str],
        workflow_id: str,
        logger_instance: LoggerProtocol | None = None,
    ) -> int:
        """Clean up active file cache entries for completed/failed processing.

        Args:
            provider_file_uuids: List of provider file UUIDs to clean up
            workflow_id: Workflow ID
            logger_instance: Optional logger instance

        Returns:
            Number of cache entries cleaned up
        """
        log = logger_instance or logger

        if not provider_file_uuids:
            return 0

        log.debug(f"🧹 Cleaning up cache entries for {len(provider_file_uuids)} files")

        return ActiveFileManager.cleanup_cache_entries(
            provider_file_uuids=provider_file_uuids, workflow_id=workflow_id, log=log
        )

    @staticmethod
    def extract_provider_uuids(hash_values_of_files: dict[str, Any]) -> list[str]:
        """Extract provider file UUIDs from file hash data.

        Args:
            hash_values_of_files: Dictionary of file hash data

        Returns:
            List of provider file UUIDs
        """
        provider_uuids = []
        for hash_data in hash_values_of_files.values():
            if hasattr(hash_data, "provider_file_uuid") and hash_data.provider_file_uuid:
                provider_uuids.append(hash_data.provider_file_uuid)
        return provider_uuids

    @staticmethod
    def log_filtering_stats(
        filtering_stats: dict[str, Any], logger_instance: LoggerProtocol | None = None
    ) -> None:
        """Log detailed file filtering statistics.

        Args:
            filtering_stats: Statistics from file filtering operations
            logger_instance: Optional logger instance
        """
        log = logger_instance or logger

        original_count = filtering_stats.get("original_count", 0)
        filtered_count = filtering_stats.get("filtered_count", 0)

        if original_count > 0:
            log.info(
                f"📊 File filtering results: {original_count} → {filtered_count} files"
            )

            cache_created = filtering_stats.get("cache_created", 0)
            if cache_created > 0:
                log.info(f"🔒 Created {cache_created} active_file cache entries")

            cache_active = filtering_stats.get("cache_active", [])
            db_active = filtering_stats.get("db_active", [])
            if cache_active or db_active:
                cache_count = len(cache_active)
                db_count = len(db_active)
                log.info(
                    f"⚡ Skipped {cache_count} cache-active + {db_count} db-active files"
                )

    @staticmethod
    def process_files_with_active_filtering(
        source_files: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        max_limit: int,
        api_client: Any,
        logger_instance: LoggerProtocol | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Complete file processing pipeline with active filtering and limit.

        Processing order:
        1. Apply all filters (file history is already done, now cache + database)
        2. Take up to max_limit files from the filtered results
        3. Create cache entries ONLY for the final selected files

        **IMPORTANT**: Use ONLY for ETL/TASK workflows in @workers/general/
        Do NOT use for API deployments (@workers/api-deployment/) - they have their own logic.

        Args:
            source_files: Dictionary of source files (already filtered by file history)
            workflow_id: Workflow ID
            execution_id: Current execution ID
            max_limit: Maximum number of files to process after all filtering
            api_client: API client for database checks
            logger_instance: Optional logger instance

        Returns:
            Tuple of (final_files, final_count)
        """
        log = logger_instance or logger

        # Step 1: Filter out active files (no cache creation yet)
        filter_result = FileManagementUtils.apply_active_file_filtering(
            source_files=source_files,
            workflow_id=workflow_id,
            execution_id=execution_id,
            api_client=api_client,
            logger_instance=log,
            final_files_to_process=None,  # No cache creation at this step
        )

        # Step 2: Apply limit to the filtered results (max files after all filtering)
        limit_result = FileManagementUtils.apply_file_limit(
            files=filter_result.filtered_files, max_limit=max_limit, logger_instance=log
        )

        # Step 3: Create cache entries ONLY for the final selected files
        if limit_result.limited_files:
            log.info(
                f"Creating cache entries for {limit_result.final_count} final selected files"
            )
            # Call filter_and_cache_files again just for cache creation
            ActiveFileManager.filter_and_cache_files(
                source_files=source_files,  # Need original for file_tracking_data
                workflow_id=workflow_id,
                execution_id=execution_id,
                api_client=api_client,
                logger_instance=log,
                final_files_to_process=limit_result.limited_files,  # Create cache for these files only
            )

        # Step 4: Log statistics
        FileManagementUtils.log_filtering_stats(
            filtering_stats=filter_result.filtering_stats, logger_instance=log
        )

        return limit_result.limited_files, limit_result.final_count

    # IMPORTANT: Maximum file limit behavior
    # The max_limit parameter specifies the maximum number of files to process
    # AFTER all filtering has been applied. For example:
    #
    # Source: 10 files → File History: 7 files → Cache Filter: 5 files → DB Filter: 3 files
    # If max_limit=4: Process 3 files (less than limit)
    # If max_limit=2: Process 2 files (limited by max_limit)
    #
    # Example usage for different worker types:
    #
    # # ✅ ETL/TASK workflows (@workers/general/):
    # final_files, count = FileManagementUtils.process_files_with_active_filtering(
    #     source_files=files, workflow_id=wf_id, execution_id=exec_id,
    #     max_limit=10, api_client=client
    # )
    #
    # # ✅ API deployments (@workers/api-deployment/):
    # final_files, count = FileManagementUtils.process_files_without_active_filtering(
    #     source_files=files, max_limit=10
    # )
    #
    # # ✅ Cleanup (ONLY for ETL/TASK workflows - API deployments don't use cache):
    # uuids = FileManagementUtils.extract_provider_uuids(hash_values_of_files)
    # cleaned = FileManagementUtils.cleanup_active_file_cache(uuids, workflow_id)
    #
    # # Custom filtering only:
    # filter_result = FileManagementUtils.apply_active_file_filtering(
    #     source_files=files, workflow_id=wf_id, execution_id=exec_id, api_client=client
    # )
    # if not filter_result.has_files():
    #     # Handle case where all files are active
    #
    # limit_result = FileManagementUtils.apply_file_limit(filter_result.filtered_files, 5)
    # final_files = limit_result.limited_files

    @staticmethod
    def process_files_without_active_filtering(
        source_files: dict[str, Any],
        max_limit: int,
        logger_instance: LoggerProtocol | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Process files with only limit application, no active filtering.

        **IMPORTANT**: Use for API workflows (@workers/api-deployment/) that don't need
        duplicate processing prevention. API deployments handle concurrency differently
        and should NOT use the file_active cache pattern.

        Args:
            source_files: Dictionary of source files
            max_limit: Maximum number of files to process
            logger_instance: Optional logger instance

        Returns:
            Tuple of (final_files, final_count)
        """
        log = logger_instance or logger

        log.info(f"📋 Processing {len(source_files)} files without active filtering")

        # Apply file limit only
        limit_result = FileManagementUtils.apply_file_limit(
            files=source_files, max_limit=max_limit, logger_instance=log
        )

        return limit_result.limited_files, limit_result.final_count


# Example usage for different worker types:
#
# # ✅ ETL/TASK workflows (@workers/general/):
# final_files, count = FileManagementUtils.process_files_with_active_filtering(
#     source_files=files, workflow_id=wf_id, execution_id=exec_id,
#     max_limit=10, api_client=client
# )
#
# # ✅ API deployments (@workers/api-deployment/):
# final_files, count = FileManagementUtils.process_files_without_active_filtering(
#     source_files=files, max_limit=10
# )
#
# # ✅ Cleanup (ONLY for ETL/TASK workflows - API deployments don't use cache):
# uuids = FileManagementUtils.extract_provider_uuids(hash_values_of_files)
# cleaned = FileManagementUtils.cleanup_active_file_cache(uuids, workflow_id)
#
# # Custom filtering only:
# filter_result = FileManagementUtils.apply_active_file_filtering(
#     source_files=files, workflow_id=wf_id, execution_id=exec_id, api_client=client
# )
# if not filter_result.has_files():
#     # Handle case where all files are active
#
# limit_result = FileManagementUtils.apply_file_limit(filter_result.filtered_files, 5)
# final_files = limit_result.limited_files
