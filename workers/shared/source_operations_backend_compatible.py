"""Source Operations Backend Compatible Implementation

This module implements the exact same file listing and processing logic
as the Django backend source.py, enabling workers to handle file listing
and deduplication identically to the backend.
"""

import hashlib
import os
from dataclasses import dataclass
from typing import Any

from unstract.connectors.constants import Common

# Import connector infrastructure (matching backend)
from unstract.connectors.filesystems import connectors

# Import shared data models
from unstract.core.data_models import FileHashData

from .api_client import InternalAPIClient
from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


@dataclass
class FileListingResult:
    """Result of file listing operation matching backend structure."""

    files: dict[str, FileHashData]
    total_count: int
    connection_type: str
    is_api: bool
    used_file_history: bool


class WorkerSourceConnector:
    """Worker-compatible source connector implementation.

    This implements the exact same logic as backend SourceConnector
    but uses API calls instead of Django ORM.
    """

    READ_CHUNK_SIZE = 4194304  # Same as backend: 4MB chunks

    def __init__(
        self,
        api_client: InternalAPIClient,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        use_file_history: bool = False,
    ):
        self.api_client = api_client
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.use_file_history = use_file_history
        self.logger = logger

        # Get workflow endpoint configuration via API (matching backend)
        self.endpoint_config = self._get_endpoint_configuration()

    def _get_endpoint_configuration(self) -> dict[str, Any]:
        """Get workflow endpoint configuration via API (replacing Django ORM)."""
        try:
            # Get workflow endpoints and extract source endpoint configuration
            endpoints_response = self.api_client.get_workflow_endpoints(self.workflow_id)
            endpoints = endpoints_response.get("endpoints", [])

            # Find the SOURCE endpoint configuration
            source_endpoint = None
            for endpoint in endpoints:
                if endpoint.get("endpoint_type") == "SOURCE":
                    source_endpoint = endpoint
                    break

            if not source_endpoint:
                raise ValueError(
                    f"No SOURCE endpoint found for workflow {self.workflow_id}"
                )

            endpoint_config = source_endpoint

            if not endpoint_config:
                raise ValueError(
                    f"No endpoint configuration found for workflow {self.workflow_id}"
                )

            logger.info(
                f"Retrieved endpoint configuration for workflow {self.workflow_id}: {endpoint_config.get('connection_type')}"
            )
            return endpoint_config

        except Exception as e:
            logger.error(
                f"Failed to get endpoint configuration for workflow {self.workflow_id}: {e}"
            )
            raise

    def list_files_from_source(
        self, existing_file_hashes: dict[str, FileHashData] | None = None
    ) -> FileListingResult:
        """List files from source connector.

        This implements the exact same logic as backend SourceConnector.list_files_from_source()
        with API vs ETL/TASK differentiation.

        Args:
            existing_file_hashes: Pre-existing file hashes (for API workflows)

        Returns:
            FileListingResult with files and metadata
        """
        connection_type = self.endpoint_config.get("connection_type")
        is_api = connection_type == "API"

        logger.info(
            f"Listing files for workflow {self.workflow_id} with connection_type: {connection_type}"
        )

        if is_api:
            # API workflow: Use provided file hashes (matches backend API logic)
            files, count = self._list_files_from_api_storage(existing_file_hashes or {})
        else:
            # ETL/TASK workflow: List from file system connector (matches backend FILESYSTEM logic)
            files, count = self._list_files_from_file_connector()

        # Add file numbers (matching backend logic)
        for index, file_hash in enumerate(files.values(), start=1):
            file_hash.file_number = index

        logger.info(f"Listed {count} files for {connection_type} workflow")

        return FileListingResult(
            files=files,
            total_count=count,
            connection_type=connection_type,
            is_api=is_api,
            used_file_history=self.use_file_history,
        )

    def _list_files_from_api_storage(
        self, existing_file_hashes: dict[str, FileHashData]
    ) -> tuple[dict[str, FileHashData], int]:
        """List files from API storage (matching backend logic).

        For API workflows, files are already uploaded and we just process them.
        """
        logger.info(f"Listing {len(existing_file_hashes)} files from API storage")

        # Apply file history filtering if enabled (matching backend)
        if self.use_file_history:
            filtered_files = self._apply_file_history_filtering(existing_file_hashes)
            logger.info(
                f"File history filtering: {len(filtered_files)}/{len(existing_file_hashes)} files after deduplication"
            )
            return filtered_files, len(filtered_files)

        return existing_file_hashes, len(existing_file_hashes)

    def _list_files_from_file_connector(self) -> tuple[dict[str, FileHashData], int]:
        """List files from file system connector (matching backend logic).

        This implements the exact same logic as backend SourceConnector.list_files_from_file_connector()
        """
        logger.info("Listing files from file system connector")

        # Get connector configuration via API (now with proper connector_instance data)
        connector_instance = self.endpoint_config.get("connector_instance", {})
        connector_metadata = connector_instance.get("connector_metadata", {})
        connector_id = connector_instance.get("connector_id")

        if not connector_id:
            raise ValueError("No connector ID found in endpoint configuration")

        # Get source configuration (matching backend)
        source_configuration = self.endpoint_config.get("configuration", {})

        # Extract configuration parameters (matching backend SourceKey constants)
        # Use exact same keys as backend SourceKey class
        required_patterns = source_configuration.get(
            "fileExtensions", []
        )  # SourceKey.FILE_EXTENSIONS
        recursive = bool(
            source_configuration.get("processSubDirectories", False)
        )  # SourceKey.PROCESS_SUB_DIRECTORIES
        limit = int(source_configuration.get("maxFiles", 1000))  # SourceKey.MAX_FILES
        root_dir_path = connector_metadata.get("path", "")
        folders_to_process = source_configuration.get(
            "folders", ["/"]
        )  # SourceKey.FOLDERS

        # Process from root if folder list is empty
        if not folders_to_process:
            folders_to_process = ["/"]

        logger.info(
            f"File listing parameters: patterns={required_patterns}, recursive={recursive}, limit={limit}, folders={folders_to_process}"
        )
        logger.info(f"Connector metadata path (root_dir_path): '{root_dir_path}'")

        # Get file system using connector registry (matching backend)
        try:
            # Find matching connector in registry
            matching_connector_key = None
            for key in connectors.keys():
                if key.startswith(f"{connector_id.split('|')[0]}|"):
                    matching_connector_key = key
                    break

            if not matching_connector_key:
                raise ValueError(f"Connector not found in registry: {connector_id}")

            connector_class = connectors[matching_connector_key][Common.METADATA][
                Common.CONNECTOR
            ]
            source_connector = connector_class(connector_metadata)

            # The source_connector IS the UnstractFileSystem instance
            # source_fs is the underlying fsspec filesystem
            source_fs = source_connector.get_fsspec_fs()

            logger.info(
                f"Successfully created file system connector: {matching_connector_key}"
            )

        except Exception as e:
            logger.error(f"Failed to create file system connector: {e}")
            raise

        # List files using backend-compatible approach (matching source.py logic)
        found_files = {}
        total_processed = 0
        unique_file_paths = set()

        try:
            for folder in folders_to_process:
                # Use connector's get_connector_root_dir method (matching backend logic)
                try:
                    # Call get_connector_root_dir exactly like backend does
                    folder_path = source_connector.get_connector_root_dir(
                        input_dir=folder, root_path=root_dir_path
                    )
                    logger.info(
                        f"Resolved folder path via get_connector_root_dir: {folder_path} (from input: {folder}, root: {root_dir_path})"
                    )
                except Exception as e:
                    # Some connectors may not have this method, use default logic
                    logger.debug(f"Using default path resolution: {e}")
                    if root_dir_path:
                        # If we have a root path, join it with the folder
                        folder_path = os.path.join(root_dir_path, folder.lstrip("/"))
                    else:
                        # No root path (common for cloud storage), use folder as-is
                        folder_path = folder.strip("/")
                        if folder_path and not folder_path.endswith("/"):
                            folder_path += "/"
                    logger.info(f"Default path resolution result: {folder_path}")

                # Additional logging to debug GCS path issues
                logger.info(f"Connector type: {connector_id}")
                logger.info(f"Connector metadata: {connector_metadata}")
                logger.info(f"Final folder_path to check: '{folder_path}'")

                # Special handling for GCS - check if the folder path contains bucket name
                if "google_cloud_storage" in matching_connector_key:
                    logger.info(
                        f"GCS connector detected - analyzing path format for: '{folder_path}'"
                    )
                    # For GCS, the folder might be passed as "bucket-name/folder-path"
                    # But fsspec GCS expects just "folder-path" without bucket prefix
                    # The bucket name should be configured in the credentials

                    paths_to_try = []

                    # Always try the original path first
                    paths_to_try.append(folder_path)

                    if "/" in folder_path:
                        # Split into potential bucket/folder parts
                        parts = folder_path.split("/", 1)
                        if len(parts) == 2:
                            bucket_name, folder_in_bucket = parts
                            logger.info(
                                f"GCS path analysis: potential_bucket='{bucket_name}', folder_in_bucket='{folder_in_bucket}'"
                            )

                            # Try just the folder part (most likely correct for GCS)
                            paths_to_try.append(folder_in_bucket)

                            # Try folder with trailing slash
                            if not folder_in_bucket.endswith("/"):
                                paths_to_try.append(folder_in_bucket + "/")

                            # Try folder without trailing slash
                            if folder_in_bucket.endswith("/"):
                                paths_to_try.append(folder_in_bucket.rstrip("/"))

                    # Try root paths as fallback
                    paths_to_try.extend(["", "/"])

                    # Remove duplicates while preserving order
                    gcs_paths_to_try = []
                    seen = set()
                    for path in paths_to_try:
                        if path not in seen:
                            gcs_paths_to_try.append(path)
                            seen.add(path)

                    logger.info(f"GCS paths to try in order: {gcs_paths_to_try}")
                else:
                    gcs_paths_to_try = [folder_path]

                # Validate directory exists (with special handling for GCS)
                valid_folder_path = None
                validation_errors = []

                for i, path_to_try in enumerate(gcs_paths_to_try, 1):
                    logger.info(
                        f"Attempt {i}/{len(gcs_paths_to_try)}: Checking directory existence for path: '{path_to_try}'"
                    )
                    try:
                        if source_fs.isdir(path_to_try):
                            logger.info(
                                f"✅ SUCCESS: Directory found at path: '{path_to_try}'"
                            )
                            valid_folder_path = path_to_try
                            break
                        else:
                            logger.debug(
                                f"❌ Directory not found at path: '{path_to_try}'"
                            )
                            # Try without trailing slash for some connectors
                            path_no_slash = path_to_try.rstrip("/")
                            if path_no_slash != path_to_try:
                                logger.debug(
                                    f"   Trying without trailing slash: '{path_no_slash}'"
                                )
                                if source_fs.isdir(path_no_slash):
                                    logger.info(
                                        f"✅ SUCCESS: Directory found without trailing slash: '{path_no_slash}'"
                                    )
                                    valid_folder_path = path_no_slash
                                    break
                                else:
                                    logger.debug(
                                        f"   ❌ Directory not found without trailing slash: '{path_no_slash}'"
                                    )

                            validation_errors.append(f"Path '{path_to_try}' not found")
                    except Exception as e:
                        error_msg = f"Error validating path '{path_to_try}': {e}"
                        logger.warning(error_msg)
                        validation_errors.append(error_msg)
                        continue

                if not valid_folder_path:
                    logger.error(
                        f"❌ DIRECTORY NOT FOUND: No valid directory found after trying {len(gcs_paths_to_try)} different paths"
                    )
                    logger.error(f"   Original folder: '{folder}'")
                    logger.error(f"   Root dir path: '{root_dir_path}'")
                    logger.error(f"   Connector: {matching_connector_key}")
                    logger.error(f"   Attempted paths: {gcs_paths_to_try}")
                    logger.error(f"   Validation errors: {validation_errors}")

                    # For GCS specifically, provide troubleshooting hints
                    if "google_cloud_storage" in matching_connector_key:
                        logger.error("💡 GCS TROUBLESHOOTING HINTS:")
                        logger.error(
                            "   1. Check if bucket name is correctly configured in connector credentials (not in path)"
                        )
                        logger.error("   2. Verify bucket permissions and authentication")
                        logger.error("   3. Ensure the folder exists in the GCS bucket")
                        logger.error(
                            "   4. Try accessing the bucket root first to test connectivity"
                        )

                    continue

                # Use the valid path for processing
                folder_path = valid_folder_path

                logger.info(f"Processing directory: {folder_path}")

                # Use backend pattern: walk through directories and use listdir() for each
                # Match backend SourceConstant.MAX_RECURSIVE_DEPTH = 10
                max_depth = 10 if recursive else 1

                try:
                    # Use fsspec walk to get directories (matching backend source.py:352)
                    walk_results = list(source_fs.walk(folder_path, maxdepth=max_depth))
                    logger.info(
                        f"Walk found {len(walk_results)} directories to process in {folder_path}"
                    )

                    for root, dirs, _ in walk_results:
                        if total_processed >= limit:
                            logger.info(f"Reached file limit of {limit}")
                            break

                        logger.debug(
                            f"Processing directory: {root} (contains {len(dirs)} subdirs)"
                        )

                        try:
                            # Get metadata list for all items in directory (matching backend source.py:354)
                            fs_metadata_list = source_fs.listdir(root)
                            logger.debug(
                                f"Listed {len(fs_metadata_list)} items in {root}"
                            )

                            # Process each item using backend-compatible logic
                            total_processed = self._process_directory_items(
                                fs_metadata_list=fs_metadata_list,
                                count=total_processed,
                                limit=limit,
                                unique_file_paths=unique_file_paths,
                                matched_files=found_files,
                                patterns=required_patterns,
                                source_fs=source_fs,
                                source_connector=source_connector,
                                connector_metadata=connector_metadata,
                                matching_connector_key=matching_connector_key,
                                dirs=dirs,
                            )

                        except Exception as listdir_error:
                            logger.warning(
                                f"Failed to list directory {root}: {listdir_error}"
                            )
                            continue

                except Exception as walk_error:
                    logger.warning(
                        f"Failed to walk directory {folder_path}: {walk_error}"
                    )
                    logger.debug(f"Walk error details: {walk_error}", exc_info=True)
                    continue

            logger.info(
                f"Successfully listed {len(found_files)} files from file system connector"
            )

            # Apply file history filtering if enabled
            if self.use_file_history and found_files:
                filtered_files = self._apply_file_history_filtering(found_files)
                logger.info(
                    f"File history filtering: {len(filtered_files)}/{len(found_files)} files after deduplication"
                )
                return filtered_files, len(filtered_files)

            return found_files, len(found_files)

        except Exception as e:
            logger.error(f"Failed to list files from file system: {e}")
            raise

    def _compute_file_content_hash(self, source_fs, file_path: str) -> str:
        """Compute file content hash (matching backend logic).

        This uses the same chunked reading approach as backend.
        """
        file_content_hash = hashlib.sha256()

        try:
            with source_fs.open(file_path, "rb") as remote_file:
                while chunk := remote_file.read(self.READ_CHUNK_SIZE):
                    file_content_hash.update(chunk)

            return file_content_hash.hexdigest()

        except Exception as e:
            logger.warning(f"Failed to compute content hash for {file_path}: {e}")
            # Return a fallback hash based on file path and current time
            import time

            fallback_content = f"{file_path}_{int(time.time())}"
            return hashlib.md5(fallback_content.encode()).hexdigest()

    def _detect_mime_type(self, file_path: str) -> str:
        """Detect MIME type from file extension (simple fallback)."""
        ext = os.path.splitext(file_path)[1].lower()

        mime_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
        }

        return mime_map.get(ext, "application/octet-stream")

    def _process_directory_items(
        self,
        fs_metadata_list: list,
        count: int,
        limit: int,
        unique_file_paths: set,
        matched_files: dict,
        patterns: list,
        source_fs,
        source_connector,
        connector_metadata: dict,
        matching_connector_key: str,
        dirs: list,
    ) -> int:
        """Process directory items matching backend _process_file_fs_directory logic.

        This method filters out directories and processes only files.
        """
        for fs_metadata in fs_metadata_list:
            if count >= limit:
                logger.info(f"Maximum limit of {limit} files reached")
                break

            file_path = fs_metadata.get("name")
            file_size = fs_metadata.get("size", 0)

            if not file_path:
                continue

            logger.debug(
                f"Processing metadata item: path={file_path}, size={file_size}, type={fs_metadata.get('type')}"
            )

            # Check if this is a directory (matching backend _is_directory logic)
            if self._is_directory(source_fs, file_path, fs_metadata, dirs):
                logger.debug(f"Skipping directory: {file_path}")
                continue

            # Create file hash data (matching backend _create_file_hash logic)
            try:
                file_hash_data = self._create_file_hash_from_metadata(
                    file_path=file_path,
                    source_fs=source_fs,
                    source_connector=source_connector,
                    file_size=file_size,
                    fs_metadata=fs_metadata,
                    connector_metadata=connector_metadata,
                    matching_connector_key=matching_connector_key,
                )

                # Check file patterns (matching backend _should_skip_file logic)
                if self._should_skip_file(file_hash_data, patterns):
                    logger.debug(f"Skipping file due to pattern mismatch: {file_path}")
                    continue

                # Check for duplicates (matching backend _is_duplicate logic)
                if self._is_duplicate(file_hash_data, unique_file_paths):
                    logger.info(f"Skipping duplicate file: {file_path}")
                    continue

                # Update unique file paths tracking
                self._update_unique_file_paths(file_hash_data, unique_file_paths)

                # Add to matched files
                matched_files[file_path] = file_hash_data
                count += 1

                logger.debug(f"Added file: {file_path} (size: {file_size})")

            except Exception as file_error:
                logger.warning(f"Failed to process file {file_path}: {file_error}")
                continue

        return count

    def _is_directory(
        self, source_fs, file_path: str, metadata: dict, dirs: list
    ) -> bool:
        """Check if the given path is a directory (matching backend logic).

        Uses metadata-based detection first, with fallbacks to other methods.
        """
        try:
            # Check using connector's metadata-based method if available
            if hasattr(source_fs, "is_dir_by_metadata"):
                try:
                    if source_fs.is_dir_by_metadata(metadata):
                        logger.debug(f"Directory identified via metadata: {file_path}")
                        return True
                except (NotImplementedError, AttributeError):
                    pass

            # Fallback: check if path ends with "/" (common directory indicator)
            if file_path.endswith("/"):
                logger.debug(f"Directory identified by path suffix: {file_path}")
                return True

            # Fallback: check if file_path is in dirs list from walk()
            if os.path.basename(file_path) in dirs:
                logger.debug(f"Directory identified from dirs list: {file_path}")
                return True

            # Fallback: check using fsspec isdir() (may not work for all connectors)
            try:
                if source_fs.isdir(file_path):
                    logger.debug(f"Directory identified via isdir(): {file_path}")
                    return True
            except Exception:
                pass

            # Check metadata type field if available
            file_type = metadata.get("type", "").lower()
            if file_type in ["directory", "dir", "folder"]:
                logger.debug(f"Directory identified by type field: {file_path}")
                return True

            # If size is explicitly 0 and we can't determine otherwise, might be directory
            # But be cautious as empty files also have size 0
            file_size = metadata.get("size", -1)
            if (
                file_size == 0 and file_path.count(".") == 0
            ):  # No extension often means directory
                logger.debug(f"Potential directory (no extension, size 0): {file_path}")
                return True

            return False

        except Exception as e:
            logger.debug(f"Error checking if {file_path} is directory: {e}")
            # When in doubt, assume it's a file and let file processing handle any errors
            return False

    def _create_file_hash_from_metadata(
        self,
        file_path: str,
        source_fs,
        source_connector,
        file_size: int,
        fs_metadata: dict,
        connector_metadata: dict,
        matching_connector_key: str,
    ) -> FileHashData:
        """Create FileHashData from file metadata (matching backend logic)."""
        # Generate file hash from content (matching backend)
        file_hash = self._compute_file_content_hash(source_fs, file_path)

        # Generate provider_file_uuid (matching backend source.py:707-709)
        try:
            provider_file_uuid = source_connector.get_file_system_uuid(
                file_path=file_path, metadata=fs_metadata
            )
        except Exception as uuid_error:
            logger.debug(
                f"Failed to generate provider UUID for {file_path}: {uuid_error}"
            )
            provider_file_uuid = None

        # Create FileHashData (matching backend FileHash structure)
        return FileHashData(
            file_name=os.path.basename(file_path),
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            mime_type=self._detect_mime_type(file_path),
            provider_file_uuid=provider_file_uuid,
            fs_metadata={
                "last_modified": str(fs_metadata.get("mtime", ""))
                if fs_metadata.get("mtime")
                else None,
                "file_type": "file",
                "connector_id": matching_connector_key,
                "size": file_size,
                "connector_metadata": connector_metadata,
                "fs_metadata": fs_metadata,
            },
            source_connection_type=matching_connector_key,
            file_destination="destination",
            is_executed=False,
            file_number=None,  # Will be set later
            connector_metadata=connector_metadata,
            connector_id=matching_connector_key,
        )

    def _should_skip_file(self, file_hash_data: FileHashData, patterns: list) -> bool:
        """Check if file should be skipped based on patterns (matching backend logic)."""
        if not patterns:
            return False  # No patterns means accept all files

        file_name = file_hash_data.file_name
        file_ext = os.path.splitext(file_name)[1].lower()

        # Check if file extension matches any of the required patterns
        for pattern in patterns:
            if file_ext.endswith(pattern.lower()):
                return False  # File matches pattern, don't skip

        return True  # File doesn't match any pattern, skip it

    def _is_duplicate(self, file_hash_data: FileHashData, unique_file_paths: set) -> bool:
        """Check if file is duplicate (matching backend logic)."""
        file_path = file_hash_data.file_path
        if file_path in unique_file_paths:
            return True
        return False

    def _update_unique_file_paths(
        self, file_hash_data: FileHashData, unique_file_paths: set
    ):
        """Update unique file paths tracking (matching backend logic)."""
        unique_file_paths.add(file_hash_data.file_path)

    def _apply_file_history_filtering(
        self, files: dict[str, FileHashData]
    ) -> dict[str, FileHashData]:
        """Apply file history filtering (matching backend logic).

        This removes files that have already been processed successfully.
        """
        if not self.use_file_history:
            return files

        logger.info(f"Applying file history filtering to {len(files)} files")

        filtered_files = {}

        try:
            # Get file history for all files via API
            file_hashes = [
                file_data.file_hash for file_data in files.values() if file_data.file_hash
            ]

            if not file_hashes:
                logger.warning("No file hashes available for history filtering")
                return files

            # Batch check file history via API
            history_response = self.api_client.check_file_history_batch(
                workflow_id=self.workflow_id,
                file_hashes=file_hashes,
                organization_id=self.organization_id,
            )

            processed_hashes = set(history_response.get("processed_file_hashes", []))

            # Filter out already processed files
            for file_path, file_data in files.items():
                if file_data.file_hash not in processed_hashes:
                    filtered_files[file_path] = file_data
                else:
                    logger.info(
                        f"Skipping already processed file: {file_data.file_name} (hash: {file_data.file_hash[:16]}...)"
                    )

            logger.info(
                f"File history filtering complete: {len(filtered_files)}/{len(files)} files remaining"
            )

        except Exception as e:
            logger.warning(f"File history filtering failed, processing all files: {e}")
            return files

        return filtered_files


