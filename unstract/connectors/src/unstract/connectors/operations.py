"""Connector Operations for Unstract Platform

This module provides connector operations that can be used by both
Django backend and Celery workers.

Uses the internal connector registry and follows proper Unstract package architecture.

Shared between:
- backend/workflow_manager/endpoint_v2/source.py (for API endpoints)
- backend/workflow_manager/endpoint_v2/destination.py (for API endpoints)
- workers/shared/source_operations.py (for worker-native operations)
- workers/shared/connector_service.py (for worker-native operations)
"""

import logging
from typing import Any

# Import internal connector components (no try/catch needed - proper dependencies)
from unstract.connectors.constants import Common
from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.filesystems import connectors as fs_connectors
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

# Import from unstract-core package for data models and file operations
from unstract.core.data_models import (
    DirectoryValidationData,
    FileHashData,
    SourceFileListingRequest,
    SourceFileListingResponse,
)
from unstract.core.file_operations import FileOperations

logger = logging.getLogger(__name__)


class ConnectorOperations:
    """Common connector operations shared between backend and workers with strict error handling"""

    @staticmethod
    def validate_source_config(source_config: dict[str, Any]) -> dict[str, Any]:
        """Validate source configuration before attempting connector operations.

        This replicates backend validation logic from SourceConnector.validate()

        Args:
            source_config: Source configuration dictionary

        Returns:
            Dictionary with validation results: {'is_valid': bool, 'errors': list}
        """
        errors = []

        # Check for required fields
        if not source_config:
            errors.append("Source configuration is empty")
            return {"is_valid": False, "errors": errors}

        # Check for connector_id or connection_type
        connector_id = source_config.get("connector_id") or source_config.get(
            "connection_type"
        )
        if not connector_id:
            errors.append(
                "Missing connector_id or connection_type in source configuration"
            )

        # Check if connector registry is loaded (should always be available with proper dependencies)
        if not fs_connectors:
            errors.append("Filesystem connector registry not initialized")
            return {"is_valid": False, "errors": errors}

        # Check if connector type is supported
        if connector_id and connector_id not in fs_connectors:
            available_connectors = list(fs_connectors.keys())
            errors.append(
                f"Unsupported connector type '{connector_id}'. Available: {available_connectors}"
            )

        # Check for required settings
        settings = source_config.get("settings", {})
        if not settings and connector_id != "API":
            errors.append("Missing connector settings")

        # Connector-specific validation
        if connector_id and not errors:
            try:
                validation_errors = ConnectorOperations._validate_connector_settings(
                    connector_id, settings
                )
                errors.extend(validation_errors)
            except Exception as e:
                errors.append(f"Connector validation failed: {str(e)}")

        return {"is_valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def _validate_connector_settings(
        connector_id: str, settings: dict[str, Any]
    ) -> list[str]:
        """Validate connector-specific settings.

        Args:
            connector_id: Connector ID
            settings: Connector settings

        Returns:
            List of validation error messages
        """
        errors = []

        # Common validation for filesystem connectors
        if connector_id in ["LOCAL_STORAGE", "MINIO", "S3", "GOOGLE_CLOUD_STORAGE"]:
            # Path validation
            if "path" not in settings or not settings["path"]:
                errors.append(f"Missing required 'path' setting for {connector_id}")

        # Minio/S3 specific validation
        if connector_id in ["MINIO", "S3"]:
            required_fields = (
                ["endpoint_url", "key", "secret"]
                if connector_id == "MINIO"
                else ["key", "secret"]
            )
            for field in required_fields:
                if field not in settings or not settings[field]:
                    errors.append(
                        f"Missing required '{field}' setting for {connector_id}"
                    )

        # Google Cloud Storage validation
        if connector_id == "GOOGLE_CLOUD_STORAGE":
            if (
                "service_account_data" not in settings
                or not settings["service_account_data"]
            ):
                errors.append(
                    "Missing required 'service_account_data' setting for Google Cloud Storage"
                )

        # Database connector validation
        if db_connectors and connector_id in db_connectors:
            required_db_fields = ["host", "database", "username", "password"]
            for field in required_db_fields:
                if field not in settings or not settings[field]:
                    errors.append(
                        f"Missing required '{field}' setting for database connector {connector_id}"
                    )

        return errors

    @staticmethod
    def test_connector_connection(
        connector_id: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Test connection to connector before attempting operations.

        Args:
            connector_id: Connector ID
            settings: Connector settings

        Returns:
            Dictionary with connection test results: {'is_connected': bool, 'error': str}
        """
        try:
            # Get connector instance
            connector = ConnectorOperations.get_fs_connector(connector_id, settings)

            # Test basic connectivity by getting fsspec filesystem
            fs = connector.get_fsspec_fs()

            # For filesystem connectors, try to check if root path exists
            test_path = settings.get("path", "/")
            try:
                fs.exists(test_path)
                return {"is_connected": True, "error": None}
            except Exception as path_error:
                return {
                    "is_connected": False,
                    "error": f"Cannot access path '{test_path}': {str(path_error)}",
                }

        except Exception as e:
            return {"is_connected": False, "error": str(e)}

    @staticmethod
    def get_fs_connector(
        connector_id: str, settings: dict[str, Any]
    ) -> "UnstractFileSystem":
        """Get filesystem connector instance using exact backend BaseConnector logic.

        This replicates backend/workflow_manager/endpoint_v2/base_connector.py:get_fs_connector()

        Args:
            connector_id: Connector ID from the registry
            settings: Connector-specific settings

        Returns:
            UnstractFileSystem instance

        Raises:
            ImportError: If connector registries not available (critical error)
            ValueError: If connector_id is not supported
        """
        if not fs_connectors:
            raise RuntimeError("Filesystem connectors registry not initialized")

        if connector_id not in fs_connectors:
            available_ids = list(fs_connectors.keys())
            raise ValueError(
                f"Connector '{connector_id}' is not supported. "
                f"Available connectors: {available_ids}"
            )

        if not Common:
            raise RuntimeError("Common connector constants not initialized")

        # Use exact same pattern as backend BaseConnector
        connector_class = fs_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        return connector_class(settings)

    @staticmethod
    def list_files_from_source(
        connector_id: str,
        settings: dict[str, Any],
        organization_id: str,
        filters: dict[str, Any] | None = None,
    ) -> list[FileHashData]:
        """Shared source file listing logic with strict error handling.

        No graceful fallbacks - all connector errors are raised immediately.
        This matches backend behavior from endpoint_v2/source.py.

        Args:
            connector_id: Connector ID from registry (not connection_type)
            settings: Connector-specific settings
            organization_id: Organization ID for context
            filters: Optional filters for file listing

        Returns:
            List of FileHashData objects representing source files

        Raises:
            ImportError: If connector registry not available (critical error)
            ValueError: If connector_id is not supported or settings invalid
            ConnectionError: If connector cannot connect to source or list files
            FileNotFoundError: If specified path does not exist
            NotADirectoryError: If specified path is not a directory
        """
        filters = filters or {}

        # Validate inputs before attempting connection - fail fast
        if not connector_id:
            raise ValueError("Connector ID is required")

        if not settings:
            raise ValueError(f"Connector settings are required for {connector_id}")

        # Get connector using exact same pattern as backend - let all exceptions propagate
        source_connector = ConnectorOperations.get_fs_connector(
            connector_id=connector_id, settings=settings
        )

        logger.info(
            f"Created filesystem connector {connector_id} for org {organization_id}"
        )

        # Test connectivity before proceeding - critical for fail-fast behavior
        try:
            source_fs_fsspec = source_connector.get_fsspec_fs()
        except Exception as e:
            error_msg = f"Failed to create fsspec filesystem for {connector_id}: {str(e)}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        # Apply filters and list files - Follow backend source.py pattern
        folders_to_process = filters.get("folders_to_process", [filters.get("path", "/")])
        max_files = filters.get("max_files", 1000)  # Match backend default
        recursive = filters.get("recursive", True)
        file_extensions = filters.get("allowed_extensions", [])

        # Validate folders exist before processing - matching backend behavior
        valid_directories = []
        for input_directory in folders_to_process:
            try:
                if not source_fs_fsspec.exists(input_directory):
                    raise FileNotFoundError(
                        f"Path '{input_directory}' does not exist in {connector_id}"
                    )

                if not source_fs_fsspec.isdir(input_directory):
                    raise NotADirectoryError(
                        f"Path '{input_directory}' is not a directory in {connector_id}"
                    )

                valid_directories.append(input_directory)
                logger.debug(f"Validated directory: {input_directory}")

            except Exception as e:
                if isinstance(e, (FileNotFoundError, NotADirectoryError)):
                    logger.error(
                        f"Invalid directory '{input_directory}' for {connector_id}: {str(e)}"
                    )
                    raise ConnectionError(
                        f"Invalid input directory '{input_directory}': {str(e)}"
                    ) from e
                else:
                    logger.error(
                        f"Failed to validate directory '{input_directory}' for {connector_id}: {str(e)}"
                    )
                    raise ConnectionError(
                        f"Path validation failed for '{input_directory}': {str(e)}"
                    ) from e

        # List files using fs_fsspec.walk() - matching backend pattern
        files_only = []
        total_files_processed = 0

        try:
            for input_directory in valid_directories:
                logger.debug(f"Listing files from: {input_directory}")

                # Use walk() like backend source.py:307 instead of problematic glob()
                max_depth = 10 if recursive else 1  # Match backend MAX_RECURSIVE_DEPTH

                for root, dirs, _ in source_fs_fsspec.walk(
                    input_directory, maxdepth=max_depth
                ):
                    try:
                        # Get file metadata list like backend source.py:309
                        fs_metadata_list = source_fs_fsspec.listdir(root)
                    except Exception as e:
                        logger.warning(
                            f"Failed to list directory from path: {root}, error: {e}"
                        )
                        continue

                    # Process files in this directory
                    for fs_metadata in fs_metadata_list:
                        if total_files_processed >= max_files:
                            logger.info(
                                f"Maximum limit of '{max_files}' files to process reached"
                            )
                            break

                        file_path = fs_metadata.get("name")
                        if not file_path:
                            continue

                        # Check if it's a file (not directory)
                        try:
                            if source_fs_fsspec.isfile(file_path):
                                files_only.append(file_path)
                                total_files_processed += 1
                        except Exception as file_check_error:
                            logger.warning(
                                f"Could not check if '{file_path}' is a file: {file_check_error}"
                            )
                            continue

                    if total_files_processed >= max_files:
                        break

                if total_files_processed >= max_files:
                    break

            logger.info(
                f"Listed {len(files_only)} files from {connector_id} across {len(valid_directories)} directories"
            )

        except Exception as e:
            error_msg = f"Failed to list files from {connector_id} directories {valid_directories}: {str(e)}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        # Convert to FileHashData objects - Following backend _create_file_hash pattern
        file_hash_list = []
        for file_path in files_only:
            try:
                # Get file info using fsspec - matching backend pattern
                file_info = source_fs_fsspec.info(file_path)

                # Skip directories - defensive check
                if file_info.get("type") == "directory":
                    continue

                file_name = file_path.split("/")[-1]
                file_size = file_info.get("size", 0)

                # Apply extension filters if specified - matching backend pattern
                if file_extensions:
                    file_ext = file_name.split(".")[-1].lower()
                    if file_ext not in [
                        ext.lower().lstrip(".") for ext in file_extensions
                    ]:
                        continue

                # Create provider_file_uuid - matching backend source.py:603-604
                provider_file_uuid = (
                    file_info.get("etag") or file_info.get("uuid") or file_path
                )

                # Serialize metadata - matching backend source.py:606
                serialized_metadata = {
                    "last_modified": file_info.get("mtime"),
                    "file_type": file_info.get("type"),
                    "connector_id": connector_id,
                    "etag": file_info.get("etag"),
                    "size": file_size,
                }

                # Create FileHashData object - matching backend FileHash structure
                file_data = FileHashData(
                    file_name=file_name,
                    file_path=file_path,
                    file_size=file_size,
                    mime_type=FileOperations.detect_mime_type(file_name),
                    provider_file_uuid=provider_file_uuid,
                    source_connection_type=connector_id,
                    fs_metadata=serialized_metadata,
                    connector_metadata=settings,  # Include connector credentials/settings
                    connector_id=connector_id,  # Include full connector ID
                )

                # Validate file if filters provided - matching backend validation
                if filters.get("validate_files", True):
                    validation = FileOperations.validate_file_compatibility(
                        file_data, filters
                    )
                    if validation["is_valid"]:
                        file_hash_list.append(file_data)
                    else:
                        logger.debug(
                            f"Skipping invalid file {file_data.file_name}: {validation['errors']}"
                        )
                else:
                    file_hash_list.append(file_data)

            except Exception as e:
                logger.warning(f"Failed to process file {file_path}: {str(e)}")
                # Continue processing other files, but log individual file errors
                continue

        logger.info(
            f"Successfully processed {len(file_hash_list)} files from {connector_id}"
        )
        return file_hash_list

    @staticmethod
    def list_files_from_source_enhanced(
        request: SourceFileListingRequest,
    ) -> SourceFileListingResponse:
        """Enhanced source file listing with backend-compatible path transformation.

        This method implements the missing logic from backend source.py including:
        - Proper path transformation using get_connector_root_dir()
        - Directory validation with transformed paths
        - File pattern processing matching backend logic
        - Comprehensive error handling and validation results

        Args:
            request: Standardized file listing request with all parameters

        Returns:
            SourceFileListingResponse with files and validation results

        Raises:
            ImportError: If connector registries not available
            ValueError: If connector_id is not supported or settings invalid
            ConnectionError: If connector cannot connect or list files
        """
        import time

        start_time = time.time()

        response = SourceFileListingResponse()
        source_config = request.source_config

        logger.info(f"Enhanced file listing for connector {source_config.connector_id}")

        try:
            # Get filesystem connector using exact backend pattern
            source_connector = ConnectorOperations.get_fs_connector(
                connector_id=source_config.connector_id,
                settings=source_config.connector_metadata,
            )

            # Get fsspec filesystem for operations
            source_fs_fsspec = source_connector.get_fsspec_fs()

            # Extract configuration using backend-compatible logic
            root_dir_path = source_config.get_root_dir_path()
            folders_to_process = source_config.get_folders_to_process()

            logger.debug(f"Root directory: {root_dir_path}")
            logger.debug(f"Folders to process: {folders_to_process}")

            # Validate and transform directories - Backend source.py:194-208 logic
            valid_directories = []
            for input_directory in folders_to_process:
                try:
                    # CRITICAL: Apply path transformation like backend source.py:197-199
                    transformed_directory = source_connector.get_connector_root_dir(
                        input_dir=input_directory, root_path=root_dir_path
                    )

                    # Validate directory exists using transformed path
                    if not source_fs_fsspec.exists(transformed_directory):
                        validation = DirectoryValidationData(
                            original_path=input_directory,
                            transformed_path=transformed_directory,
                            is_valid=False,
                            error_message=f"Transformed path '{transformed_directory}' does not exist",
                            validation_method="filesystem",
                        )
                        response.add_validation_result(validation)
                        response.add_error(
                            f"Directory does not exist: {input_directory} -> {transformed_directory}"
                        )
                        continue

                    # Validate it's actually a directory
                    if not source_fs_fsspec.isdir(transformed_directory):
                        validation = DirectoryValidationData(
                            original_path=input_directory,
                            transformed_path=transformed_directory,
                            is_valid=False,
                            error_message=f"Transformed path '{transformed_directory}' is not a directory",
                            validation_method="filesystem",
                        )
                        response.add_validation_result(validation)
                        response.add_error(
                            f"Path is not a directory: {input_directory} -> {transformed_directory}"
                        )
                        continue

                    # Directory is valid
                    valid_directories.append(transformed_directory)
                    response.add_directory(transformed_directory)

                    validation = DirectoryValidationData(
                        original_path=input_directory,
                        transformed_path=transformed_directory,
                        is_valid=True,
                        validation_method="filesystem",
                    )
                    response.add_validation_result(validation)

                    logger.debug(
                        f"Validated directory: {input_directory} -> {transformed_directory}"
                    )

                except Exception as e:
                    validation = DirectoryValidationData(
                        original_path=input_directory,
                        transformed_path=input_directory,  # Fallback to original
                        is_valid=False,
                        error_message=f"Path validation failed: {str(e)}",
                        validation_method="error",
                    )
                    response.add_validation_result(validation)
                    response.add_error(
                        f"Failed to validate directory '{input_directory}': {str(e)}"
                    )

                    # Re-raise path validation errors to match backend behavior
                    if isinstance(e, (FileNotFoundError, NotADirectoryError)):
                        raise ConnectionError(
                            f"Invalid input directory '{input_directory}': {str(e)}"
                        ) from e
                    else:
                        raise ConnectionError(
                            f"Path validation failed for '{input_directory}': {str(e)}"
                        ) from e

            # If no valid directories, return empty response
            if not valid_directories:
                response.processing_time = time.time() - start_time
                logger.warning("No valid directories found for processing")
                return response

            # Process file patterns - Backend source.py:169-181 logic
            file_pattern_config = request.file_pattern_config
            if file_pattern_config:
                file_pattern_config.wildcard_patterns = (
                    file_pattern_config.generate_wildcard_patterns()
                )

            # List files using backend-compatible logic
            max_files = request.max_files
            recursive = request.recursive
            total_files_processed = 0

            # Initialize deduplication tracking to prevent duplicate file processing
            processed_files = set()  # Track files that have been processed

            for directory in valid_directories:
                if total_files_processed >= max_files:
                    logger.info(f"Reached maximum file limit of {max_files}")
                    break

                logger.debug(f"Processing directory: {directory}")

                # Use fs_fsspec.walk() pattern like backend source.py:307
                max_depth = 10 if recursive else 1

                try:
                    for root, dirs, _ in source_fs_fsspec.walk(
                        directory, maxdepth=max_depth
                    ):
                        if total_files_processed >= max_files:
                            break

                        try:
                            # Get file metadata list like backend source.py:309
                            fs_metadata_list = source_fs_fsspec.listdir(root)
                        except Exception as e:
                            logger.warning(f"Failed to list directory {root}: {e}")
                            continue

                        # Process files in this directory
                        for fs_metadata in fs_metadata_list:
                            if total_files_processed >= max_files:
                                break

                            file_path = fs_metadata.get("name")
                            if not file_path:
                                continue

                            # Enhanced directory detection using FileOperations
                            try:
                                # Use the new shared directory detection logic
                                connector_name = (
                                    source_config.connector_id.split("|")[0]
                                    if "|" in source_config.connector_id
                                    else source_config.connector_id
                                )

                                # Check if this should be skipped as a directory
                                if FileOperations.should_skip_directory_object(
                                    file_path=file_path,
                                    metadata=fs_metadata,
                                    connector_name=connector_name,
                                ):
                                    logger.debug(
                                        f"Skipping directory object: {file_path}"
                                    )
                                    continue

                                # Fallback to fsspec check if enhanced detection didn't filter it
                                if not source_fs_fsspec.isfile(file_path):
                                    logger.debug(f"Skipping non-file object: {file_path}")
                                    continue

                            except Exception as e:
                                logger.debug(
                                    f"Could not check if '{file_path}' is a file: {e}"
                                )
                                continue

                            # Apply file pattern filtering
                            file_name = file_path.split("/")[-1]
                            if (
                                file_pattern_config
                                and not file_pattern_config.matches_pattern(file_name)
                            ):
                                continue

                            # Get file info and create FileHashData
                            try:
                                file_info = source_fs_fsspec.info(file_path)
                                file_size = file_info.get("size", 0)

                                # Create provider_file_uuid using connector method like backend source.py:603-604
                                provider_file_uuid = (
                                    source_connector.get_file_system_uuid(
                                        file_path=file_path, metadata=file_info
                                    )
                                )

                                # Validate provider UUID for this file
                                uuid_validation = (
                                    FileOperations.validate_provider_file_uuid(
                                        file_path=file_path,
                                        provider_file_uuid=provider_file_uuid,
                                        metadata=file_info,
                                        connector_name=connector_name,
                                    )
                                )

                                # If UUID validation indicates this is a directory, skip it
                                if not uuid_validation["should_have_uuid"]:
                                    logger.debug(
                                        f"Skipping directory object based on UUID validation: {file_path}"
                                    )
                                    continue

                                # Clear invalid UUIDs for directories
                                if not uuid_validation["is_valid"]:
                                    logger.warning(
                                        f"Invalid provider UUID for {file_path}: {uuid_validation['errors']}"
                                    )
                                    provider_file_uuid = None

                                # Serialize metadata like backend source.py:606
                                serialized_metadata = {
                                    "last_modified": file_info.get("mtime"),
                                    "file_type": file_info.get("type"),
                                    "connector_id": source_config.connector_id,
                                    "etag": file_info.get("etag"),
                                    "size": file_size,
                                }

                                # Check for duplicates using enhanced deduplication logic
                                dedup_keys = FileOperations.create_deduplication_key(
                                    file_path=file_path,
                                    provider_file_uuid=provider_file_uuid,
                                    file_hash=None,  # Content hash not computed during listing
                                )

                                # Check if any deduplication key has been seen before
                                is_duplicate = any(
                                    key in processed_files for key in dedup_keys
                                )

                                if is_duplicate:
                                    logger.debug(
                                        f"Skipping duplicate file: {file_path} (UUID: {provider_file_uuid})"
                                    )
                                    continue

                                # Add all deduplication keys to tracking set
                                processed_files.update(dedup_keys)

                                # Create FileHashData object
                                file_data = FileHashData(
                                    file_name=file_name,
                                    file_path=file_path,
                                    file_size=file_size,
                                    mime_type=FileOperations.detect_mime_type(file_name),
                                    provider_file_uuid=provider_file_uuid,
                                    source_connection_type=source_config.connector_id,
                                    fs_metadata=serialized_metadata,
                                    connector_metadata=source_config.connector_metadata,  # Include connector credentials/settings
                                    connector_id=source_config.connector_id,  # Include full connector ID
                                )

                                # CRITICAL: Apply FileHistory filtering if use_file_history is enabled
                                # This replicates backend source.py:392 _is_new_file() logic
                                if request.use_file_history:
                                    try:
                                        # Use the already implemented FileOperations.is_file_already_processed
                                        # This function replicates the exact backend FileHistory logic
                                        file_check_result = FileOperations.is_file_already_processed_for_listing(
                                            workflow_id=request.workflow_id,
                                            provider_file_uuid=provider_file_uuid,
                                            file_path=file_path,
                                            organization_id=request.organization_id,
                                        )

                                        if not file_check_result["should_process"]:
                                            logger.info(
                                                f"Skipping already processed file: {file_path} - {file_check_result.get('skip_reason', 'Already processed')}"
                                            )
                                            continue  # Skip this file, don't add to response

                                    except Exception as history_error:
                                        logger.warning(
                                            f"Failed to check file history for {file_path}: {history_error}"
                                        )
                                        # On error, proceed with file inclusion (fail-safe behavior)

                                response.add_file(file_data)
                                total_files_processed += 1

                            except Exception as e:
                                logger.warning(f"Failed to process file {file_path}: {e}")
                                continue

                except Exception as e:
                    error_msg = f"Failed to process directory {directory}: {str(e)}"
                    logger.error(error_msg)
                    response.add_error(error_msg)
                    continue

            response.processing_time = time.time() - start_time
            logger.info(
                f"Enhanced file listing completed: {response.total_files} files from {len(valid_directories)} directories in {response.processing_time:.2f}s"
            )

            return response

        except Exception as e:
            response.processing_time = time.time() - start_time
            error_msg = f"Enhanced file listing failed: {str(e)}"
            logger.error(error_msg)
            response.add_error(error_msg)

            # Re-raise connection errors to maintain backend compatibility
            if isinstance(e, ConnectionError):
                raise
            else:
                raise ConnectionError(error_msg) from e

    @staticmethod
    def get_connector_health(source_config: dict[str, Any]) -> dict[str, Any]:
        """Get health status of a source connector.

        Args:
            source_config: Source configuration dictionary

        Returns:
            Dictionary with health status and metadata
        """
        try:
            connector_id = source_config.get("connector_id") or source_config.get(
                "connection_type"
            )
            settings = source_config.get("settings", {})

            if not connector_id or not settings:
                return {
                    "is_healthy": False,
                    "connection_type": connector_id,
                    "errors": ["Missing connector configuration"],
                    "response_time_ms": None,
                }

            import time

            start_time = time.time()

            # Test connection
            connection_result = ConnectorOperations.test_connector_connection(
                connector_id, settings
            )

            response_time = int(
                (time.time() - start_time) * 1000
            )  # Convert to milliseconds

            return {
                "is_healthy": connection_result["is_connected"],
                "connection_type": connector_id,
                "errors": [connection_result["error"]]
                if connection_result["error"]
                else [],
                "response_time_ms": response_time,
            }

        except Exception as e:
            return {
                "is_healthy": False,
                "connection_type": source_config.get("connector_id", "unknown"),
                "errors": [str(e)],
                "response_time_ms": None,
            }
