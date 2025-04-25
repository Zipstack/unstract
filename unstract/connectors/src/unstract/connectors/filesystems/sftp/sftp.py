import logging
import os
from typing import Any

from fsspec.implementations.sftp import SFTPFileSystem

from unstract.connectors.exceptions import ConnectorError, PermissionDeniedError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class SettingsKey:
    HOST = "host"
    PORT = "port"
    USERNAME = "username"
    PASSWORD = "password"
    USER_DIRECTORY = "user_dir"


class SettingsDefault:
    PORT = 22


class SftpFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("SFTP")
        host = settings.get(SettingsKey.HOST)
        port = int(settings.get(SettingsKey.PORT, SettingsDefault.PORT))
        username = settings.get(SettingsKey.USERNAME)
        password = settings.get(SettingsKey.PASSWORD)
        self.directory = str(settings.get(SettingsKey.USER_DIRECTORY))

        self.sftp_fs = SFTPFileSystem(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    @staticmethod
    def get_id() -> str:
        return "sftp|e68fa828-2988-4cce-9e3d-4285348e3227"

    @staticmethod
    def get_name() -> str:
        return "SFTP/SSH"

    @staticmethod
    def get_description() -> str:
        return "Fetch data via SFTP/SSH"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/SFTP.png"

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> SFTPFileSystem:
        return self.sftp_fs

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        logger.error(f"[SFTP] File hash not found for the metadata: {metadata}")
        return None

    # TODO: Check if this method can be removed, and use it from parent class
    # (class UnstractFileSystem)
    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    # TODO: Check if this method can be removed, and use it from parent class
    # (class UnstractFileSystem)
    @staticmethod
    def requires_oauth() -> bool:
        return False

    # TODO: Check if this method can be removed, and use it from parent class
    # (class UnstractFileSystem)
    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    def test_credentials(self) -> bool:
        """To test credentials for SFTP."""
        is_dir = False
        user_dir = f"{self.directory.strip('/')}/"
        try:
            is_dir = bool(self.get_fsspec_fs().isdir(user_dir))
        except Exception as e:
            raise ConnectorError(
                f"Error while connecting to SFTP server: {str(e)}"
            ) from e
        if not is_dir:
            raise ConnectorError(
                "Unable to connect to SFTP server, "
                "please check the connection settings."
            )
        return True

    def create_dir_if_not_exists(self, input_dir: str) -> None:
        """Method to create dir of a connector if not exists.

        Args:
            input_dir (str): input directory of source connector
        """
        try:
            super().create_dir_if_not_exists(input_dir=input_dir)
        except PermissionError as e:
            self.raise_permission_error(input_dir=input_dir, error=e)

    def upload_file_to_storage(self, source_path: str, destination_path: str) -> None:
        """Method to upload filepath from tool to sftp connector directory.

        Args:
            source_path (str): local path of file to be uploaded, coming from tool
            destination_path (str): target path in the storage where the file will be
            uploaded
        """
        try:
            normalized_path = os.path.normpath(destination_path)
            super().upload_file_to_storage(
                source_path=source_path, destination_path=destination_path
            )
        except PermissionError as e:
            self.raise_permission_error(input_dir=normalized_path, error=e)

    def raise_permission_error(
        self, input_dir: str, error: PermissionError
    ) -> PermissionDeniedError:
        user_message = (
            "Please verify your SFTP credentials and ensure you "
            f" ensure you have the necessary permissions for the path '{input_dir}'. "
        )
        raise PermissionDeniedError(
            user_message,
            treat_as_user_message=True,
        ) from error
