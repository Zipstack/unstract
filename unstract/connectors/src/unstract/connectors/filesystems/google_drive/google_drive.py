import json
import logging
import os
from typing import Any

from oauth2client.client import OAuth2Credentials
from pydrive2.auth import GoogleAuth
from pydrive2.fs import GDriveFileSystem
from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.google_drive.constants import GDriveConstants
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.connectors.gcs_helper import GCSHelper

logger = logging.getLogger(__name__)


class GoogleDriveFS(UnstractFileSystem):
    # Settings dict should contain the following:
    # {
    #   "access_token": "<access_token>",
    #   "refresh_token": "<refresh_token>",
    #   "token_expiry": "<token_expiry (calculated)>"
    # }
    def __init__(self, settings: dict[str, Any]):
        super().__init__("GoogleDrive")
        client_secrets = json.loads(
            GCSHelper().get_secret("google_drive_client_secret")
        )
        self.oauth2_credentials = {
            "client_id": client_secrets["web"]["client_id"],
            "client_secret": client_secrets["web"]["client_secret"],
            "token_uri": client_secrets["web"]["token_uri"],
            "user_agent": None,
            "invalid": False,
            "access_token": settings["access_token"],
            "refresh_token": settings["refresh_token"],
            GDriveConstants.TOKEN_EXPIRY: settings[GDriveConstants.TOKEN_EXPIRY],
        }
        gauth = GoogleAuth(
            settings_file=f"{os.path.dirname(__file__)}/static/settings.yaml",
            settings={"client_config": client_secrets["web"]},
        )
        gauth.credentials = OAuth2Credentials.from_json(
            json_data=json.dumps(self.oauth2_credentials)
        )
        self.drive = GDriveFileSystem(path="root", google_auth=gauth)

    @staticmethod
    def get_id() -> str:
        return "gdrive|3ac4b966-9136-4261-944a-bdbfc51cd21c"

    @staticmethod
    def get_name() -> str:
        return "Google Drive"

    @staticmethod
    def get_description() -> str:
        return "Access files in your Google Drive"

    @staticmethod
    def get_icon() -> str:
        return "https://storage.googleapis.com/pandora-static/connector-icons/Google%20Drive.png"  # noqa

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def requires_oauth() -> bool:
        return True

    @staticmethod
    def python_social_auth_backend() -> str:
        return "google-oauth2"

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_fsspec_fs(self) -> GDriveFileSystem:
        return self.drive

    def test_credentials(self) -> bool:
        """To test credentials for Google Drive."""
        try:
            self.get_fsspec_fs().isdir("root")
        except Exception as e:
            raise ConnectorError(str(e))
        return True
