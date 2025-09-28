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
import os
import time
from typing import Any, Protocol

from ...api.internal_client import InternalAPIClient
from ...cache.cache_backends import RedisCacheBackend
from ...infrastructure.logging import WorkerLogger

# Constants for cache configuration
DEFAULT_ACTIVE_FILE_CACHE_TTL = 300  # 5 minutes
MAX_ACTIVE_FILE_CACHE_TTL = 3600  # 1 hour maximum


def get_active_file_cache_ttl() -> int:
    """Get the configurable TTL for active file cache entries.

    Returns:
        TTL in seconds, with sensible defaults and bounds checking
    """
    try:
        ttl = int(os.environ.get("ACTIVE_FILE_CACHE_TTL", DEFAULT_ACTIVE_FILE_CACHE_TTL))
        # Ensure TTL is within reasonable bounds
        return min(max(ttl, 60), MAX_ACTIVE_FILE_CACHE_TTL)  # Between 1 minute and 1 hour
    except (ValueError, TypeError):
        return DEFAULT_ACTIVE_FILE_CACHE_TTL


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
    def create_cache_entries(
        source_files: dict[str, Any],
        files_to_cache: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        logger_instance: LoggerProtocol | None = None,
    ) -> dict[str, Any]:
        """Create cache entries for files to prevent race conditions (cache-only, no filtering).

        This method ONLY creates cache entries for race condition prevention. It does NOT
        filter files or modify the source_files dictionary. Use this after FilterPipeline
        has already applied all necessary filtering including ActiveFileFilter.

        Args:
            source_files: Dictionary of all source files (used for file_tracking_data)
            files_to_cache: Dictionary of specific files to create cache entries for
            workflow_id: Workflow identifier
            execution_id: Current execution identifier
            logger_instance: Optional logger override (uses module logger if None)

        Returns:
            Cache statistics dictionary with creation results

        Example:
            >>> # After FilterPipeline has filtered files
            >>> cache_stats = ActiveFileManager.create_cache_entries(
            ...     source_files=all_files,  # Original files for tracking data
            ...     files_to_cache=filtered_files,  # Only cache these specific files
            ...     workflow_id="workflow-123",
            ...     execution_id="exec-456",
            ... )
            >>> print(f"Created {cache_stats['cache_created']} cache entries")
        """
        log = logger_instance or logger

        if not files_to_cache:
            return {
                "cache_created": 0,
                "cache_errors": 0,
                "processing_files": [],
            }

        cache_stats = {
            "cache_created": 0,
            "cache_errors": 0,
            "processing_files": [],
        }

        try:
            # Extract provider_file_uuids and file paths from source files for tracking data
            file_tracking_data = {}  # file_key -> {provider_uuid, file_path, file_data} mapping

            for file_key, file_data in source_files.items():
                provider_uuid = ActiveFileManager._extract_provider_uuid(file_data)
                file_path = ActiveFileManager._extract_file_path(file_data)

                if provider_uuid:
                    file_tracking_data[file_key] = {
                        "provider_uuid": provider_uuid,
                        "file_path": file_path
                        or file_key,  # fallback to file_key if no file_path
                        "file_data": file_data,
                    }

            if not file_tracking_data:
                log.warning(
                    "No provider_file_uuid found in source files, skipping cache creation"
                )
                return cache_stats

            log.info(
                f"🔒 Creating cache entries for {len(files_to_cache)} files to prevent race conditions"
            )

            # Create cache entries only for the specified files
            ActiveFileManager._create_cache_entries_for_selected_files(
                final_files_to_process=files_to_cache,
                file_tracking_data=file_tracking_data,
                workflow_id=workflow_id,
                execution_id=execution_id,
                log=log,
                filtering_stats=cache_stats,
            )

            log.info(
                f"✅ Cache creation complete: {cache_stats['cache_created']} entries created, "
                f"{cache_stats['cache_errors']} errors"
            )

        except Exception as cache_error:
            log.warning(f"Cache entry creation failed: {cache_error}")
            cache_stats["error"] = str(cache_error)

        return cache_stats

    @staticmethod
    def create_cache_entries_simple(
        files_to_cache: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        logger_instance: LoggerProtocol | None = None,
    ) -> dict[str, Any]:
        """Create cache entries for files to prevent race conditions (simplified API).

        This is a simplified version of create_cache_entries() for cases where you only
        have the final filtered files to cache (e.g., in discovery methods after FilterPipeline).
        Use this when source_files and files_to_cache would be the same dictionary.

        Args:
            files_to_cache: Dictionary of files to create cache entries for
            workflow_id: Workflow identifier
            execution_id: Current execution identifier
            logger_instance: Optional logger override (uses module logger if None)

        Returns:
            Cache statistics dictionary with creation results

        Example:
            >>> # After FilterPipeline in discovery methods
            >>> cache_stats = ActiveFileManager.create_cache_entries_simple(
            ...     files_to_cache=final_filtered_files,
            ...     workflow_id="workflow-123",
            ...     execution_id="exec-456",
            ... )
            >>> print(f"Created {cache_stats['cache_created']} cache entries")
        """
        # Delegate to the full method with same dict for both parameters
        return ActiveFileManager.create_cache_entries(
            source_files=files_to_cache,
            files_to_cache=files_to_cache,
            workflow_id=workflow_id,
            execution_id=execution_id,
            logger_instance=logger_instance,
        )

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
        """Handle cache checking operations using batch Redis operations for performance."""
        cache = RedisCacheBackend()
        active_files_to_skip = set()  # Set of file_keys to skip
        stats = {
            "cache_active": [],
            "processing_files": [],
            "cache_created": 0,
            "cache_errors": 0,
        }

        if not file_tracking_data:
            return {"active_files": active_files_to_skip, "stats": stats}

        try:
            # BATCH OPTIMIZATION: Pre-compute all cache keys and fetch in single operation
            cache_key_to_file_key = {}  # cache_key -> file_key mapping
            file_key_to_tracking = {}  # file_key -> tracking_info mapping

            # Pre-compute all cache keys
            for file_key, tracking_info in file_tracking_data.items():
                provider_uuid = tracking_info["provider_uuid"]
                file_path = tracking_info["file_path"]

                cache_key = ActiveFileManager._create_cache_key(
                    workflow_id, provider_uuid, file_path
                )
                cache_key_to_file_key[cache_key] = file_key
                file_key_to_tracking[file_key] = tracking_info

            # Single batch Redis call instead of N individual calls
            cache_keys = list(cache_key_to_file_key.keys())
            log.debug(f"Batch checking {len(cache_keys)} cache keys for active files")

            cached_results = cache.mget(cache_keys)

            # Process batch results
            for cache_key, cached_data in cached_results.items():
                file_key = cache_key_to_file_key[cache_key]
                tracking_info = file_key_to_tracking[file_key]

                if cached_data and isinstance(cached_data, dict):
                    # Extract data from cache wrapper
                    cached_active = cached_data.get("data", {})

                    if isinstance(cached_active, dict):
                        cached_execution_id = cached_active.get("execution_id")
                        cached_file_path = cached_active.get("file_path", "unknown")
                        current_file_path = tracking_info["file_path"]

                        log.debug(
                            f"File {file_key}: cached_execution_id={cached_execution_id}, current_execution_id={execution_id}"
                        )
                        log.debug(
                            f"  Cache path: {cached_file_path}, Current path: {current_file_path}"
                        )

                        if cached_execution_id != execution_id:
                            active_files_to_skip.add(file_key)
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
                    f"⚡ Found {len(active_files_to_skip)} files already active in cache (batch check)"
                )

        except Exception as batch_error:
            log.warning(
                f"Batch cache check failed, falling back to individual checks: {batch_error}"
            )
            # Fallback to individual checks if batch fails
            return ActiveFileManager._handle_cache_check_fallback(
                file_tracking_data, workflow_id, execution_id, log
            )

        return {"active_files": active_files_to_skip, "stats": stats}

    @staticmethod
    def _handle_cache_check_fallback(
        file_tracking_data: dict[str, dict],
        workflow_id: str,
        execution_id: str,
        log: LoggerProtocol,
    ) -> dict[str, Any]:
        """Fallback method using individual Redis operations if batch fails."""
        cache = RedisCacheBackend()
        active_files_to_skip = set()
        stats = {
            "cache_active": [],
            "processing_files": [],
            "cache_created": 0,
            "cache_errors": 0,
        }

        # Fallback to individual cache checks
        for file_key, tracking_info in file_tracking_data.items():
            provider_uuid = tracking_info["provider_uuid"]
            file_path = tracking_info["file_path"]

            try:
                cache_key = ActiveFileManager._create_cache_key(
                    workflow_id, provider_uuid, file_path
                )
                cached_active = cache.get(cache_key)

                if cached_active and isinstance(cached_active, dict):
                    cached_execution_id = cached_active.get("execution_id")
                    if cached_execution_id != execution_id:
                        active_files_to_skip.add(file_key)
                        stats["cache_active"].append(file_key)

            except Exception as key_error:
                log.debug(f"Individual cache check failed for {file_key}: {key_error}")

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

        OPTIMIZED: Uses batch Redis operations for better performance with large file sets.
        Uses file-path-aware cache keys to differentiate files with the same content
        but different paths.
        """
        if not final_files_to_process:
            return

        cache = RedisCacheBackend()
        ttl = get_active_file_cache_ttl()  # Use configurable TTL

        log.info(
            f"Creating cache entries for {len(final_files_to_process)} final selected files (TTL: {ttl}s)"
        )

        try:
            # BATCH OPTIMIZATION: Prepare all cache entries for batch creation
            batch_cache_data = {}  # cache_key -> (cache_data, ttl)
            processing_files = []
            cache_errors = 0

            for file_key, file_data in final_files_to_process.items():
                # Get tracking info for this file
                tracking_info = file_tracking_data.get(file_key)
                if not tracking_info:
                    log.warning(f"No tracking info found for file: {file_key}")
                    cache_errors += 1
                    continue

                provider_uuid = tracking_info["provider_uuid"]
                file_path = tracking_info["file_path"]

                if not provider_uuid:
                    cache_errors += 1
                    continue

                try:
                    # Prepare cache entry data
                    cache_key = ActiveFileManager._create_cache_key(
                        workflow_id, provider_uuid, file_path
                    )
                    cache_data = {
                        "execution_id": execution_id,
                        "workflow_id": workflow_id,
                        "provider_file_uuid": provider_uuid,
                        "file_path": file_path,
                        "status": "EXECUTING",
                        "created_at": time.time(),
                    }

                    batch_cache_data[cache_key] = (cache_data, ttl)
                    processing_files.append(file_key)
                    log.debug(f"Prepared cache entry for: {file_key} ({provider_uuid})")

                except Exception as prep_error:
                    log.warning(
                        f"Failed to prepare cache entry for {file_key}: {prep_error}"
                    )
                    cache_errors += 1

            # Single batch Redis operation instead of N individual operations
            if batch_cache_data:
                cache_created = cache.mset(batch_cache_data)
                log.info(
                    f"🔒 Batch created {cache_created}/{len(batch_cache_data)} cache entries "
                    f"for race condition prevention"
                )
            else:
                cache_created = 0
                log.warning("No valid cache entries prepared for batch creation")

        except Exception as batch_error:
            log.warning(
                f"Batch cache creation failed, falling back to individual operations: {batch_error}"
            )
            # Fallback to individual cache creation
            cache_created, cache_errors, processing_files = (
                ActiveFileManager._create_cache_entries_fallback(
                    final_files_to_process=final_files_to_process,
                    file_tracking_data=file_tracking_data,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    log=log,
                    ttl=ttl,
                )
            )

        # Update statistics with the actual cache creation results
        filtering_stats["cache_created"] = cache_created
        filtering_stats["cache_errors"] = cache_errors
        filtering_stats["processing_files"] = processing_files

    @staticmethod
    def _create_cache_entries_fallback(
        final_files_to_process: dict[str, Any],
        file_tracking_data: dict[str, dict],
        workflow_id: str,
        execution_id: str,
        log: LoggerProtocol,
        ttl: int,
    ) -> tuple[int, int, list[str]]:
        """Fallback method for individual cache creation if batch fails."""
        cache = RedisCacheBackend()
        cache_created = 0
        cache_errors = 0
        processing_files = []

        for file_key, file_data in final_files_to_process.items():
            tracking_info = file_tracking_data.get(file_key)
            if not tracking_info:
                cache_errors += 1
                continue

            provider_uuid = tracking_info["provider_uuid"]
            file_path = tracking_info["file_path"]

            if not provider_uuid:
                cache_errors += 1
                continue

            success = ActiveFileManager._create_cache_entry(
                cache=cache,
                workflow_id=workflow_id,
                execution_id=execution_id,
                provider_uuid=provider_uuid,
                file_path=file_path,
                log=log,
                ttl=ttl,
            )

            if success:
                cache_created += 1
                processing_files.append(file_key)
            else:
                cache_errors += 1

        return cache_created, cache_errors, processing_files

    @staticmethod
    def _create_cache_entry(
        cache: RedisCacheBackend,
        workflow_id: str,
        execution_id: str,
        provider_uuid: str,
        file_path: str,
        log: LoggerProtocol,
        ttl: int | None = None,
    ) -> bool:
        """Create a cache entry for an active file using file-path-aware key."""
        try:
            # Use configurable TTL if not provided
            if ttl is None:
                ttl = get_active_file_cache_ttl()

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
        api_client: InternalAPIClient,
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

        OPTIMIZED: Uses non-blocking SCAN instead of blocking KEYS for production safety.
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
                    # Use non-blocking SCAN instead of blocking KEYS
                    matching_keys = cache.scan_keys(
                        pattern, count=50
                    )  # Small batches for safety

                    if matching_keys:
                        # Delete in batches to avoid large delete operations
                        batch_size = 100
                        for i in range(0, len(matching_keys), batch_size):
                            batch_keys = matching_keys[i : i + batch_size]
                            try:
                                # Batch delete for efficiency
                                deleted_count = cache.redis_client.delete(*batch_keys)
                                cleaned_count += deleted_count
                                logger_instance.debug(
                                    f"Cleaned up {deleted_count} cache entries for {provider_uuid} (batch {i//batch_size + 1})"
                                )
                            except Exception as batch_error:
                                logger_instance.warning(
                                    f"Failed to delete batch for {provider_uuid}: {batch_error}"
                                )
                                # Fallback to individual deletion
                                for key in batch_keys:
                                    try:
                                        if cache.delete(key):
                                            cleaned_count += 1
                                    except Exception:
                                        pass  # Continue with other keys

                except Exception as pattern_error:
                    logger_instance.warning(
                        f"Failed to cleanup entries for {provider_uuid}: {pattern_error}"
                    )

            if cleaned_count > 0:
                logger_instance.info(
                    f"🧹 Cleaned up {cleaned_count} active file cache entries (non-blocking SCAN)"
                )

            return cleaned_count

        except Exception as cleanup_error:
            logger_instance.warning(f"Failed to cleanup cache entries: {cleanup_error}")
            return 0


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
