"""
Filesystem Connector Template

Replace placeholders:
- {ClassName}: PascalCase class name (e.g., MinioFS, AzureBlobFS)
- {connector_name}: lowercase connector name (e.g., minio, azure_blob)
- {display_name}: Display name (e.g., "Minio", "Azure Blob Storage")
- {description}: Brief description
- {uuid}: Generated UUID (use uuid4())
- {icon_name}: Icon filename (e.g., "Minio.png")
- {fsspec_class}: fsspec filesystem class (e.g., S3FileSystem, AzureBlobFileSystem)
- {fsspec_module}: Module path for fsspec class (e.g., s3fs, adlfs)
"""

import os
import threading
from typing import Any

from fsspec import AbstractFileSystem

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem
from unstract.connectors.exceptions import ConnectorError


class {ClassName}(UnstractFileSystem):
    """
    {display_name} filesystem connector.

    {description}
    """

    def __init__(self, settings: dict[str, Any]):
        super().__init__("{display_name}")

        # Store settings - DO NOT initialize clients in __init__
        # (prevents gRPC issues with Celery fork)
        self._settings = settings

        # Authentication settings
        self.access_key = settings.get("access_key", "")
        self.secret_key = settings.get("secret_key", "")
        self.endpoint_url = settings.get("endpoint_url", "")
        self.bucket = settings.get("bucket", "")
        self.region = settings.get("region", "")

        # Lazy initialization
        self._fs = None
        self._fs_lock = threading.Lock()

    @staticmethod
    def get_id() -> str:
        return "{connector_name}|{uuid}"

    @staticmethod
    def get_name() -> str:
        return "{display_name}"

    @staticmethod
    def get_description() -> str:
        return "{description}"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/{icon_name}"

    @staticmethod
    def get_json_schema() -> str:
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "json_schema.json"
        )
        with open(schema_path, "r") as f:
            return f.read()

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    def get_fsspec_fs(self) -> AbstractFileSystem:
        """
        Return fsspec filesystem instance.

        Uses lazy initialization with thread safety for Celery compatibility.

        Returns:
            fsspec AbstractFileSystem instance
        """
        if self._fs is None:
            with self._fs_lock:
                if self._fs is None:
                    # Import here for fork safety
                    from {fsspec_module} import {fsspec_class}

                    try:
                        self._fs = {fsspec_class}(
                            key=self.access_key,
                            secret=self.secret_key,
                            endpoint_url=self.endpoint_url,
                            # Add more options as needed:
                            # client_kwargs={"region_name": self.region},
                        )
                    except Exception as e:
                        raise ConnectorError(
                            f"Failed to initialize filesystem: {str(e)}",
                            treat_as_user_message=True
                        ) from e

        return self._fs

    def test_credentials(self) -> bool:
        """
        Test filesystem credentials.

        Returns:
            True if connection successful

        Raises:
            ConnectorError: If connection fails
        """
        try:
            fs = self.get_fsspec_fs()
            # Try to list the bucket/root to verify access
            fs.ls(self.bucket or "/")
            return True
        except Exception as e:
            raise ConnectorError(
                f"Credential test failed: {str(e)}",
                treat_as_user_message=True
            ) from e

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """
        Extract unique file hash from fsspec metadata.

        Different storage systems use different keys for file hashes:
        - S3/Minio: ETag
        - Azure: content_md5
        - GCS: md5Hash

        Args:
            metadata: File metadata from fsspec

        Returns:
            File hash string or None
        """
        # Try common hash fields
        hash_fields = ["ETag", "etag", "md5Hash", "content_md5", "contentHash"]

        for field in hash_fields:
            if field in metadata:
                value = metadata[field]
                # Remove quotes from ETags
                if isinstance(value, str):
                    return value.strip('"')
                return str(value)

        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """
        Check if path is a directory from metadata.

        Args:
            metadata: File metadata from fsspec

        Returns:
            True if path is a directory
        """
        # Different storage systems indicate directories differently
        if metadata.get("type") == "directory":
            return True
        if metadata.get("StorageClass") == "DIRECTORY":
            return True
        if metadata.get("size") == 0 and metadata.get("name", "").endswith("/"):
            return True

        return False