class WorkerFileHistoryManager:
    """Worker-compatible file history manager.

    This handles creating FileHistory entries after successful processing
    to enable deduplication for future runs.
    """

    def __init__(self, api_client: InternalAPIClient):
        self.api_client = api_client
        self.logger = logger

    def create_file_history_entry(
        self,
        workflow_id: str,
        file_data: FileHashData,
        execution_result: dict[str, Any],
        organization_id: str,
    ) -> bool:
        """Create file history entry after successful processing.

        This matches backend FileHistoryHelper.create_file_history() logic.
        For FILESYSTEM workflows, file_hash is used as the unique identifier.
        """
        try:
            if not file_data.file_hash:
                logger.warning(
                    f"Cannot create file history entry for {file_data.file_name}: missing file hash"
                )
                return False

            # Determine status based on execution result
            if execution_result.get("error"):
                status = "ERROR"
            else:
                status = "COMPLETED"

            result = execution_result.get("result", "")
            error = execution_result.get("error", "")

            # For FILESYSTEM workflows, provider_file_uuid is typically None
            # The file_hash (content hash) serves as the unique identifier
            provider_uuid = file_data.provider_file_uuid
            if provider_uuid is None:
                logger.debug(
                    f"File {file_data.file_name} has no provider_file_uuid (normal for FILESYSTEM workflows)"
                )

            # Create file history entry via API
            history_data = {
                "workflow_id": workflow_id,
                "cache_key": file_data.file_hash,  # This is the unique identifier for deduplication
                "provider_file_uuid": provider_uuid,  # Can be None for FILESYSTEM
                "file_path": file_data.file_path,
                "file_name": file_data.file_name,
                "status": status,
                "result": str(result) if result else "",
                "error": str(error) if error else "",
                "metadata": execution_result.get("metadata", {}),
                "organization_id": organization_id,
                "source_connection_type": file_data.source_connection_type,  # Required by backend FileHash model
            }

            response = self.api_client.create_file_history_entry(history_data)

            if response.get("created"):
                logger.info(
                    f"Created file history entry for {file_data.file_name} (status: {status})"
                )
                return True
            else:
                logger.info(
                    f"File history entry already exists for {file_data.file_name}"
                )
                return True

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
        """Create file history entries for a batch of processed files."""
        results = {}

        for execution_result in execution_results:
            file_data = execution_result.get("file_data")
            if file_data and isinstance(file_data, (FileHashData, dict)):
                if isinstance(file_data, dict):
                    file_data = FileHashData.from_dict(file_data)

                file_name = file_data.file_name
                success = self.create_file_history_entry(
                    workflow_id=workflow_id,
                    file_data=file_data,
                    execution_result=execution_result,
                    organization_id=organization_id,
                )
                results[file_name] = success

        successful_entries = sum(1 for success in results.values() if success)
        logger.info(
            f"Created file history entries: {successful_entries}/{len(results)} successful"
        )

        return results
