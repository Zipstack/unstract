import logging
import os
from typing import Any

from fsspec.implementations.local import LocalFileSystem

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class LocalStorageFS(UnstractFileSystem):
    def __init__(self, settings: dict | None = None):  # type:ignore
        super().__init__("LocalStorage")
        self.path = settings["path"]  # type:ignore
        self.local = LocalFileSystem()

    @staticmethod
    def get_id() -> str:
        return "localstorage|ded5e7f0-f527-416d-8d4a-19f559bd6da5"

    @staticmethod
    def get_name() -> str:
        return "LocalStorage File Server"

    @staticmethod
    def get_description() -> str:
        return "Access data in your LocalStorage"

    @staticmethod
    def get_icon() -> str:
        # TO DO: Add an icon for local storage
        return "/icons/connector-icons/S3.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> Any:
        return self.local

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        logger.error(f"[LocalStorage] File hash not found for the metadata: {metadata}")
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        raise NotImplementedError

    def test_credentials(self, *args, **kwargs) -> bool:  # type:ignore
        """To test credentials for LocalStorage."""
        is_dir = False
        try:
            is_dir = bool(self.get_fsspec_fs().isdir("/"))
        except Exception as e:
            raise ConnectorError(
                f"Error while connecting to local storage: {str(e)}"
            ) from e
        if not is_dir:
            raise ConnectorError(
                "Unable to connect to local storage, "
                "please check the connection settings."
            )
        return True
