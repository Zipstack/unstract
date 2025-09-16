import base64
import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
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

    @abstractmethod
    def extract_modified_date(self, metadata: dict[str, Any]) -> datetime | None:
        """Extract the last modified date from file metadata.

        Args:
            metadata: File metadata dictionary from fsspec

        Returns:
            datetime object or None if not available
        """
        pass

    def sort_files_by_modified_date(
        self, file_metadata_list: list[dict[str, Any]], ascending: bool = True
    ) -> list[dict[str, Any]]:
        """Sort files by their last modified date.

        Args:
            file_metadata_list: List of file metadata dictionaries
            ascending: If True, sort oldest first (FIFO); if False, newest first (LIFO)

        Returns:
            Sorted list of file metadata
        """

        def get_modified_date(metadata: dict[str, Any]) -> datetime:
            date = self.extract_modified_date(metadata)
            if date is None:
                # Fallback to epoch for files without timestamp
                return datetime.fromtimestamp(0, tz=UTC)
            # Ensure the extracted date is normalized to UTC and timezone-aware
            if date.tzinfo is None:
                # Naive datetime - assume UTC
                return date.replace(tzinfo=UTC)
            else:
                # Convert to UTC
                return date.astimezone(UTC)

        try:
            return sorted(
                file_metadata_list, key=get_modified_date, reverse=not ascending
            )
        except Exception as e:
            msg = "Failed to sort files by modified date"
            logger.warning(f"{msg}: {e}")
            self._store_user_error(msg)
            return file_metadata_list

    def _store_user_error(self, error_msg: str) -> None:
        """Store user-friendly error message for later reporting.

        Args:
            error_msg: User-friendly error message without technical details
        """
        if not hasattr(self, "_user_errors"):
            self._user_errors = []
        self._user_errors.append(error_msg)

    def list_files(
        self,
        directory: str,
        max_depth: int = 1,
        include_dirs: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List files in a directory with optional sorting.

        Args:
            directory: Directory path to list
            max_depth: Maximum depth for recursive traversal
            include_dirs: Whether to include directories in results
            limit: Maximum number of files to collect (for performance)

        Returns:
            List of file metadata dictionaries
        """
        all_files = []
        fs_fsspec = self.get_fsspec_fs()

        for root, dirs, _ in fs_fsspec.walk(directory, maxdepth=max_depth):
            try:
                fs_metadata_list = fs_fsspec.listdir(root)
                for metadata in fs_metadata_list:
                    if not include_dirs and self.is_dir_by_metadata(metadata):
                        continue
                    all_files.append(metadata)

                    if limit is not None and len(all_files) >= limit:
                        return all_files
            except Exception as e:
                logger.warning(f"Failed to list directory {root}: {e}")
                self._store_user_error(f"Could not access directory: {root}")
                continue
        return all_files

    def report_errors_to_user(self) -> list[str]:
        """Get accumulated errors and clear the list.

        This method will be called from source.py after list_files() completes,
        to get any accumulated errors for reporting to the user.

        Returns:
            List of user-friendly error messages
        """
        if hasattr(self, "_user_errors") and self._user_errors:
            errors = self._user_errors.copy()
            self._user_errors.clear()
            return errors
        return []

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Override to get root dir of a connector."""
        return f"{input_dir.strip('/')}/"

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
