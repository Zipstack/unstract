import base64
import logging
import os
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from fsspec import AbstractFileSystem

from unstract.connectors.base import UnstractConnector
from unstract.connectors.enums import ConnectorMode
from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


class UnstractFileSystem(UnstractConnector, ABC):
    """Abstract class for file systems."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.FILE_SYSTEM

    @abstractmethod
    def get_fsspec_fs(self) -> AbstractFileSystem:
        pass

    @abstractmethod
    def test_credentials(self) -> bool:
        """Override to test credentials for a connector."""
        pass

    @abstractmethod
    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        This method must be implemented in subclasses.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        pass

    @abstractmethod
    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        pass

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Get the correct root directory for filesystem operations.

        This method provides a common implementation for path resolution that handles:
        - Root path combination logic
        - Proper path formatting for different connectors
        - Backward compatibility with Django backend expectations
        - Container/bucket-aware path handling for cloud storage

        Args:
            input_dir: Input directory path (may include bucket/container name)
            root_path: Root path configured for the connector (optional)
            connector_type: Type of connector for specific handling (optional)

        Returns:
            str: Properly formatted path with trailing slash for directory compatibility
        """
        root_path = kwargs.get("root_path", "")

        # If root_path is set, combine with input_dir
        if root_path:
            # Remove leading/trailing slashes
            root_path = root_path.strip("/")
            input_dir = input_dir.strip("/")

            # If input_dir is just "/", use root_path
            if not input_dir or input_dir == "/":
                # BACKWARD COMPATIBILITY: Ensure trailing slash for directory operations
                return f"{root_path}/" if not root_path.endswith("/") else root_path

            # Combine paths with trailing slash for backward compatibility
            combined_path = f"{root_path}/{input_dir}"
            return (
                f"{combined_path}/" if not combined_path.endswith("/") else combined_path
            )

        # If no root_path, clean up the input_dir
        input_dir = input_dir.strip("/")

        # Handle cloud storage paths (bucket/container format)
        if "/" in input_dir:
            # This might be "bucket/path" or "container/path" format
            # For cloud storage, we typically need the full path
            # BACKWARD COMPATIBILITY: Add trailing slash for directory operations
            return f"{input_dir}/" if not input_dir.endswith("/") else input_dir

        # Single path component (might be bucket/container name or folder)
        # BACKWARD COMPATIBILITY: Add trailing slash for directory operations
        return f"{input_dir}/" if not input_dir.endswith("/") else input_dir

    def get_file_size(
        self, file_path: str | None = None, metadata: dict[str, Any] | None = None
    ) -> int | None:
        """Get the size of a file."""
        if not metadata:
            if not file_path:
                return None
            fs_fsspec = self.get_fsspec_fs()
            metadata = fs_fsspec.stat(file_path)
        if not metadata or not isinstance(metadata, dict):
            return None
        return metadata.get("size")

    def serialize_metadata_value(self, value: Any, depth: int = 0) -> Any:
        """Recursively serialize metadata values to ensure JSON compatibility.

        Args:
            value: Any value that needs to be serialized
            depth: Current recursion depth (default: 0)

        Returns:
            JSON serializable version of the value
        """
        # Prevent infinite recursion
        if depth > 10:  # Max recursion depth
            return str(value)

        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, (bytes, bytearray)):
            return base64.b64encode(value).decode("utf-8")
        elif isinstance(value, dict):
            return {
                k: self.serialize_metadata_value(v, depth + 1) for k, v in value.items()
            }
        elif isinstance(value, (list, tuple)):
            return [self.serialize_metadata_value(v, depth + 1) for v in value]
        else:
            # For custom objects like ContentSettings, convert to dict if possible
            if hasattr(value, "__dict__"):
                try:
                    return self.serialize_metadata_value(value.__dict__, depth + 1)
                except Exception:
                    return str(value)
            # Last resort: convert to string
            return str(value)

    def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Get the metadata of a file.

        Args:
            file_path (str): Path of the file.

        Returns:
            dict[str, Any]: Metadata of the file or empty dict
                if metadata cannot be retrieved.
            All values are guaranteed to be JSON serializable.
        """
        try:
            fs_fsspec = self.get_fsspec_fs()
            metadata = fs_fsspec.stat(file_path)
            if not metadata or not isinstance(metadata, dict):
                return {}

            # Recursively serialize all metadata values
            serialized_metadata = {}
            for key, value in metadata.items():
                serialized_metadata[key] = self.serialize_metadata_value(value)

            return serialized_metadata
        except Exception as e:
            logger.error(f"Error getting file system metadata for {file_path}: {str(e)}")
            return {}

    def get_file_system_uuid(
        self, file_path: str, metadata: dict[str, Any]
    ) -> str | None:
        """Get the UUID of a file.

        Args:
            file_path (str): Path of the file.
            metadata (dict[str, Any]): Metadata of the file.

        Returns:
            Optional[str]: UUID of the file in hex format or None if not found.
        """
        if not metadata:
            fs_fsspec = self.get_fsspec_fs()
            metadata = fs_fsspec.stat(file_path)

        file_hash = self.extract_metadata_file_hash(metadata)
        if not file_hash:
            logger.error(f"File hash not found for {file_path}.")
        return file_hash

    def create_dir_if_not_exists(self, input_dir: str) -> None:
        """Method to create dir of a connector if not exists.

        Args:
            input_dir (str): input directory of source connector
        """
        fs_fsspec = self.get_fsspec_fs()
        is_dir = fs_fsspec.isdir(input_dir)
        if not is_dir:
            fs_fsspec.mkdir(input_dir)

    def upload_file_to_storage(self, source_path: str, destination_path: str) -> None:
        """Method to upload filepath from tool to destination connector
        directory.

        Args:
            source_path (str): local path of file to be uploaded, coming from tool
            destination_path (str): target path in the storage where the file will be
            uploaded
        """
        normalized_path = os.path.normpath(destination_path)
        destination_connector_fs = self.get_fsspec_fs()
        file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        workflow_fs = file_system.get_file_storage()
        data = workflow_fs.read(path=source_path, mode="rb")
        destination_connector_fs.write_bytes(normalized_path, data)
