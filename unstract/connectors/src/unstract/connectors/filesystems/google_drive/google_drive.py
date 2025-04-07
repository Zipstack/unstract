import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import google.api_core.exceptions as GoogleApiException
from oauth2client.client import OAuth2Credentials
from pydrive2.auth import GoogleAuth
from pydrive2.fs import GDriveFileSystem

from unstract.connectors.exceptions import ConnectorError, FSAccessDeniedError
from unstract.connectors.filesystems.google_drive.constants import GDriveConstants
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.connectors.gcs_helper import GCSHelper

logging.getLogger("gdrive").setLevel(logging.ERROR)
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
        try:
            self.client_secrets = json.loads(
                GCSHelper().get_secret("google_drive_client_secret")
            )
        except GoogleApiException.PermissionDenied as e:
            user_message = "Permission denied. Please check your credentials. "
            raise FSAccessDeniedError(
                user_message,
                treat_as_user_message=True,
            ) from e
        self.oauth2_credentials = {
            "client_id": self.client_secrets["web"]["client_id"],
            "client_secret": self.client_secrets["web"]["client_secret"],
            "token_uri": self.client_secrets["web"]["token_uri"],
            "user_agent": None,
            "invalid": False,
            "access_token": settings["access_token"],
            "refresh_token": settings["refresh_token"],
            GDriveConstants.TOKEN_EXPIRY: settings[GDriveConstants.TOKEN_EXPIRY],
        }
        gauth = GoogleAuth(
            settings_file=f"{os.path.dirname(__file__)}/static/settings.yaml",
            settings={"client_config": self.client_secrets["web"]},
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
        return "/icons/connector-icons/Google%20Drive.png"

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

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> Optional[str]:
        """
        Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        logger.error(f"[Google Drive] File hash not found for the metadata: {metadata}")
        return None

    def test_credentials(self) -> bool:
        """To test credentials for Google Drive."""
        is_dir = False
        try:
            is_dir = bool(self.get_fsspec_fs().isdir("root"))
        except Exception as e:
            raise ConnectorError(
                f"Error from Google Drive while testing connection: {str(e)}"
            ) from e
        if not is_dir:
            raise ConnectorError(
                "Unable to connect to Google Drive, "
                "please check the connection settings."
            )
        return True

    @staticmethod
    def get_connector_root_dir(input_dir: str, **kwargs: Any) -> str:
        """Get roor dir of gdrive."""
        root_path = kwargs.get("root_path")
        if root_path is None:
            raise ValueError("root_path is required to get root_dir for Google Drive")
        input_dir = str(Path(root_path, input_dir.lstrip("/")))
        return f"{input_dir.strip('/')}/"

    # TODO: This should be removed later once the root casue is fixed.
    # This is a bandaid fix to avoid duplicate file upload in google drive.
    # GDrive allows multiple files with same name in a single folder which is
    # causing file duplication.
    # Below logic removes the file if already exists to avoid duplication.
    # Since other conenctor behaviour is to replace file sif exists
    # the deletion lgoci should be okay here.
    def upload_file_to_storage(self, source_path: str, destination_path: str) -> None:
        """Method to upload filepath from tool to destination connector directory.
        If a file already exists at the destination path, it will be deleted first.

        Args:
            source_path (str): local path of file to be uploaded, coming from tool
            destination_path (str): target path in the storage where the file will be
            uploaded
        """
        normalized_path = os.path.normpath(destination_path)
        destination_connector_fs = self.get_fsspec_fs()

        # Check if file exists and delete it
        if destination_connector_fs.exists(normalized_path):
            destination_connector_fs.delete(normalized_path)

        # Call parent class's upload method
        super().upload_file_to_storage(source_path, destination_path)
