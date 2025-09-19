"""File Discovery Service

This module provides the StreamingFileDiscovery service, moved to shared/processing
to avoid circular imports and provide clean separation of concerns.
"""

import time
from typing import Any

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.core.data_models import ConnectionType, FileHashData, FileOperationConstants
from unstract.core.file_operations import FileOperations

from ..infrastructure.logging import WorkerLogger
from .filter_pipeline import FilterPipeline

logger = WorkerLogger.get_logger(__name__)


class StreamingFileDiscovery:
    """Streams files from directories with early filtering and termination.

    This class replaces the inefficient "discover-all-then-filter" approach with
    a streaming system that:
    1. Walks directories incrementally
    2. Applies ALL filters as files are discovered
    3. Stops immediately when limit is reached
    4. Uses batch processing for efficient API calls
    """

    def __init__(
        self,
        source_fs: UnstractFileSystem,
        api_client,  # Removed type hint to avoid import
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        connector_id: str | None = None,
    ):
        """Initialize streaming file discovery.

        Args:
            source_fs: Filesystem connector
            api_client: API client for backend communication
            workflow_id: Workflow ID for filtering
            execution_id: Current execution ID
            organization_id: Organization ID
            connector_id: Optional connector ID for metadata
        """
        self.source_fs = source_fs
        self.api_client = api_client
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.connector_id = connector_id
        self.fs_fsspec = source_fs.get_fsspec_fs()

    def discover_files_streaming(
        self,
        directories: list[str],
        patterns: list[str],
        recursive: bool,
        file_hard_limit: int,
        filter_pipeline: FilterPipeline,
        batch_size: int = 100,
    ) -> tuple[dict[str, FileHashData], int]:
        """Discover files using streaming with early filtering.

        This is the main entry point that replaces the old _get_matched_files.
        It discovers files incrementally and applies all filters immediately.

        Args:
            directories: List of directories to search
            patterns: File patterns to match
            recursive: Whether to search recursively
            file_hard_limit: Maximum files to return (hard stop)
            filter_pipeline: Pipeline of filters to apply
            batch_size: Size of batches for processing

        Returns:
            Tuple of (matched_files, count)
        """
        start_time = time.time()

        matched_files: dict[str, FileHashData] = {}
        batch_buffer: list[tuple[str, dict[str, Any]]] = []

        # Metrics tracking
        metrics = {
            "total_files_discovered": 0,
            "files_pattern_matched": 0,
            "files_after_filtering": 0,
            "batches_processed": 0,
            "directories_walked": 0,
        }

        # Calculate max depth for recursive search
        max_depth = int(FileOperationConstants.MAX_RECURSIVE_DEPTH) if recursive else 1

        logger.info(
            f"[StreamingDiscovery] Starting streaming discovery for {len(directories)} directories "
            f"with limit={file_hard_limit}, batch_size={batch_size}, recursive={recursive}, patterns={patterns}, "
            f"max_depth={max_depth}"
        )

        try:
            for directory in directories:
                # Check if we've reached the limit
                if len(matched_files) >= file_hard_limit:
                    logger.info(
                        f"[StreamingDiscovery] Reached file limit ({file_hard_limit}), "
                        f"stopping discovery early"
                    )
                    break

                logger.info(f"[StreamingDiscovery] Processing directory: {directory}")

                # Walk directory with max depth control
                for root, dirs, _ in self.fs_fsspec.walk(directory, maxdepth=max_depth):
                    metrics["directories_walked"] += 1

                    # Check limit before processing directory
                    if len(matched_files) >= file_hard_limit:
                        break

                    try:
                        # Get all items in directory with metadata
                        fs_metadata_list: list[dict[str, Any]] = self.fs_fsspec.listdir(
                            root
                        )
                    except Exception as e:
                        logger.warning(f"Failed to list directory {root}: {e}")
                        continue

                    # Process files in this directory
                    for fs_metadata in fs_metadata_list:
                        # Early termination check
                        if len(matched_files) >= file_hard_limit:
                            break

                        file_path = fs_metadata.get("name")
                        if not file_path:
                            logger.info(
                                f"DEBUG: [StreamingDiscovery] Skipping item with no name: {fs_metadata}"
                            )
                            continue

                        # Log detailed file metadata for debugging
                        file_type = fs_metadata.get("type", "unknown")
                        file_size = fs_metadata.get("size", "unknown")
                        logger.info(
                            f"DEBUG: [StreamingDiscovery] Discovered item: '{file_path}' (type: {file_type}, size: {file_size})"
                        )

                        metrics["total_files_discovered"] += 1

                        # Skip directories with detailed logging
                        is_directory = self._is_directory(file_path, fs_metadata, dirs)
                        if is_directory:
                            logger.info(
                                f"DEBUG: [StreamingDiscovery] Skipping directory: {file_path}"
                            )
                            continue

                        logger.info(
                            f"DEBUG: [StreamingDiscovery] File passed directory check: {file_path}"
                        )

                        # Apply pattern filter first (cheapest)
                        pattern_matches = self._matches_patterns(file_path, patterns)
                        if not pattern_matches:
                            logger.info(
                                f"DEBUG: [StreamingDiscovery] File failed pattern match: {file_path} (patterns: {patterns})"
                            )
                            continue

                        logger.info(
                            f"DEBUG: [StreamingDiscovery] File passed pattern match: {file_path}"
                        )
                        metrics["files_pattern_matched"] += 1

                        # Add to batch buffer
                        batch_buffer.append((file_path, fs_metadata))
                        logger.info(
                            f"DEBUG: [StreamingDiscovery] Added to batch buffer: {file_path} (buffer size: {len(batch_buffer)})"
                        )

                        # Process batch when full
                        if len(batch_buffer) >= batch_size:
                            self._process_batch(
                                batch_buffer,
                                matched_files,
                                filter_pipeline,
                                file_hard_limit,
                            )
                            metrics["batches_processed"] += 1
                            batch_buffer = []

                            # Check if we've reached limit after batch processing
                            if len(matched_files) >= file_hard_limit:
                                logger.info(
                                    "[StreamingDiscovery] Reached limit after batch processing"
                                )
                                break

            # Process remaining files in buffer
            if batch_buffer and len(matched_files) < file_hard_limit:
                self._process_batch(
                    batch_buffer, matched_files, filter_pipeline, file_hard_limit
                )
                metrics["batches_processed"] += 1

            # Ensure we never exceed the hard limit
            if len(matched_files) > file_hard_limit:
                logger.info(
                    f"[StreamingDiscovery] Trimming results from {len(matched_files)} to {file_hard_limit}"
                )
                matched_files = dict(list(matched_files.items())[:file_hard_limit])

            final_count = len(matched_files)
            metrics["files_after_filtering"] = final_count
            elapsed_time = time.time() - start_time

            # Log comprehensive metrics
            logger.info(
                f"[StreamingDiscovery] 🎯 Discovery complete in {elapsed_time:.2f}s:\n"
                f"  • Directories walked: {metrics['directories_walked']}\n"
                f"  • Total files discovered: {metrics['total_files_discovered']}\n"
                f"  • Files matching patterns: {metrics['files_pattern_matched']}\n"
                f"  • Files after all filters: {metrics['files_after_filtering']}\n"
                f"  • Batches processed: {metrics['batches_processed']}\n"
                f"  • Hard limit: {file_hard_limit}\n"
                f"  • Early termination: {'Yes' if final_count >= file_hard_limit else 'No'}"
            )

            # Performance metrics
            if metrics["total_files_discovered"] > 0:
                filter_efficiency = (
                    (metrics["total_files_discovered"] - final_count)
                    / metrics["total_files_discovered"]
                    * 100
                )
                logger.info(
                    f"[StreamingDiscovery] 📊 Performance metrics:\n"
                    f"  • Filter efficiency: {filter_efficiency:.1f}% files filtered out\n"
                    f"  • Discovery rate: {metrics['total_files_discovered'] / elapsed_time:.0f} files/sec\n"
                    f"  • Final rate: {final_count / elapsed_time:.0f} accepted files/sec"
                )

            return matched_files, final_count

        except Exception as e:
            logger.error(
                f"[StreamingDiscovery] Error during file discovery: {e}", exc_info=True
            )
            # Return what we've collected so far
            return matched_files, len(matched_files)

    def _process_batch(
        self,
        batch_buffer: list[tuple[str, dict[str, Any]]],
        matched_files: dict[str, FileHashData],
        filter_pipeline: FilterPipeline,
        file_hard_limit: int,
    ) -> None:
        """Process a batch of files through the filter pipeline.

        Args:
            batch_buffer: Buffer of (file_path, metadata) tuples
            matched_files: Dictionary to add accepted files to
            filter_pipeline: Pipeline of filters to apply
            file_hard_limit: Maximum number of files to collect
        """
        if not batch_buffer:
            return

        logger.info(f"[StreamingDiscovery] Processing batch of {len(batch_buffer)} files")

        # Log the files being processed in this batch for debugging
        batch_files = [file_path for file_path, _ in batch_buffer]
        logger.info(f"DEBUG: [StreamingDiscovery] Batch files: {batch_files}")

        # Convert batch to FileHashData objects with defensive validation
        file_hash_batch: dict[str, FileHashData] = {}
        for file_path, fs_metadata in batch_buffer:
            try:
                # Validate file path and extract file name
                if not file_path or not isinstance(file_path, str):
                    logger.warning(
                        f"[StreamingDiscovery] Skipping invalid file path: {file_path}"
                    )
                    continue

                # Extract and validate file name
                import os

                file_name = os.path.basename(file_path.rstrip("/"))
                if not file_name or file_name in ["", ".", ".."]:
                    logger.warning(
                        f"[StreamingDiscovery] Skipping file with invalid name: '{file_path}' -> '{file_name}'"
                    )
                    continue

                # Check if this looks like a directory path
                if file_path.endswith("/") or not file_name:
                    logger.info(
                        f"DEBUG: [StreamingDiscovery] Skipping directory-like path: {file_path}"
                    )
                    continue

                logger.info(
                    f"DEBUG: [StreamingDiscovery] Processing file: '{file_path}' (name: '{file_name}', size: {fs_metadata.get('size', 0)})"
                )

                # Add connector_id to metadata if available
                if self.connector_id:
                    fs_metadata = fs_metadata.copy()
                    fs_metadata["connector_id"] = self.connector_id

                # Create FileHashData object with proper error handling
                file_hash = FileOperations.create_file_hash_from_backend_logic(
                    file_path=file_path,
                    source_fs=self.source_fs,
                    source_connection_type=ConnectionType.FILESYSTEM,
                    file_size=fs_metadata.get("size", 0),
                    fs_metadata=fs_metadata,
                    compute_content_hash=False,  # Only use provider_file_uuid
                )

                file_hash_batch[file_path] = file_hash
                logger.info(
                    f"DEBUG: [StreamingDiscovery] Successfully created FileHashData for: {file_path}"
                )

            except ValueError as ve:
                logger.error(
                    f"[StreamingDiscovery] FileHashData creation failed for '{file_path}': {ve}"
                )
                logger.info(f"DEBUG: [StreamingDiscovery] File metadata: {fs_metadata}")
                continue
            except Exception as e:
                logger.error(
                    f"[StreamingDiscovery] Unexpected error processing '{file_path}': {e}",
                    exc_info=True,
                )
                continue

        # Apply filter pipeline to batch
        filtered_batch = filter_pipeline.apply_filters(
            files=file_hash_batch,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            api_client=self.api_client,
            organization_id=self.organization_id,  # Fix: Add missing organization_id
        )

        logger.info(
            f"[StreamingDiscovery] Batch processing complete: {len(batch_buffer)} raw → {len(file_hash_batch)} valid → {len(filtered_batch)} filtered"
        )

        # Add filtered files to results (respecting limit)
        added_count = 0
        for file_path, file_hash in filtered_batch.items():
            if len(matched_files) >= file_hard_limit:
                break
            matched_files[file_path] = file_hash
            added_count += 1

        if added_count > 0:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Added {added_count} files to final results"
            )

    def _is_directory(
        self, file_path: str, metadata: dict[str, Any], dirs: list[str]
    ) -> bool:
        """Check if path is a directory using multiple detection methods.

        Args:
            file_path: Path to check
            metadata: File metadata from fsspec
            dirs: List of directories from walk

        Returns:
            True if path is a directory
        """
        import os

        if not file_path:
            return False

        # 1. Check if path ends with directory separator
        if file_path.endswith("/") or file_path.endswith("\\"):
            logger.info(
                f"DEBUG: [StreamingDiscovery] Directory detected by path suffix: {file_path}"
            )
            return True

        # 2. Check if basename is in dirs list from walk
        basename = os.path.basename(file_path)
        if basename in dirs:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Directory detected in dirs list: {file_path}"
            )
            return True

        # 3. Check metadata type with broader detection
        file_type = metadata.get("type", "").lower()
        if file_type in ["directory", "dir", "folder", "d"]:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Directory detected by metadata type '{file_type}': {file_path}"
            )
            return True

        # 4. Check size - directories often have size 0 or None
        file_size = metadata.get("size")
        if file_size is None and metadata.get("type") != "file":
            logger.info(
                f"DEBUG: [StreamingDiscovery] Possible directory (no size, not file type): {file_path}"
            )
            return True

        # 5. Check for common directory characteristics
        if not basename or basename in [".", ".."]:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Directory detected by special name: {file_path}"
            )
            return True

        # 6. Try connector-specific directory check
        try:
            if hasattr(self.source_fs, "is_dir_by_metadata"):
                is_dir = self.source_fs.is_dir_by_metadata(metadata)
                if is_dir:
                    logger.info(
                        f"DEBUG: [StreamingDiscovery] Directory detected by connector-specific check: {file_path}"
                    )
                return is_dir
            else:
                is_dir = self.fs_fsspec.isdir(file_path)
                if is_dir:
                    logger.info(
                        f"DEBUG: [StreamingDiscovery] Directory detected by fsspec.isdir: {file_path}"
                    )
                return is_dir
        except Exception as e:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Directory check failed for {file_path}: {e}"
            )

        # 7. Final check: if no file extension and metadata suggests it might be a directory
        if "." not in basename and file_size == 0:
            logger.info(
                f"DEBUG: [StreamingDiscovery] Possible directory (no extension, zero size): {file_path}"
            )
            # Don't return True here, just log - this is too aggressive

        return False

    def _matches_patterns(self, file_path: str, patterns: list[str]) -> bool:
        """Check if file matches any of the patterns.

        Args:
            file_path: File path to check
            patterns: List of file patterns

        Returns:
            True if file matches any pattern
        """
        if not patterns or patterns == ["*"]:
            return True

        import fnmatch
        import os

        file_name = os.path.basename(file_path)
        for pattern in patterns:
            # Case-insensitive matching
            if fnmatch.fnmatch(file_name.lower(), pattern.lower()):
                return True

        return False
