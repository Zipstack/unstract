"""Common File Operations for Unstract Platform

This module provides shared file operations that can be used by both
Django backend and Celery workers without Django dependencies.

Shared between:
- backend/workflow_manager/endpoint_v2/source.py
- workers/shared/source_operations.py
- Any other component that needs file operations
"""

import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from .constants import FilePatternConstants
from .data_models import FileHash, FileHashData, FileOperationConstants

logger = logging.getLogger(__name__)


class FileOperations:
    """Common file operations shared between backend and workers"""

    @staticmethod
    def compute_file_content_hash_from_fsspec(source_fs, file_path: str) -> str:
        """Generate a hash value from the file content using fsspec filesystem.

        This matches the exact implementation from backend source.py:745

        Args:
            source_fs: The file system object (fsspec compatible)
            file_path: The path of the file

        Returns:
            str: The SHA256 hash value of the file content
        """
        file_content_hash = hashlib.sha256()
        source = (
            source_fs.get_fsspec_fs()
            if hasattr(source_fs, "get_fsspec_fs")
            else source_fs
        )

        try:
            with source.open(file_path, "rb") as remote_file:
                while chunk := remote_file.read(FileOperationConstants.READ_CHUNK_SIZE):
                    file_content_hash.update(chunk)
            return file_content_hash.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to compute content hash for {file_path}: {e}")
            # Return a fallback hash based on file path and current time
            import time

            fallback_string = f"{file_path}:{time.time()}"
            return hashlib.sha256(fallback_string.encode()).hexdigest()

    @staticmethod
    def compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            file_path: Path to the file
            chunk_size: Size of chunks to read (default 8KB)

        Returns:
            SHA-256 hex string of file content

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file cannot be read
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to compute hash for {file_path}: {str(e)}")
            raise

    @staticmethod
    def detect_mime_type(file_path: str) -> str:
        """Detect MIME type of file.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string (default: 'application/octet-stream')
        """
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            return mime_type or "application/octet-stream"
        except Exception as e:
            logger.warning(f"Failed to detect MIME type for {file_path}: {str(e)}")
            return "application/octet-stream"

    @staticmethod
    def create_file_hash_from_backend_logic(
        file_path: str,
        source_fs,
        source_connection_type: str,
        file_size: int,
        fs_metadata: dict[str, Any],
        compute_content_hash: bool = False,
    ) -> FileHash:
        """Create FileHash object matching backend source.py:352 _create_file_hash.

        Args:
            file_path: Path to the file
            source_fs: File system object (UnstractFileSystem)
            source_connection_type: Type of source connection (FILESYSTEM/API)
            file_size: Size of the file in bytes
            fs_metadata: Metadata from fsspec
            compute_content_hash: Whether to compute file content hash (only for API deployments)

        Returns:
            FileHash: Populated FileHash object
        """
        # Only compute content hash for API deployments or when explicitly requested
        file_hash = None
        if compute_content_hash:
            file_hash = FileOperations.compute_file_content_hash_from_fsspec(
                source_fs, file_path
            )

        # Extract file name from path
        file_name = os.path.basename(file_path)

        # Get provider-specific file UUID (this is the primary identifier for ETL/TASK)
        provider_file_uuid = None
        # Use the correct method name - check the source_fs interface
        if hasattr(source_fs, "get_file_system_uuid"):
            provider_file_uuid = source_fs.get_file_system_uuid(
                file_path=file_path, metadata=fs_metadata
            )
        elif hasattr(source_fs, "extract_metadata_file_hash"):
            provider_file_uuid = source_fs.extract_metadata_file_hash(fs_metadata)

        # Detect MIME type if possible
        mime_type = fs_metadata.get("ContentType") or fs_metadata.get("content_type")

        # Sanitize metadata for JSON serialization (critical for Celery tasks)
        sanitized_metadata = FileOperations._sanitize_metadata_for_serialization(
            fs_metadata
        )

        return FileHash(
            file_path=file_path,
            file_name=file_name,
            source_connection_type=source_connection_type,
            file_hash=file_hash,  # None for ETL/TASK, computed for API deployments
            file_size=file_size,
            provider_file_uuid=provider_file_uuid,
            mime_type=mime_type,
            fs_metadata=sanitized_metadata,
        )

    @staticmethod
    def _sanitize_metadata_for_serialization(metadata: dict[str, Any]) -> dict[str, Any]:
        """Sanitize file metadata for JSON serialization by converting non-serializable objects.

        This is critical for Azure Blob Storage which includes ContentSettings objects
        that cannot be serialized for Celery task distribution.

        Args:
            metadata: Raw metadata dictionary from fsspec/connector

        Returns:
            dict[str, Any]: Sanitized metadata safe for JSON serialization
        """
        if not isinstance(metadata, dict):
            return {}

        sanitized = {}

        for key, value in metadata.items():
            try:
                # Handle Azure ContentSettings object or similar objects with content_type
                if hasattr(value, "content_type") and hasattr(value, "__dict__"):
                    # Convert ContentSettings-like objects to dictionary
                    try:
                        sanitized[key] = {
                            "content_type": getattr(value, "content_type", None),
                            "content_encoding": getattr(value, "content_encoding", None),
                            "content_language": getattr(value, "content_language", None),
                            "content_disposition": getattr(
                                value, "content_disposition", None
                            ),
                            "cache_control": getattr(value, "cache_control", None),
                            "content_md5": value.content_md5.hex()
                            if getattr(value, "content_md5", None)
                            else None,
                        }
                        continue
                    except Exception as content_error:
                        logger.debug(
                            f"Failed to convert ContentSettings object: {content_error}"
                        )
                        sanitized[key] = str(value)
                        continue

                # Handle bytearray objects (like content_md5)
                if isinstance(value, bytearray):
                    sanitized[key] = value.hex()
                    continue

                # Handle datetime objects
                if hasattr(value, "isoformat"):
                    sanitized[key] = value.isoformat()
                    continue

                # Handle other complex objects by converting to string
                if not FileOperations._is_json_serializable(value):
                    sanitized[key] = str(value)
                    continue

                # Keep as-is if it's JSON serializable
                sanitized[key] = value

            except Exception as e:
                # If anything fails, convert to string as fallback
                logger.debug(
                    f"Failed to sanitize metadata key '{key}': {e}, converting to string"
                )
                sanitized[key] = str(value)

        return sanitized

    @staticmethod
    def _is_json_serializable(obj: Any) -> bool:
        """Check if an object is JSON serializable."""
        import json

        try:
            json.dumps(obj)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def process_file_fs_directory(
        fs_metadata_list: list[dict[str, Any]],
        count: int,
        limit: int,
        unique_file_paths: set[str],
        matched_files: dict[str, FileHash],
        patterns: list[str],
        source_fs,
        source_connection_type: str,
        dirs: list[str],
        workflow_log=None,
        connector_id: str | None = None,
    ) -> int:
        """Process directory items matching backend source.py:326 _process_file_fs_directory.

        Args:
            fs_metadata_list: List of file metadata from fsspec listdir
            count: Current count of matched files
            limit: Maximum number of files to process
            unique_file_paths: Set of already seen file paths
            matched_files: Dictionary to populate with matched files
            patterns: File patterns to match
            source_fs: File system object
            source_connection_type: Type of source connection
            dirs: List of directories from fsspec walk
            workflow_log: Optional workflow logger

        Returns:
            int: Updated count of matched files
        """
        for fs_metadata in fs_metadata_list:
            if count >= limit:
                msg = f"Maximum limit of '{limit}' files to process reached"
                if workflow_log:
                    workflow_log.publish_log(msg)
                logger.info(msg)
                break

            file_path = fs_metadata.get("name")
            file_size = fs_metadata.get("size", 0)

            if not file_path or FileOperations._is_directory_backend_compatible(
                source_fs, file_path, fs_metadata, dirs
            ):
                continue

            # Add connector_id to fs_metadata if provided
            if connector_id:
                fs_metadata = fs_metadata.copy()  # Don't modify original
                fs_metadata["connector_id"] = connector_id

            file_hash = FileOperations.create_file_hash_from_backend_logic(
                file_path=file_path,
                source_fs=source_fs,
                source_connection_type=source_connection_type,
                file_size=file_size,
                fs_metadata=fs_metadata,
                compute_content_hash=False,  # ETL/TASK: Only use provider_file_uuid for deduplication
            )

            if FileOperations._should_skip_file_backend_compatible(file_hash, patterns):
                continue

            # Skip duplicate files
            if FileOperations._is_duplicate_backend_compatible(
                file_hash, unique_file_paths
            ):
                msg = f"Skipping execution of duplicate file '{file_path}'"
                if workflow_log:
                    workflow_log.publish_log(msg)
                logger.info(msg)
                continue

            FileOperations._update_unique_file_paths_backend_compatible(
                file_hash, unique_file_paths
            )

            matched_files[file_path] = file_hash
            count += 1

        return count

    @staticmethod
    def _is_directory_backend_compatible(
        source_fs, file_path: str, metadata: dict, dirs: list
    ) -> bool:
        """Check if path is directory matching backend logic."""
        try:
            # Check if basename is in dirs list from walk
            if os.path.basename(file_path) in dirs:
                return True

            # Try fsspec isdir
            fs_fsspec = (
                source_fs.get_fsspec_fs()
                if hasattr(source_fs, "get_fsspec_fs")
                else source_fs
            )
            try:
                if fs_fsspec.isdir(file_path):
                    return True
            except Exception:
                pass

            # Check metadata type
            file_type = metadata.get("type", "").lower()
            if file_type in ["directory", "dir", "folder"]:
                return True

            return False

        except Exception:
            return False

    @staticmethod
    def _should_skip_file_backend_compatible(
        file_hash: FileHash, patterns: list[str]
    ) -> bool:
        """Check if file should be skipped based on patterns with case-insensitive matching."""
        if not patterns or patterns == ["*"]:
            return False

        import fnmatch

        file_name = file_hash.file_name

        for pattern in patterns:
            # Case-insensitive pattern matching to handle Azure Blob Storage case variations
            if fnmatch.fnmatch(file_name.lower(), pattern.lower()):
                return False

        return True

    @staticmethod
    def _is_duplicate_backend_compatible(
        file_hash: FileHash, unique_file_paths: set[str]
    ) -> bool:
        """Check if file is duplicate."""
        return file_hash.file_path in unique_file_paths

    @staticmethod
    def _update_unique_file_paths_backend_compatible(
        file_hash: FileHash, unique_file_paths: set
    ) -> None:
        """Update unique file paths."""
        unique_file_paths.add(file_hash.file_path)

    @staticmethod
    def valid_file_patterns(required_patterns: list[str]) -> list[str]:
        """Get valid file patterns matching backend logic with display name translation."""
        if not required_patterns:
            return ["*"]

        valid_patterns = [p for p in required_patterns if p and p.strip()]

        if not valid_patterns:
            return ["*"]

        # Translate display names to actual file patterns
        translated_patterns = []
        for pattern in valid_patterns:
            translated = FileOperations._translate_display_name_to_pattern(pattern)
            translated_patterns.extend(translated)

        return translated_patterns if translated_patterns else ["*"]

    @staticmethod
    def _translate_display_name_to_pattern(display_name: str) -> list[str]:
        """Translate UI display names to actual file matching patterns.

        Args:
            display_name: Display name from UI (e.g., "PDF documents")

        Returns:
            List of file patterns (e.g., ["*.pdf"])
        """
        # First, try exact display name match using constants
        patterns = FilePatternConstants.get_patterns_for_display_name(display_name)
        if patterns:
            logger.info(
                f"Translating display name '{display_name}' to patterns: {patterns}"
            )
            return patterns

        # If it looks like a file pattern already (contains * or .), use as-is
        if "*" in display_name or "." in display_name:
            return [display_name]

        # Try to infer patterns from keywords using constants
        inferred_patterns = FilePatternConstants.infer_patterns_from_keyword(display_name)
        if inferred_patterns:
            logger.info(f"Inferred patterns for '{display_name}': {inferred_patterns}")
            return inferred_patterns

        # If no match, return the original pattern
        logger.warning(
            f"Unknown display name pattern '{display_name}', using as literal pattern"
        )
        return [display_name]

    @staticmethod
    def validate_file_compatibility(
        file_data: FileHash, workflow_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate file against workflow requirements.

        This shared validation logic ensures consistency between
        backend endpoint validation and worker file processing.

        Args:
            file_data: FileHashData object with file information
            workflow_config: Workflow configuration with validation rules

        Returns:
            Dictionary with 'is_valid' boolean and 'errors' list
        """
        validations = {"is_valid": True, "errors": []}

        # Check file size limits
        max_size = workflow_config.get(
            "max_file_size", 100 * 1024 * 1024
        )  # 100MB default
        if file_data.file_size > max_size:
            validations["is_valid"] = False
            validations["errors"].append(
                f"File size {file_data.file_size} bytes exceeds limit: {max_size} bytes"
            )

        # Check minimum file size
        min_size = workflow_config.get("min_file_size", 1)  # 1 byte default
        if file_data.file_size < min_size:
            validations["is_valid"] = False
            validations["errors"].append(
                f"File size {file_data.file_size} bytes below minimum: {min_size} bytes"
            )

        # Check allowed MIME types
        allowed_types = workflow_config.get("allowed_mime_types", [])
        if allowed_types and file_data.mime_type not in allowed_types:
            validations["is_valid"] = False
            validations["errors"].append(
                f"MIME type not allowed: {file_data.mime_type}. Allowed: {allowed_types}"
            )

        # Check blocked MIME types
        blocked_types = workflow_config.get("blocked_mime_types", [])
        if blocked_types and file_data.mime_type in blocked_types:
            validations["is_valid"] = False
            validations["errors"].append(f"MIME type blocked: {file_data.mime_type}")

        # Check file extensions
        allowed_extensions = workflow_config.get("allowed_extensions", [])
        if allowed_extensions:
            file_ext = Path(file_data.file_name).suffix.lower()
            if file_ext not in [ext.lower() for ext in allowed_extensions]:
                validations["is_valid"] = False
                validations["errors"].append(
                    f"File extension not allowed: {file_ext}. Allowed: {allowed_extensions}"
                )

        # Check blocked extensions
        blocked_extensions = workflow_config.get("blocked_extensions", [])
        if blocked_extensions:
            file_ext = Path(file_data.file_name).suffix.lower()
            if file_ext in [ext.lower() for ext in blocked_extensions]:
                validations["is_valid"] = False
                validations["errors"].append(f"File extension blocked: {file_ext}")

        return validations

    @staticmethod
    def create_file_metadata(
        file_path: str, compute_hash: bool = True, include_fs_metadata: bool = True
    ) -> FileHashData:
        """Create FileHashData with computed metadata.

        This shared logic ensures consistent file metadata creation
        across backend and workers.

        Args:
            file_path: Path to the file
            compute_hash: Whether to compute SHA-256 content hash
            include_fs_metadata: Whether to include filesystem metadata

        Returns:
            FileHashData object with computed metadata

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_info = Path(file_path)

        if not file_info.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get basic file information
        stat_info = file_info.stat()

        file_data = FileHashData(
            file_name=file_info.name,
            file_path=str(file_path),
            file_size=stat_info.st_size,
            mime_type=FileOperations.detect_mime_type(str(file_path)),
        )

        # Compute content hash if requested
        if compute_hash:
            try:
                file_data.file_hash = FileOperations.compute_file_hash(str(file_path))
            except Exception as e:
                logger.warning(f"Failed to compute hash for {file_path}: {str(e)}")
                file_data.file_hash = ""

        # Include filesystem metadata if requested
        if include_fs_metadata:
            file_data.fs_metadata = {
                "created_time": stat_info.st_ctime,
                "modified_time": stat_info.st_mtime,
                "accessed_time": stat_info.st_atime,
                "is_file": file_info.is_file(),
                "is_dir": file_info.is_dir(),
                "permissions": oct(stat_info.st_mode)[-3:],
            }

        return file_data

    @staticmethod
    def validate_file_path(
        file_path: str, allowed_paths: list[str] | None = None
    ) -> dict[str, Any]:
        """Validate file path for security and access.

        Args:
            file_path: Path to validate
            allowed_paths: List of allowed path prefixes (optional)

        Returns:
            Dictionary with 'is_valid' boolean and 'errors' list
        """
        validation = {"is_valid": True, "errors": []}

        try:
            # Resolve and normalize path
            resolved_path = Path(file_path).resolve()

            # Check for path traversal attempts
            if ".." in str(resolved_path):
                validation["is_valid"] = False
                validation["errors"].append("Path traversal detected")

            # Check against allowed paths if provided
            if allowed_paths:
                path_allowed = False
                for allowed_path in allowed_paths:
                    try:
                        resolved_allowed = Path(allowed_path).resolve()
                        if resolved_path.is_relative_to(resolved_allowed):
                            path_allowed = True
                            break
                    except (ValueError, OSError):
                        continue

                if not path_allowed:
                    validation["is_valid"] = False
                    validation["errors"].append(
                        f"Path not in allowed directories: {allowed_paths}"
                    )

            # Check if file exists
            if not resolved_path.exists():
                validation["is_valid"] = False
                validation["errors"].append("File does not exist")

            # Check if it's actually a file (not a directory)
            elif not resolved_path.is_file():
                validation["is_valid"] = False
                validation["errors"].append("Path is not a file")

        except Exception as e:
            validation["is_valid"] = False
            validation["errors"].append(f"Path validation failed: {str(e)}")

        return validation

    @staticmethod
    def get_file_batch_metadata(file_paths: list[str]) -> dict[str, Any]:
        """Get metadata for a batch of files efficiently.

        Args:
            file_paths: List of file paths

        Returns:
            Dictionary with batch metadata and individual file data
        """
        batch_metadata = {
            "total_files": len(file_paths),
            "total_size": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "file_data": [],
            "errors": [],
        }

        for file_path in file_paths:
            try:
                file_data = FileOperations.create_file_metadata(
                    file_path=file_path,
                    compute_hash=False,  # Skip hash computation for batch operations
                    include_fs_metadata=False,
                )

                batch_metadata["file_data"].append(file_data.to_dict())
                batch_metadata["total_size"] += file_data.file_size
                batch_metadata["valid_files"] += 1

            except Exception as e:
                batch_metadata["invalid_files"] += 1
                batch_metadata["errors"].append({"file_path": file_path, "error": str(e)})

        return batch_metadata

    @staticmethod
    def is_directory_by_patterns(
        file_path: str,
        metadata: dict[str, Any] | None = None,
        connector_name: str | None = None,
    ) -> bool:
        """Enhanced directory detection using file patterns and metadata.

        This method provides connector-agnostic directory detection that works
        across different storage backends (GCS, S3, Azure, local filesystem).

        Args:
            file_path: Path to check
            metadata: Optional file metadata from connector
            connector_name: Optional connector name for specific patterns

        Returns:
            True if the path appears to be a directory
        """
        # Primary check: Path ends with slash (universal directory indicator)
        if file_path.endswith("/"):
            logger.debug(
                f"[Directory Check] '{file_path}' identified as directory: ends with '/'"
            )
            return True

        # Check for common directory naming patterns
        if FileOperations._looks_like_directory_path(file_path):
            logger.debug(
                f"[Directory Check] '{file_path}' identified as directory: naming pattern"
            )
            return True

        # Connector-specific directory detection
        if metadata and connector_name:
            if FileOperations._is_directory_by_connector_patterns(
                file_path, metadata, connector_name
            ):
                logger.debug(
                    f"[Directory Check] '{file_path}' identified as directory: connector-specific pattern"
                )
                return True

        # Enhanced zero-size file check with additional validation
        if metadata:
            file_size = metadata.get("size", 0)
            if file_size == 0:
                # Only treat zero-size objects as directories if they have directory indicators
                if FileOperations._has_directory_indicators(
                    file_path, metadata, connector_name
                ):
                    logger.debug(
                        f"[Directory Check] '{file_path}' identified as directory: zero-size with directory indicators"
                    )
                    return True

        return False

    @staticmethod
    def _looks_like_directory_path(file_path: str) -> bool:
        """Check if a file path looks like a directory based on naming patterns."""
        file_name = os.path.basename(file_path)

        # Directory-like names (no file extension, common folder names)
        common_dir_names = {
            "tmp",
            "temp",
            "cache",
            "logs",
            "data",
            "config",
            "bin",
            "lib",
            "src",
            "test",
            "tests",
            "docs",
            "assets",
            "images",
            "files",
            "duplicate-test",  # Add the specific directory from the issue
        }

        # Check if it's a common directory name
        if file_name.lower() in common_dir_names:
            return True

        # Check if it has no file extension and contains no dots (likely a folder)
        if "." not in file_name and len(file_name) > 0:
            return True

        return False

    @staticmethod
    def _is_directory_by_connector_patterns(
        file_path: str, metadata: dict[str, Any], connector_name: str
    ) -> bool:
        """Check connector-specific patterns that indicate a directory."""
        connector_name = connector_name.lower()

        # Google Cloud Storage specific patterns
        if "google" in connector_name or "gcs" in connector_name:
            content_type = metadata.get("contentType", "")
            object_name = metadata.get("name", file_path)

            # GCS folder objects often have specific content types
            if content_type in ["text/plain", "application/x-www-form-urlencoded"]:
                return True

            # GCS folder objects may have no content type
            if not content_type and metadata.get("size", 0) == 0:
                return True

            # Object name ends with "/" in GCS
            if object_name.endswith("/"):
                return True

        # AWS S3 specific patterns (for future extensibility)
        elif "s3" in connector_name or "amazon" in connector_name:
            # S3 folder objects typically end with /
            if file_path.endswith("/"):
                return True

            # S3 may have specific metadata markers
            if metadata.get("ContentType") == "application/x-directory":
                return True

        # Azure Blob Storage specific patterns (for future extensibility)
        elif "azure" in connector_name:
            content_type = metadata.get("content_type", "")
            if content_type == "httpd/unix-directory":
                return True

        return False

    @staticmethod
    def _has_directory_indicators(
        file_path: str, metadata: dict[str, Any], connector_name: str | None = None
    ) -> bool:
        """Check if a zero-size object has additional directory indicators."""
        # Path-based indicators
        if file_path.endswith("/"):
            return True

        if FileOperations._looks_like_directory_path(file_path):
            return True

        # Metadata-based indicators
        if connector_name:
            connector_name = connector_name.lower()

            # GCS-specific indicators
            if "google" in connector_name or "gcs" in connector_name:
                content_type = metadata.get("contentType", "")
                if content_type in ["text/plain", "application/x-www-form-urlencoded"]:
                    return True

                # Check for folder-like etag patterns in GCS
                etag = metadata.get("etag", "")
                if etag and not etag.startswith(
                    '"'
                ):  # GCS folders often have simple etags
                    return True

        return False

    @staticmethod
    def should_skip_directory_object(
        file_path: str,
        metadata: dict[str, Any] | None = None,
        connector_name: str | None = None,
    ) -> bool:
        """Determine if a file object should be skipped because it's actually a directory.

        This method provides a single entry point for directory filtering
        that can be used by both backend and workers.

        Args:
            file_path: Path to check
            metadata: Optional file metadata from connector
            connector_name: Optional connector name for specific patterns

        Returns:
            True if the object should be skipped (it's a directory)
        """
        is_directory = FileOperations.is_directory_by_patterns(
            file_path=file_path, metadata=metadata, connector_name=connector_name
        )

        if is_directory:
            logger.info(f"Skipping directory object: {file_path}")
            return True

        return False

    @staticmethod
    def validate_provider_file_uuid(
        file_path: str,
        provider_file_uuid: str | None,
        metadata: dict[str, Any] | None = None,
        connector_name: str | None = None,
    ) -> dict[str, Any]:
        """Validate provider file UUID and ensure it's not assigned to directories.

        Args:
            file_path: File path
            provider_file_uuid: Provider-assigned file UUID
            metadata: File metadata
            connector_name: Connector name

        Returns:
            Dictionary with validation results
        """
        validation = {"is_valid": True, "should_have_uuid": True, "errors": []}

        # Check if this is a directory - directories shouldn't have UUIDs
        if FileOperations.is_directory_by_patterns(file_path, metadata, connector_name):
            validation["should_have_uuid"] = False

            if provider_file_uuid:
                validation["is_valid"] = False
                validation["errors"].append(
                    f"Directory object '{file_path}' should not have provider UUID: {provider_file_uuid}"
                )

        # Check UUID format if present
        if provider_file_uuid and validation["should_have_uuid"]:
            if not provider_file_uuid.strip():
                validation["is_valid"] = False
                validation["errors"].append("Provider UUID is empty or whitespace-only")

        return validation

    @staticmethod
    def create_deduplication_key(
        file_path: str | None = None,
        provider_file_uuid: str | None = None,
        file_hash: str | None = None,
    ) -> list[str]:
        """Create deduplication keys for file tracking.

        Returns multiple keys to support different deduplication strategies.

        Args:
            file_path: File path
            provider_file_uuid: Provider UUID
            file_hash: Content hash

        Returns:
            List of deduplication keys
        """
        keys = []

        # Path-based key
        if file_path:
            keys.append(f"path:{file_path}")

        # UUID-based key (most reliable for same file across different paths)
        if provider_file_uuid:
            keys.append(f"uuid:{provider_file_uuid}")

        # Content-based key (for content deduplication)
        if file_hash:
            keys.append(f"hash:{file_hash}")

        return keys

    @staticmethod
    def is_file_already_processed(
        api_client,
        workflow_id: str,
        provider_file_uuid: str | None,
        file_path: str,
        organization_id: str,
        use_file_history: bool = True,
    ) -> dict[str, Any]:
        """Check if file is already processed using backend-compatible FileHistory logic.

        This method replicates the exact logic from backend source.py:515-540 (_is_new_file)
        to ensure consistent deduplication behavior between backend and workers.

        Args:
            api_client: API client for backend communication
            workflow_id: Workflow ID
            provider_file_uuid: Provider file UUID (from source connector)
            file_path: File path
            organization_id: Organization ID
            use_file_history: Whether to use file history (matches backend parameter)

        Returns:
            Dictionary with processing status:
            {
                'is_new_file': bool,
                'should_process': bool,
                'skip_reason': str,
                'file_history': dict
            }
        """
        result = {
            "is_new_file": True,
            "should_process": True,
            "skip_reason": None,
            "file_history": None,
        }

        try:
            # Always treat as new if history usage is not enforced (backend source.py:517-518)
            if not use_file_history:
                logger.debug(
                    f"File history not enforced - treating {file_path} as new file"
                )
                return result

            # Always treat as new if provider_file_uuid is not available (backend source.py:521-522)
            if not provider_file_uuid:
                logger.debug(
                    f"No provider_file_uuid available for {file_path} - treating as new file"
                )
                return result

            logger.info(
                f"Checking file history for {file_path} with provider UUID: {provider_file_uuid}"
            )

            # Call backend API to get file history using FileHistoryHelper (backend source.py:566-570)
            file_history_response = api_client.get_file_history(
                workflow_id=workflow_id,
                provider_file_uuid=provider_file_uuid,
                file_path=file_path,
                organization_id=organization_id,
            )

            if not file_history_response or "file_history" not in file_history_response:
                logger.info(
                    f"No file history found for {file_path} - treating as new file"
                )
                return result

            file_history = file_history_response["file_history"]
            result["file_history"] = file_history

            # No history or incomplete history means the file is new (backend source.py:528-529)
            if not file_history or not file_history.get("is_completed", False):
                logger.info(
                    f"File history incomplete for {file_path} - treating as new file"
                )
                return result

            # Compare file paths (backend source.py:535-536)
            history_file_path = file_history.get("file_path")
            if history_file_path and history_file_path != file_path:
                logger.info(
                    f"File path changed from {history_file_path} to {file_path} - treating as new file"
                )
                return result

            # File has been processed with the same path (backend source.py:539-540)
            result["is_new_file"] = False
            result["should_process"] = False
            result["skip_reason"] = (
                f"File '{file_path}' has already been processed. Clear file markers to process again."
            )

            logger.info(f"File {file_path} already processed - skipping")
            return result

        except Exception as e:
            # If file history check fails, err on the side of processing the file
            logger.warning(
                f"Failed to check file history for {file_path}: {str(e)} - treating as new file"
            )
            result["skip_reason"] = f"File history check failed: {str(e)}"
            return result

    @staticmethod
    def is_file_already_processed_for_listing(
        workflow_id: str,
        provider_file_uuid: str | None,
        file_path: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """Check if file is already processed for file listing phase (without API client).

        This is a simplified version of is_file_already_processed that works during
        file listing when we don't have API client access.

        Args:
            workflow_id: Workflow ID
            provider_file_uuid: Provider file UUID
            file_path: File path
            organization_id: Organization ID

        Returns:
            Dictionary with should_process and skip_reason
        """
        # For file listing phase, we'll make a simplified check
        # Since we don't have API client here, we'll return should_process=True
        # and let the actual processing phase handle the deduplication

        # TODO: Implement direct database access for file listing phase
        # For now, return True to maintain existing behavior but log the check

        return {
            "should_process": True,
            "is_new_file": True,
            "skip_reason": None,
            "file_history": None,
            "note": "File listing phase - deduplication deferred to processing phase",
        }
