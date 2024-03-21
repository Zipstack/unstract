import logging
import os
from typing import Any, Optional

from fsspec.implementations.local import LocalFileSystem
from unstract.connectors.filesystems.unstract_file_system import (
    UnstractFileSystem,
)

logger = logging.getLogger(__name__)


class LocalStorageFS(UnstractFileSystem):
    def __init__(self, settings: Optional[dict] = None):  # type:ignore
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

    def test_credentials(self, *args, **kwargs) -> bool:  # type:ignore
        """To test credentials for LocalStorage."""
        try:
            self.get_fsspec_fs().isdir("/")
        except Exception as e:
            logger.error(f"Test creds failed: {e}")
            return False
        return True
