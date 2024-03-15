import logging
import os
from typing import Any

from dropbox.exceptions import DropboxException
from dropboxdrivefs import DropboxDriveFileSystem

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import (
    UnstractFileSystem,
)

from .exceptions import handle_dropbox_exception

logger = logging.getLogger(__name__)


class DropboxFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Dropbox")
        self.dropbox_fs = DropboxDriveFileSystem(token=settings["token"])
        self.path = "///"

    @staticmethod
    def get_id() -> str:
        return "dropbox|db6bf4a6-f892-4d25-8652-2bf251946134"

    @staticmethod
    def get_name() -> str:
        return "Dropbox"

    @staticmethod
    def get_description() -> str:
        return "Access files in your Dropbox storage"

    @staticmethod
    def get_icon() -> str:
        # TODO: Add an icon to GCS and serve it
        return (
            "https://storage.googleapis.com"
            "/pandora-static/connector-icons/Dropbox.png"
        )

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

    def get_fsspec_fs(self) -> DropboxDriveFileSystem:
        return self.dropbox_fs

    def test_credentials(self) -> bool:
        """To test credentials for Dropbox."""
        try:
            # self.get_fsspec_fs().connect()
            self.get_fsspec_fs().ls("")
        except DropboxException as e:
            logger.error(f"Test creds failed: {e}")
            raise handle_dropbox_exception(e)
        except Exception as e:
            logger.error(f"Test creds failed: {e}")
            raise ConnectorError(str(e))
        return True
