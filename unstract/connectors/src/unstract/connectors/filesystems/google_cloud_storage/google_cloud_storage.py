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
        # Primary check: Standard directory type
        if metadata.get("type") == "directory":
            return True

        # GCS-specific directory detection
        # In GCS, folders are represented as objects with specific characteristics
        object_name = metadata.get("name", "")
        size = metadata.get("size", 0)
        content_type = metadata.get("contentType", "")

        # GCS folder indicators:
        # 1. Object name ends with "/" (most reliable indicator)
        if object_name.endswith("/"):
            logger.debug(
                f"[GCS Directory Check] '{object_name}' identified as directory: name ends with '/'"
            )
            return True

        # 2. Zero-size object with text/plain content type (common for GCS folders)
        if size == 0 and content_type == "text/plain":
            logger.debug(
                f"[GCS Directory Check] '{object_name}' identified as directory: zero-size with text/plain content type"
            )
            return True

        # 3. Check for GCS-specific folder metadata
        # Some GCS folder objects have no contentType or have application/x-www-form-urlencoded
        if size == 0 and (
            not content_type
            or content_type
            in ["application/x-www-form-urlencoded", "binary/octet-stream"]
        ):
            # Additional validation: check if this looks like a folder path
            if "/" in object_name and not object_name.split("/")[-1]:  # Path ends with /
                logger.debug(
                    f"[GCS Directory Check] '{object_name}' identified as directory: zero-size folder-like object"
                )
                return True

        return False

    def debug_directory_access(
        self, directory_path: str, execution_id: str = ""
    ) -> dict[str, Any]:
        """GCS-specific directory access debugging.

        Args:
            directory_path: The directory path being accessed
            execution_id: Execution ID for log correlation

        Returns:
            dict[str, Any]: GCS-specific debug information
        """
        debug_info = {
            "connector_type": "google_cloud_storage",
            "directory_path": directory_path,
            "execution_id": execution_id,
            "debug_results": {},
        }

        try:
            # Extract bucket name for debugging
            bucket_name = (
                directory_path.split("/")[0] if "/" in directory_path else directory_path
            )

            logger.info(
                f"[exec:{execution_id}] [GCS Debug] Checking bucket: '{bucket_name}'"
            )
            debug_info["bucket_name"] = bucket_name

            gcs_fs = self.get_fsspec_fs()

            # Try to list the bucket to see if it exists and is accessible
            try:
                bucket_info = gcs_fs.info(bucket_name)
                logger.info(
                    f"[exec:{execution_id}] [GCS Debug] Bucket '{bucket_name}' exists with info: {bucket_info}"
                )
                debug_info["debug_results"]["bucket_exists"] = True
                debug_info["debug_results"]["bucket_info"] = str(bucket_info)
            except Exception as bucket_error:
                logger.warning(
                    f"[exec:{execution_id}] [GCS Debug] Cannot access bucket '{bucket_name}': {bucket_error}"
                )
                debug_info["debug_results"]["bucket_exists"] = False
                debug_info["debug_results"]["bucket_error"] = str(bucket_error)

            # Try to list contents of the resolved directory
            try:
                dir_contents = gcs_fs.ls(directory_path, detail=False)
                logger.info(
                    f"[exec:{execution_id}] [GCS Debug] Directory '{directory_path}' contents: {dir_contents[:10]}..."
                )  # First 10 items
                debug_info["debug_results"]["directory_accessible"] = True
                debug_info["debug_results"]["contents_count"] = len(dir_contents)
                debug_info["debug_results"]["sample_contents"] = dir_contents[
                    :5
                ]  # First 5 items
            except Exception as ls_error:
                logger.warning(
                    f"[exec:{execution_id}] [GCS Debug] Cannot list directory '{directory_path}': {ls_error}"
                )
                debug_info["debug_results"]["directory_accessible"] = False
                debug_info["debug_results"]["directory_error"] = str(ls_error)

        except Exception as debug_error:
            logger.warning(
                f"[exec:{execution_id}] [GCS Debug] Debug check failed: {debug_error}"
            )
            debug_info["debug_results"]["debug_failed"] = True
            debug_info["debug_results"]["debug_error"] = str(debug_error)

        return debug_info

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
