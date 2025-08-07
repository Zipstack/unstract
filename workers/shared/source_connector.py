"""Unified Source Connector for Workers

This module provides a worker-compatible implementation of the SourceConnector
that matches the exact logic from backend/workflow_manager/endpoint_v2/source.py
"""

import logging
from typing import Any

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.core.data_models import (
    FileHash,
    FileOperationConstants,
    SourceConnectionType,
    SourceKey,
)
from unstract.core.file_operations import FileOperations

from .api_client import InternalAPIClient
from .connector_utils import get_connector_instance

logger = logging.getLogger(__name__)


class WorkerSourceConnector:
    """Worker-compatible source connector matching backend source.py logic exactly.

    This class provides the same file listing functionality as the backend
    SourceConnector but adapted for worker processes that communicate via
    internal APIs rather than direct database access.
    """

    READ_CHUNK_SIZE = FileOperationConstants.READ_CHUNK_SIZE

    def __init__(
        self,
        api_client: InternalAPIClient,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        use_file_history: bool = False,
    ):
        """Initialize the worker source connector.

        Args:
            api_client: Internal API client for backend communication
            workflow_id: Workflow ID
            execution_id: Execution ID
            organization_id: Organization ID
            use_file_history: Whether to use file history for deduplication
        """
        self.api_client = api_client
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.use_file_history = use_file_history
        self.logger = logger

        # Get workflow endpoint configuration via API
        self.endpoint_config = self._get_endpoint_configuration()

    def _get_endpoint_configuration(self) -> dict[str, Any]:
        """Get workflow endpoint configuration from backend."""
        try:
            response = self.api_client.get_workflow_endpoints(
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
            )
            # The API returns endpoints list, we need the first source endpoint
            endpoints = response.get("endpoints", [])
            for endpoint in endpoints:
                if endpoint.get("endpoint_type") == "SOURCE":
                    return endpoint
            # If no source endpoint found, return empty dict
            return {}
        except Exception as e:
            logger.error(f"Failed to get endpoint configuration: {e}")
            raise

    def list_files_from_source(
        self, file_hashes: dict[str, FileHash] | None = None
    ) -> tuple[dict[str, FileHash], int]:
        """List files from source connector matching backend source.py:721.

        Args:
            file_hashes: Optional existing file hashes for API workflows

        Returns:
            tuple: (matched_files, total_count)
        """
        connection_type = self.endpoint_config.get("connection_type")

        if connection_type == SourceConnectionType.FILESYSTEM:
            files, count = self.list_files_from_file_connector()
        elif connection_type == SourceConnectionType.API:
            files, count = self.list_files_from_api_storage(file_hashes or {})
        else:
            raise ValueError(f"Invalid source connection type: {connection_type}")

        # Number files (matching backend source.py:740)
        for index, file_hash in enumerate(files.values(), start=1):
            file_hash.file_number = index

        return files, count

    def list_files_from_file_connector(self) -> tuple[dict[str, FileHash], int]:
        """List files from filesystem connector matching backend source.py:153.

        Returns:
            tuple: (matched_files, total_count)
        """
        # Get connector configuration
        connector_config = self.endpoint_config.get("connector_instance", {})
        connector_id = connector_config.get("connector_id")
        connector_settings = connector_config.get("connector_metadata", {})

        # Get source configuration using unified SourceKey helper methods
        source_config = self.endpoint_config.get("configuration", {})
        required_patterns = SourceKey.get_file_extensions(source_config)
        recursive = SourceKey.get_process_sub_directories(source_config)
        limit = SourceKey.get_max_files(
            source_config, FileOperationConstants.DEFAULT_MAX_FILES
        )
        root_dir_path = connector_settings.get("path", "")
        folders_to_process = SourceKey.get_folders(source_config)

        logger.info(
            f"Source connector configuration - Connector ID: {connector_id}, Root path: '{root_dir_path}', Folders: {folders_to_process}"
        )
        logger.info(
            f"File processing limits - Max files: {limit}, Recursive: {recursive}, Patterns: {required_patterns}"
        )
        logger.debug(f"Raw source_config for max_files debug: {source_config}")

        # Process from root if folder list is empty
        if not folders_to_process:
            folders_to_process = ["/"]

        # Get valid patterns
        patterns = FileOperations.valid_file_patterns(required_patterns)

        logger.info(
            f"Matching for patterns '{', '.join(patterns)}' from "
            f"'{', '.join(folders_to_process)}'"
        )

        # Get filesystem connector
        source_fs = self._get_fs_connector(
            settings=connector_settings, connector_id=connector_id
        )
        source_fs_fsspec = source_fs.get_fsspec_fs()

        # Validate directories
        valid_directories = []
        for input_directory in folders_to_process:
            try:
                # Use connector's root dir resolution (all connectors have this method)
                resolved_directory = source_fs.get_connector_root_dir(
                    input_dir=input_directory, root_path=root_dir_path
                )

                logger.info(
                    f"Checking directory: '{input_directory}' → '{resolved_directory}'"
                )

                # Debug: Try to get bucket info and list root for GCS
                if "google_cloud_storage" in connector_id:
                    try:
                        # Extract bucket name for debugging
                        bucket_name = (
                            resolved_directory.split("/")[0]
                            if "/" in resolved_directory
                            else resolved_directory
                        )
                        logger.info(f"[GCS Debug] Checking bucket: '{bucket_name}'")

                        # Try to list the bucket to see if it exists and is accessible
                        try:
                            bucket_info = source_fs_fsspec.info(bucket_name)
                            logger.info(
                                f"[GCS Debug] Bucket '{bucket_name}' exists with info: {bucket_info}"
                            )
                        except Exception as bucket_error:
                            logger.warning(
                                f"[GCS Debug] Cannot access bucket '{bucket_name}': {bucket_error}"
                            )

                        # Try to list contents of the resolved directory
                        try:
                            dir_contents = source_fs_fsspec.ls(
                                resolved_directory, detail=False
                            )
                            logger.info(
                                f"[GCS Debug] Directory '{resolved_directory}' contents: {dir_contents[:10]}..."
                            )  # First 10 items
                        except Exception as ls_error:
                            logger.warning(
                                f"[GCS Debug] Cannot list directory '{resolved_directory}': {ls_error}"
                            )

                    except Exception as debug_error:
                        logger.warning(f"[GCS Debug] Debug check failed: {debug_error}")

                # Use connector-specific directory check instead of generic fsspec.isdir()
                # This is especially important for GCS where fsspec.isdir() doesn't work correctly
                is_directory = False
                try:
                    if hasattr(source_fs, "is_dir_by_metadata"):
                        # Get directory info and check using connector's method
                        dir_info = source_fs_fsspec.info(resolved_directory)
                        is_directory = source_fs.is_dir_by_metadata(dir_info)
                    else:
                        # Fallback to fsspec's isdir for other connectors
                        is_directory = source_fs_fsspec.isdir(resolved_directory)
                except Exception as dir_check_error:
                    logger.warning(
                        f"Failed to check if '{resolved_directory}' is directory: {dir_check_error}"
                    )
                    is_directory = False

                if not is_directory:
                    logger.warning(
                        f"Source directory not found or not accessible: '{resolved_directory}'. "
                        f"This may be expected if the directory doesn't exist in the connector storage."
                    )
                    continue

                valid_directories.append(resolved_directory)
                logger.info(f"✓ Validated directory: '{resolved_directory}'")

            except Exception as e:
                logger.error(f"Error accessing directory '{input_directory}': {e}")
                continue

        # Process directories
        total_files_to_process = 0
        total_matched_files = {}
        unique_file_paths: set[str] = set()

        for input_directory in valid_directories:
            logger.debug(f"Listing files from: {input_directory}")
            matched_files, count = self._get_matched_files(
                source_fs, input_directory, patterns, recursive, limit, unique_file_paths
            )
            logger.info(f"Matched '{count}' files from '{input_directory}'")
            total_matched_files.update(matched_files)
            total_files_to_process += count

        return total_matched_files, total_files_to_process

    def _get_matched_files(
        self,
        source_fs: UnstractFileSystem,
        input_directory: str,
        patterns: list[str],
        recursive: bool,
        limit: int,
        unique_file_paths: set[str],
    ) -> tuple[dict[str, FileHash], int]:
        """Get matched files from directory with proper batch filtering and limit application.

        This method follows the correct order:
        1. Discover all matching files
        2. Apply batch file history filtering
        3. Apply deduplication
        4. Apply max files limit

        Args:
            source_fs: Filesystem connector
            input_directory: Directory to search
            patterns: File patterns to match
            recursive: Whether to search recursively
            limit: Maximum files to return (applied after all filtering)
            unique_file_paths: Set of already seen file paths

        Returns:
            tuple: (matched_files, count)
        """
        matched_files: dict[str, FileHash] = {}
        count = 0
        max_depth = int(FileOperationConstants.MAX_RECURSIVE_DEPTH) if recursive else 1
        fs_fsspec = source_fs.get_fsspec_fs()

        logger.info(
            f"Starting file discovery - will apply limit after filtering (limit: {limit})"
        )

        # Step 1: Discover ALL matching files first (no limit applied)
        for root, dirs, _ in fs_fsspec.walk(input_directory, maxdepth=max_depth):
            try:
                # Get all items in directory with metadata
                fs_metadata_list: list[dict[str, Any]] = fs_fsspec.listdir(root)
            except Exception as e:
                logger.warning(f"Failed to list directory from path: {root}, error: {e}")
                continue

            # Process directory items WITHOUT limit - discover all files first
            count = FileOperations.process_file_fs_directory(
                fs_metadata_list=fs_metadata_list,
                count=count,
                limit=999999,  # Very large limit during initial discovery
                unique_file_paths=unique_file_paths,
                matched_files=matched_files,
                patterns=patterns,
                source_fs=source_fs,
                source_connection_type=SourceConnectionType.FILESYSTEM,
                dirs=dirs,
                # Pass connector_id so FileHash objects have it in fs_metadata
                connector_id=self.endpoint_config.get("connector_instance", {}).get(
                    "connector_id"
                ),
            )

        logger.info(
            f"Discovery completed: found {len(matched_files)} matching files before filtering"
        )

        # Step 2: Apply batch file history filtering (remove already processed files)
        files_before_history_filtering = len(matched_files)
        if self.use_file_history and matched_files:
            filtered_files = self._apply_file_history_filtering(matched_files)
            logger.info(
                f"File history batch filtering: {len(filtered_files)}/{files_before_history_filtering} files after deduplication"
            )
        else:
            filtered_files = matched_files

        # Step 3: Apply max files limit to the final filtered results
        if len(filtered_files) > limit:
            logger.info(
                f"Applying max files limit: taking {limit} files from {len(filtered_files)} available"
            )
            # Convert to list, take first N files, convert back to dict
            limited_files = dict(list(filtered_files.items())[:limit])
            final_count = len(limited_files)
        else:
            limited_files = filtered_files
            final_count = len(filtered_files)

        logger.info(
            f"File discovery completed: {final_count} files will be processed (limit: {limit})"
        )
        return limited_files, final_count

    def list_files_from_api_storage(
        self, existing_file_hashes: dict[str, FileHash]
    ) -> tuple[dict[str, FileHash], int]:
        """List files from API storage.

        For API workflows, files are already uploaded and we just process them.

        Args:
            existing_file_hashes: Pre-uploaded files

        Returns:
            tuple: (files, count)
        """
        logger.info(f"Listing {len(existing_file_hashes)} files from API storage")

        # Apply file history filtering if enabled
        if self.use_file_history:
            filtered_files = self._apply_file_history_filtering(existing_file_hashes)
            logger.info(
                f"File history filtering: {len(filtered_files)}/{len(existing_file_hashes)} files after deduplication"
            )
            return filtered_files, len(filtered_files)

        return existing_file_hashes, len(existing_file_hashes)

    def _apply_file_history_filtering(
        self, files: dict[str, FileHash]
    ) -> dict[str, FileHash]:
        """Apply file history filtering to remove already processed files.

        Args:
            files: Files to filter

        Returns:
            dict: Filtered files
        """
        if not self.use_file_history:
            return files

        logger.info(f"DEBUG: Starting file history filtering for {len(files)} files")
        logger.info(
            f"DEBUG: use_file_history={self.use_file_history}, workflow_id={self.workflow_id}"
        )

        filtered_files = {}

        try:
            # For ETL/TASK workflows, we'll check file history individually using provider_file_uuid
            # (matches backend behavior which uses provider_file_uuid as primary identifier)

            # Process each file individually to check history by provider_file_uuid
            for file_path, file_data in files.items():
                logger.info(
                    f"DEBUG: Processing file {file_data.file_name} (path: {file_path})"
                )
                logger.info(
                    f"DEBUG: File data - provider_file_uuid: '{file_data.provider_file_uuid}', source_connection_type: '{file_data.source_connection_type}'"
                )
                # Skip files without provider_file_uuid (shouldn't happen for ETL/TASK)
                if not file_data.provider_file_uuid:
                    logger.warning(
                        f"DEBUG: File {file_data.file_name} missing provider_file_uuid - including anyway"
                    )
                    filtered_files[file_path] = file_data
                    continue

                try:
                    # Check individual file history using provider_file_uuid (matches backend logic)
                    logger.info(
                        f"DEBUG: Making file history API call for {file_data.file_name}"
                    )
                    logger.info(
                        f"DEBUG: API params - workflow_id='{self.workflow_id}', provider_file_uuid='{file_data.provider_file_uuid}', file_path='{file_path}', organization_id='{self.organization_id}'"
                    )

                    history_response = self.api_client.get_file_history(
                        workflow_id=self.workflow_id,
                        provider_file_uuid=file_data.provider_file_uuid,
                        file_path=file_path,
                        organization_id=self.organization_id,
                    )

                    logger.info(
                        f"DEBUG: File history API response for {file_data.file_name}: {history_response}"
                    )

                    # If no history or incomplete history, file is new (matches backend source.py:628-630)
                    if not history_response or "file_history" not in history_response:
                        logger.info(
                            f"DEBUG: No file history found for {file_data.file_name} - including in batch"
                        )
                        logger.info(
                            f"DEBUG: Reason - response is empty: {not history_response}, missing file_history key: {'file_history' not in (history_response or {})}"
                        )
                        filtered_files[file_path] = file_data
                        continue

                    file_history = history_response["file_history"]
                    logger.info(
                        f"DEBUG: File history data for {file_data.file_name}: {file_history}"
                    )

                    if not file_history or not file_history.get("is_completed", False):
                        is_completed_val = (
                            file_history.get("is_completed", False)
                            if file_history
                            else "N/A"
                        )
                        status_val = (
                            file_history.get("status", "N/A") if file_history else "N/A"
                        )
                        logger.info(
                            f"DEBUG: File history incomplete for {file_data.file_name} - including in batch"
                        )
                        logger.info(
                            f"DEBUG: Details - file_history exists: {bool(file_history)}, is_completed: {is_completed_val}, status: {status_val}"
                        )
                        filtered_files[file_path] = file_data
                        continue

                    # Compare file paths (matches backend source.py:635-637)
                    history_file_path = file_history.get("file_path")
                    logger.info(
                        f"DEBUG: Path comparison for {file_data.file_name}: current='{file_path}', history='{history_file_path}'"
                    )
                    if history_file_path and history_file_path != file_path:
                        # Same provider_file_uuid but different path - treat as new file
                        logger.info(
                            f"DEBUG: Different paths detected for {file_data.file_name} - including in batch"
                        )
                        logger.info(
                            f"DEBUG: Path mismatch details - paths are different: {history_file_path != file_path}"
                        )
                        filtered_files[file_path] = file_data
                        continue

                    # File has been processed with same provider_file_uuid and path - skip
                    logger.info(
                        f"DEBUG: *** FILTERING OUT PROCESSED FILE *** {file_data.file_name} "
                        f"(provider_file_uuid: {file_data.provider_file_uuid[:16]}..., status: {file_history.get('status', 'unknown')})"
                    )
                    logger.info(
                        f"DEBUG: File {file_data.file_name} will NOT be included in batch - already processed"
                    )
                    # NOTE: Do not add to filtered_files - this excludes the file from processing

                except Exception as history_error:
                    logger.warning(
                        f"DEBUG: File history check failed for {file_data.file_name}: {history_error} - including file anyway"
                    )
                    filtered_files[file_path] = file_data

            logger.info(
                f"DEBUG: File history filtering complete - {len(filtered_files)}/{len(files)} files remain after filtering"
            )
            logger.info(
                f"DEBUG: Files remaining: {[f.file_name for f in filtered_files.values()]}"
            )
            logger.info(
                f"DEBUG: Files filtered out: {[f.file_name for f in files.values() if f not in filtered_files.values()]}"
            )

            return filtered_files

        except Exception as e:
            logger.error(f"Failed to apply file history filtering: {e}")
            # On error, return all files to avoid skipping incorrectly
            return files

    def _get_fs_connector(
        self, settings: dict[str, Any], connector_id: str
    ) -> UnstractFileSystem:
        """Get filesystem connector instance.

        Args:
            settings: Connector settings
            connector_id: Connector ID

        Returns:
            UnstractFileSystem: Connector instance
        """
        return get_connector_instance(connector_id, settings)

    def get_file_content_hash(self, source_fs: UnstractFileSystem, file_path: str) -> str:
        """Get file content hash matching backend source.py:745.

        Args:
            source_fs: Filesystem connector
            file_path: Path to file

        Returns:
            str: SHA256 hash of file content
        """
        return FileOperations.compute_file_content_hash_from_fsspec(source_fs, file_path)
