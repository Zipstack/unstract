import logging
import os
from typing import Any

from fsspec.implementations.sftp import SFTPFileSystem

from unstract.connectors.exceptions import ConnectorError
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
        # TODO: Use sshfs if above implementation doesn't work as expected
        # self.sftp_fs = SSHFileSystem(host=host, port=port, username=username, password=password)  # noqa: E501

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
