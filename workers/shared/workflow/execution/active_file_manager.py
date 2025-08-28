"""Active File Manager Utility

This module provides utilities for managing active file processing state and preventing
race conditions in concurrent workflow executions.

Key Features:
- Filter files that are already being processed by other executions
- Create cache entries to prevent race conditions
- Provide detailed statistics for monitoring and debugging
- Graceful error handling that never fails the entire execution
"""

import hashlib
import time
from typing import Any, Protocol

from ...cache.base_cache import RedisCacheBackend
from ...infrastructure.logging import WorkerLogger


class LoggerProtocol(Protocol):
    """Protocol for logger objects to provide proper type hints."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


logger = WorkerLogger.get_logger(__name__)


class ActiveFileManager:
    """Utility class for managing active file processing state and race condition prevention.

    **USAGE SCOPE**:
    - ✅ USE: ETL/TASK workflows in @workers/general/
    - ❌ DON'T USE: API deployments in @workers/api-deployment/

    API deployments have different concurrency patterns and should not use the file_active
    cache pattern. They handle duplicate processing through their own mechanisms.
    """

    @staticmethod
    def filter_and_cache_files(
        source_files: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        api_client: Any,
        logger_instance: LoggerProtocol | None = None,
        final_files_to_process: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int, dict[str, Any]]:
        """Filter out active files and create cache entries for files to be processed.

        This method performs three key operations:
        1. Checks cache and database for files already being processed
        2. Creates cache entries ONLY for files that will actually be processed (race condition prevention)
        3. Filters the source_files dict to remove active files

        Args:
            source_files: Dictionary of source files to process
            workflow_id: Workflow identifier
            execution_id: Current execution identifier
            api_client: API client for database checks
            logger_instance: Optional logger override (uses module logger if None)
            final_files_to_process: Optional dict of files that will actually be processed (after limits)
                                    If provided, cache entries are created only for these files

        Returns:
            Tuple of (filtered_source_files, new_file_count, filtering_stats)

        Example:
            >>> files = {"file1": {"provider_file_uuid": "uuid1"}}
            >>> filtered, count, stats = ActiveFileManager.filter_and_cache_files(
            ...     source_files=files,
            ...     workflow_id="workflow-123",
            ...     execution_id="exec-456",
            ...     api_client=client,
            ... )
            >>> print(f"Processing {count} files, stats: {stats}")
        """
        log = logger_instance or logger

        if not source_files:
            return (
                source_files,
                0,
                {"original_count": 0, "filtered_count": 0, "skipped_files": []},
            )

        original_count = len(source_files)
        filtering_stats = {
            "original_count": original_count,
            "cache_active": [],  # Files found active in cache
            "db_active": [],  # Files found active in database
            "processing_files": [],  # Files that will be processed
            "cache_created": 0,  # Successfully created cache entries
            "cache_errors": 0,  # Failed cache operations
            "filtered_count": original_count,  # Will be updated if filtering occurs
        }

        try:
            # Extract provider_file_uuids and file paths from source files for checking
            provider_file_map = {}  # provider_uuid -> file_key mapping (for backward compatibility)
            file_tracking_data = {}  # file_key -> {provider_uuid, file_path, file_data} mapping

            for file_key, file_data in source_files.items():
                provider_uuid = ActiveFileManager._extract_provider_uuid(file_data)
                file_path = ActiveFileManager._extract_file_path(file_data)

                if provider_uuid:
                    # For backward compatibility with database checks
                    provider_file_map[provider_uuid] = file_key
                    # New tracking structure includes both provider_uuid and file_path
                    file_tracking_data[file_key] = {
                        "provider_uuid": provider_uuid,
                        "file_path": file_path
                        or file_key,  # fallback to file_key if no file_path
                        "file_data": file_data,
                    }

            if not provider_file_map:
                log.warning(
                    "No provider_file_uuid found in source files, proceeding without filtering"
                )
                return source_files, original_count, filtering_stats

            log.info(
                f"Checking {len(provider_file_map)} files for active processing conflicts"
            )
            log.debug(f"Current execution_id: {execution_id}, workflow_id: {workflow_id}")

            active_files_to_skip = set()

            # STEP 1: Check active_file cache for OTHER executions
            try:
                cache_stats = ActiveFileManager._handle_cache_check(
                    file_tracking_data=file_tracking_data,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    log=log,
                )
                active_files_to_skip.update(cache_stats["active_files"])
                filtering_stats.update(cache_stats["stats"])

            except Exception as cache_error:
                log.warning(f"Active file cache operations failed: {cache_error}")

            # STEP 2: Database check for files in PENDING/EXECUTING state (backend only reads cache, doesn't create)
            try:
                db_active_provider_uuids = ActiveFileManager._check_database_active_files(
                    api_client=api_client,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    provider_file_map=provider_file_map,
                    log=log,
                )

                if db_active_provider_uuids:
                    # Convert provider UUIDs back to file keys for filtering
                    db_active_file_keys = {
                        provider_file_map[provider_uuid]
                        for provider_uuid in db_active_provider_uuids
                        if provider_uuid in provider_file_map
                    }

                    new_db_active = db_active_file_keys - active_files_to_skip
                    active_files_to_skip.update(db_active_file_keys)
                    filtering_stats["db_active"].extend(list(new_db_active))
                    log.info(
                        f"📊 Found {len(new_db_active)} additional files active in database"
                    )

            except Exception as db_error:
                log.warning(f"Database file check failed: {db_error}")

            # STEP 3: Filter source_files to remove active ones (now using file_keys directly)
            if active_files_to_skip:
                filtered_files, new_count = (
                    ActiveFileManager._filter_source_files_by_keys(
                        source_files=source_files,
                        active_file_keys_to_skip=active_files_to_skip,
                        log=log,
                    )
                )

                filtering_stats["filtered_count"] = new_count
                filtering_stats["skipped_files"] = list(active_files_to_skip)

                log.info(
                    f"🔄 Filtered files: {original_count} → {new_count} "
                    f"(removed {len(active_files_to_skip)} active files)"
                )

                # STEP 4: Create cache entries only for files that will actually be processed
                if final_files_to_process:
                    ActiveFileManager._create_cache_entries_for_selected_files(
                        final_files_to_process=final_files_to_process,
                        file_tracking_data=file_tracking_data,
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        log=log,
                        filtering_stats=filtering_stats,
                    )

                return filtered_files, new_count, filtering_stats
            else:
                log.info("✅ No active files found - processing all files")

                # Create cache entries for files that will actually be processed
                if final_files_to_process:
                    ActiveFileManager._create_cache_entries_for_selected_files(
                        final_files_to_process=final_files_to_process,
                        file_tracking_data=file_tracking_data,
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        log=log,
                        filtering_stats=filtering_stats,
                    )

                return source_files, original_count, filtering_stats

        except Exception as filter_error:
            log.warning(f"File filtering failed: {filter_error}")
            filtering_stats["error"] = str(filter_error)
            return source_files, original_count, filtering_stats

    @staticmethod
    def _extract_provider_uuid(file_data: Any) -> str | None:
        """Extract provider_file_uuid from file data, handling different formats."""
        if hasattr(file_data, "provider_file_uuid") and file_data.provider_file_uuid:
            return file_data.provider_file_uuid
        elif isinstance(file_data, dict) and file_data.get("provider_file_uuid"):
            return file_data["provider_file_uuid"]
        return None

    @staticmethod
    def _extract_file_path(file_data: Any) -> str | None:
        """Extract file_path from file data, handling different formats."""
        if hasattr(file_data, "file_path") and file_data.file_path:
            return file_data.file_path
        elif isinstance(file_data, dict) and file_data.get("file_path"):
            return file_data["file_path"]
        return None

    @staticmethod
    def _generate_file_path_hash(file_path: str) -> str:
        """Generate a short hash for file path to differentiate files with same provider_uuid.

        Uses SHA256 with 12 characters for better collision resistance while keeping
        cache keys reasonably short.
        """
        return hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _create_cache_key(workflow_id: str, provider_uuid: str, file_path: str) -> str:
        """Create cache key that uniquely identifies a file by provider_uuid AND file_path.

        This prevents conflicts when multiple files with same content (same provider_uuid)
        but different paths exist.
        """
        file_path_hash = ActiveFileManager._generate_file_path_hash(file_path)
        return f"file_active:{workflow_id}:{provider_uuid}:{file_path_hash}"

    @staticmethod
    def _handle_cache_check(
        file_tracking_data: dict[str, dict],
        workflow_id: str,
        execution_id: str,
        log: LoggerProtocol,
    ) -> dict[str, Any]:
        """Handle cache checking operations using file-path-aware cache keys."""
        cache = RedisCacheBackend()
        active_files_to_skip = set()  # Set of file_keys to skip
        stats = {
            "cache_active": [],
            "processing_files": [],
            "cache_created": 0,
            "cache_errors": 0,
        }

        # Check which files are already active using file-path-aware cache keys
        for file_key, tracking_info in file_tracking_data.items():
            provider_uuid = tracking_info["provider_uuid"]
            file_path = tracking_info["file_path"]

            # Create file-path-aware cache key
            cache_key = ActiveFileManager._create_cache_key(
                workflow_id, provider_uuid, file_path
            )
            cached_active = cache.get(cache_key)

            if cached_active and isinstance(cached_active, dict):
                cached_execution_id = cached_active.get("execution_id")
                cached_file_path = cached_active.get("file_path", "unknown")

                log.debug(
                    f"File {file_key}: cached_execution_id={cached_execution_id}, current_execution_id={execution_id}"
                )
                log.debug(f"  Cache path: {cached_file_path}, Current path: {file_path}")

                if cached_execution_id != execution_id:
                    active_files_to_skip.add(
                        file_key
                    )  # Track by file_key, not provider_uuid
                    stats["cache_active"].append(file_key)
                    log.debug(
                        f"File {file_key} already active by execution {cached_execution_id}, will skip"
                    )
                else:
                    log.debug(
                        f"File {file_key} cached by same execution {execution_id}, will process"
                    )

        if active_files_to_skip:
            log.info(
                f"⚡ Found {len(active_files_to_skip)} files already active in cache"
            )

        return {"active_files": active_files_to_skip, "stats": stats}

    @staticmethod
    def _create_cache_entries_for_selected_files(
        final_files_to_process: dict[str, Any],
        file_tracking_data: dict[str, dict],
        workflow_id: str,
        execution_id: str,
        log: LoggerProtocol,
        filtering_stats: dict[str, Any],
    ) -> None:
        """Create cache entries only for files that will actually be processed.

        Uses file-path-aware cache keys to differentiate files with the same content
        but different paths.
        """
        if not final_files_to_process:
            return

        cache = RedisCacheBackend()
        cache_created = 0
        cache_errors = 0
        processing_files = []

        log.info(
            f"Creating cache entries for {len(final_files_to_process)} final selected files"
        )

        for file_key, file_data in final_files_to_process.items():
            # Get tracking info for this file
            tracking_info = file_tracking_data.get(file_key)
            if not tracking_info:
                log.warning(f"No tracking info found for file: {file_key}")
                continue

            provider_uuid = tracking_info["provider_uuid"]
            file_path = tracking_info["file_path"]

            if not provider_uuid:
                continue

            success = ActiveFileManager._create_cache_entry(
                cache=cache,
                workflow_id=workflow_id,
                execution_id=execution_id,
                provider_uuid=provider_uuid,
                file_path=file_path,
                log=log,
            )

            if success:
                cache_created += 1
                processing_files.append(file_key)
                log.debug(
                    f"Created file-path-aware cache entry for: {file_key} ({provider_uuid})"
                )
            else:
                cache_errors += 1

        # Update statistics with the actual cache creation results
        filtering_stats["cache_created"] = cache_created
        filtering_stats["cache_errors"] = cache_errors
        filtering_stats["processing_files"] = processing_files

        if cache_created > 0:
            log.info(
                f"🔒 Successfully created {cache_created} cache entries for final selection"
            )

    @staticmethod
    def _create_cache_entry(
        cache: RedisCacheBackend,
        workflow_id: str,
        execution_id: str,
        provider_uuid: str,
        file_path: str,
        log: LoggerProtocol,
        ttl: int = 300,
    ) -> bool:
        """Create a cache entry for an active file using file-path-aware key."""
        try:
            cache_key = ActiveFileManager._create_cache_key(
                workflow_id, provider_uuid, file_path
            )
            cache_data = {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "provider_file_uuid": provider_uuid,
                "file_path": file_path,  # Include file path in cache data
                "status": "EXECUTING",
                "created_at": time.time(),
            }

            cache.set(cache_key, cache_data, ttl=ttl)
            log.debug(f"Created cache entry for {provider_uuid} at {file_path}")
            return True

        except Exception as cache_set_error:
            log.warning(
                f"Failed to create cache entry for {provider_uuid}: {cache_set_error}"
            )
            return False

    @staticmethod
    def _check_database_active_files(
        api_client: Any,
        workflow_id: str,
        execution_id: str,
        provider_file_map: dict[str, str],
        log: LoggerProtocol,
    ) -> set[str]:
        """Check database for active files and return set of active provider UUIDs."""
        active_files_response = api_client.check_files_active_processing(
            workflow_id=workflow_id,
            provider_file_uuids=list(provider_file_map.keys()),
            current_execution_id=execution_id,
        )

        if active_files_response.success:
            active_files_data = active_files_response.data
            return {uuid for uuid, is_active in active_files_data.items() if is_active}
        else:
            log.warning(
                f"Database active file check failed: {active_files_response.error}"
            )
            return set()

    @staticmethod
    def _filter_source_files_by_keys(
        source_files: dict[str, Any],
        active_file_keys_to_skip: set[str],
        log: LoggerProtocol,
    ) -> tuple[dict[str, Any], int]:
        """Filter source_files dict to remove active files by file keys."""
        for file_key in active_file_keys_to_skip:
            if file_key in source_files:
                del source_files[file_key]
                log.debug(f"Removed active file: {file_key}")

        new_count = len(source_files)
        return source_files, new_count

    @staticmethod
    def _filter_source_files(
        source_files: dict[str, Any],
        active_files_to_skip: set[str],
        provider_file_map: dict[str, str],
        log: LoggerProtocol,
    ) -> tuple[dict[str, Any], int]:
        """Filter source_files dict to remove active files (legacy method)."""
        files_to_remove = [
            provider_file_map[provider_uuid]
            for provider_uuid in active_files_to_skip
            if provider_uuid in provider_file_map
        ]

        for file_key in files_to_remove:
            del source_files[file_key]

        new_count = len(source_files)
        return source_files, new_count

    @staticmethod
    def cleanup_cache_entries(
        provider_file_uuids: list[str],
        workflow_id: str,
        log: LoggerProtocol | None = None,
    ) -> int:
        """Clean up file-path-aware cache entries for completed file processing.

        Uses pattern matching to find all cache entries for the given provider UUIDs
        since we don't have the file paths available during cleanup.

        Args:
            provider_file_uuids: List of provider file UUIDs to clean up
            workflow_id: Workflow ID
            log: Optional logger instance

        Returns:
            Number of cache entries cleaned up
        """
        logger_instance = log or logger

        if not provider_file_uuids:
            return 0

        try:
            cache = RedisCacheBackend()
            cleaned_count = 0

            for provider_uuid in provider_file_uuids:
                # Find all file-path-aware cache entries for this provider_uuid
                pattern = f"file_active:{workflow_id}:{provider_uuid}:*"
                try:
                    # Get all keys matching the pattern
                    matching_keys = cache.keys(pattern)
                    for key in matching_keys:
                        if cache.delete(key):
                            cleaned_count += 1
                            logger_instance.debug(f"Cleaned up cache entry: {key}")
                except Exception as pattern_error:
                    logger_instance.warning(
                        f"Failed to cleanup entries for {provider_uuid}: {pattern_error}"
                    )

            if cleaned_count > 0:
                logger_instance.info(
                    f"🧹 Cleaned up {cleaned_count} active file cache entries"
                )

            return cleaned_count

        except Exception as cleanup_error:
            logger_instance.warning(f"Failed to cleanup cache entries: {cleanup_error}")
            return 0


# Convenience functions for common operations
def filter_active_files(
    source_files: dict[str, Any],
    workflow_id: str,
    execution_id: str,
    api_client: Any,
    logger_instance: LoggerProtocol | None = None,
    final_files_to_process: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Convenience function that delegates to ActiveFileManager.filter_and_cache_files()."""
    return ActiveFileManager.filter_and_cache_files(
        source_files=source_files,
        workflow_id=workflow_id,
        execution_id=execution_id,
        api_client=api_client,
        logger_instance=logger_instance,
        final_files_to_process=final_files_to_process,
    )


def cleanup_active_file_cache(
    provider_file_uuids: list[str],
    workflow_id: str,
    logger_instance: LoggerProtocol | None = None,
) -> int:
    """Convenience function that delegates to ActiveFileManager.cleanup_cache_entries()."""
    return ActiveFileManager.cleanup_cache_entries(
        provider_file_uuids=provider_file_uuids,
        workflow_id=workflow_id,
        log=logger_instance,
    )
