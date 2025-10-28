import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

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

        # Store OAuth settings WITHOUT loading secrets from Secret Manager
        # Secret Manager uses gRPC which is NOT fork-safe!
        # Secrets will be loaded lazily in get_fsspec_fs() AFTER fork
        self._oauth_settings = {
            "access_token": settings["access_token"],
            "refresh_token": settings["refresh_token"],
            GDriveConstants.TOKEN_EXPIRY: settings[GDriveConstants.TOKEN_EXPIRY],
        }

        # Store settings file path for lazy initialization
        self._settings_file = f"{os.path.dirname(__file__)}/static/settings.yaml"

        # Lazy initialization - create client secrets and drive client only when needed (after fork)
        # This prevents SIGSEGV crashes in Celery ForkPoolWorker processes from gRPC calls
        self._client_secrets = None
        self._client_secrets_lock = threading.Lock()
        self._drive = None
        self._drive_lock = threading.Lock()

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

    def _get_client_secrets(self) -> dict[str, Any]:
        """Get client secrets with lazy initialization (fork-safe).

        This method loads secrets from Google Cloud Secret Manager on first access,
        ensuring the gRPC call happens AFTER Celery fork to avoid SIGSEGV crashes.

        Secret Manager uses gRPC which is not fork-safe. Loading secrets in __init__
        causes them to be loaded in the parent process before fork(), resulting in
        stale gRPC connections in child processes that trigger segmentation faults.

        Returns:
            dict: Client secrets configuration from Secret Manager

        Raises:
            FSAccessDeniedError: If permission denied accessing Secret Manager
        """
        if self._client_secrets is None:
            with self._client_secrets_lock:
                # Double-check pattern for thread safety
                if self._client_secrets is None:
                    logger.info(
                        "Loading Google Drive client secrets from Secret Manager "
                        "(lazy init after fork)"
                    )
                    try:
                        # This gRPC call happens AFTER fork in child process
                        self._client_secrets = json.loads(
                            GCSHelper().get_secret("google_drive_client_secret")
                        )
                        logger.info("Google Drive client secrets loaded successfully")
                    except GoogleApiException.PermissionDenied as e:
                        user_message = (
                            "Permission denied accessing Google Drive secrets. "
                            "Please check your credentials."
                        )
                        raise FSAccessDeniedError(
                            user_message,
                            treat_as_user_message=True,
                        ) from e

        return self._client_secrets

    def get_fsspec_fs(self) -> GDriveFileSystem:
        """Get GDrive filesystem with lazy initialization (fork-safe).

        This method creates the Google Drive API client on first access,
        ensuring it's created AFTER Celery fork to avoid SIGSEGV crashes.

        The lazy initialization pattern ensures that:
        1. Secret Manager gRPC calls happen in child process (after fork)
        2. Google Drive API client is created in child process (after fork)
        3. No stale gRPC connections exist from parent process

        Returns:
            GDriveFileSystem: The initialized Google Drive filesystem client
        """
        if self._drive is None:
            with self._drive_lock:
                # Double-check pattern for thread safety
                if self._drive is None:
                    logger.info("Initializing Google Drive client (lazy init after fork)")

                    # Load client secrets AFTER fork (gRPC call)
                    client_secrets = self._get_client_secrets()

                    # Build OAuth2 credentials with secrets loaded after fork
                    oauth2_credentials = {
                        "client_id": client_secrets["web"]["client_id"],
                        "client_secret": client_secrets["web"]["client_secret"],
                        "token_uri": client_secrets["web"]["token_uri"],
                        "user_agent": None,
                        "invalid": False,
                        **self._oauth_settings,  # Add access token, refresh token, expiry
                    }

                    # Create Google Auth and Drive filesystem
                    gauth = GoogleAuth(
                        settings_file=self._settings_file,
                        settings={"client_config": client_secrets["web"]},
                    )
                    gauth.credentials = OAuth2Credentials.from_json(
                        json_data=json.dumps(oauth2_credentials)
                    )
                    self._drive = GDriveFileSystem(path="root", google_auth=gauth)
                    logger.info("Google Drive client initialized successfully")

        return self._drive

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        # Extracts checksum for GDrive
        file_hash = metadata.get("checksum")
        if file_hash:
            return file_hash.lower()
        logger.error(f"[Google Drive] File hash not found for the metadata: {metadata}")
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        return metadata.get("type") == "directory"

    def extract_modified_date(self, metadata: dict[str, Any]) -> datetime | None:
        """Extract the last modified date from Google Drive metadata.

        Args:
            metadata: File metadata dictionary from fsspec

        Returns:
            datetime object or None if not available
        """
        modified_time = metadata.get("modifiedTime") or metadata.get("modified")
        if isinstance(modified_time, datetime):
            return modified_time
        elif isinstance(modified_time, str):
            try:
                return datetime.fromisoformat(modified_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"[Google Drive] Invalid datetime format: {modified_time}")
                return None
        logger.debug(f"[Google Drive] No modified date found in metadata: {metadata}")
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
