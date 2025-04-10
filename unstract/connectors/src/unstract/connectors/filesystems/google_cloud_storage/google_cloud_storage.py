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
        super().__init__("GoogleCloudStorage")
        self.bucket = settings.get("bucket", "")
        project_id = settings.get("project_id", "")
        json_credentials = json.loads(settings.get("json_credentials", "{}"))
        self.gcs_fs = GCSFileSystem(token=json_credentials, project=project_id)

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

    def test_credentials(self) -> bool:
        """To test credentials for Google Cloud Storage."""
        try:
            is_dir = bool(self.get_fsspec_fs().isdir(self.bucket))
            if not is_dir:
                raise RuntimeError("Could not access root directory.")
        except Exception as e:
            raise ConnectorError(
                f"Error from Google Cloud Storage while testing connection: {str(e)}"
            ) from e
        return True
