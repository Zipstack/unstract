import logging
import os
from typing import Any

from dropbox.exceptions import ApiError as DropBoxApiError
from dropbox.exceptions import DropboxException
from dropboxdrivefs import DropboxDriveFileSystem

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

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
        return "/icons/connector-icons/Dropbox.png"

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

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        file_hash = metadata.get("content_hash")
        if file_hash:
            return file_hash
        logger.error(
            f"[Dropbox] File hash (content_hash) not found for the metadata: {metadata}"
        )
        return None

    def test_credentials(self) -> bool:
        """To test credentials for Dropbox."""
        try:
            # self.get_fsspec_fs().connect()
            self.get_fsspec_fs().ls("")
        except DropboxException as e:
            raise handle_dropbox_exception(e) from e
        except Exception as e:
            raise ConnectorError(f"Error while connecting to Dropbox: {str(e)}") from e
        return True

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Get roor dir of zs dropbox."""
        return f"/{input_dir.strip('/')}"

    def create_dir_if_not_exists(self, input_dir: str) -> None:
        """Create roor dir of zs dropbox if not exists."""
        fs_fsspec = self.get_fsspec_fs()
        try:
            fs_fsspec.isdir(input_dir)
        except (
            DropBoxApiError
        ) as e:  # Dropbox returns this exception when directory is not present
            logger.debug(f"Path not found in dropbox {e.error}")
            fs_fsspec.mkdir(input_dir)
