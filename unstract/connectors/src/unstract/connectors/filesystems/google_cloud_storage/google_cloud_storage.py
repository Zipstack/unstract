import base64
import json
import logging
import os
from typing import Any

from gcsfs import GCSFileSystem

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

logger = logging.getLogger(__name__)


class GoogleCloudStorageFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        """Initializing gcs

        Args:
            settings (dict[str, Any]): A json dict containing json connection string
        Raises:
            ConnectorError: Error raised when connection initialization fails
        """
        super().__init__("GoogleCloudStorage")
        project_id = settings.get("project_id", "")
        json_credentials_str = settings.get("json_credentials", "{}")
        try:
            json_credentials = json.loads(json_credentials_str)
            self.gcs_fs = GCSFileSystem(
                token=json_credentials,
                project=project_id,
                cache_timeout=0,
                use_listings_cache=False,
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON credentials: {str(e)}")
            error_msg = (
                "Failed to connect to Google Cloud Storage. \n"
                "GCS credentials are not in proper JSON format. \n"
                f"Error: \n```\n{str(e)}\n```"
            )
            raise ConnectorError(error_msg) from e

    @staticmethod
    def get_id() -> str:
        return "google_cloud_storage|109bbe7b-8861-45eb-8841-7244e833d97b"

    @staticmethod
    def get_name() -> str:
        return "Google Cloud Storage"

    @staticmethod
    def get_description() -> str:
        return "Access files in your Google Cloud Storage"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/google_cloud_storage.png"

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

    def get_fsspec_fs(self) -> GCSFileSystem:
        return self.gcs_fs

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        # Extracts md5Hash (Base64) for GCS
        file_hash = metadata.get("md5Hash")
        if file_hash:
            return base64.b64decode(file_hash).hex()
        logger.error(f"[GCS] File hash not found for the metadata: {metadata}")
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        # Note: Here Metadata type seems to be always "file" even for directories
        return metadata.get("type") == "directory"

    def test_credentials(self) -> bool:
        """Test Google Cloud Storage credentials by accessing the root path info.

        Raises:
            ConnectorError: connector-error

        Returns:
            boolean: true if test-connection is successful
        """
        try:
            self.get_fsspec_fs().info("/")
        except Exception as e:
            error_msg = (
                "Error from Google Cloud Storage while testing connection. \n"
                f"Error: \n```\n{str(e)}\n```"
            )
            raise ConnectorError(error_msg) from e
        return True
