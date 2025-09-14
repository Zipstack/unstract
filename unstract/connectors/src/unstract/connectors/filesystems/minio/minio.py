import logging
import os
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from s3fs.core import S3FileSystem

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

from .exceptions import handle_s3fs_exception

logger = logging.getLogger(__name__)


class MinioFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MinioFS/S3")
        key = settings.get("key", "")
        secret = settings.get("secret", "")
        endpoint_url = settings.get("endpoint_url", "")
        client_kwargs = {}
        if "region_name" in settings and settings["region_name"] != "":
            client_kwargs = {"region_name": settings["region_name"]}
        self.s3 = S3FileSystem(
            anon=False,
            key=key,
            secret=secret,
            default_fill_cache=False,
            default_cache_type="none",
            skip_instance_cache=True,
            endpoint_url=endpoint_url,
            client_kwargs=client_kwargs,
        )

    @staticmethod
    def get_id() -> str:
        return "minio|c799f6e3-2b57-434e-aaac-b5daa415da19"

    @staticmethod
    def get_name() -> str:
        return "S3/Minio"

    @staticmethod
    def get_description() -> str:
        return "Connect to AWS S3 and other compatible storage such as Minio."

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/S3.png"

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

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extracts a unique file hash from metadata.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec.

        Returns:
            Optional[str]: The file hash in hexadecimal format or None if not found.
        """
        # Extracts ETag for MinIO
        file_hash = metadata.get("ETag")
        if file_hash:
            file_hash = file_hash.strip('"')
            if "-" in file_hash:
                logger.warning(
                    f"[S3/MinIO] Multipart upload detected. ETag may not be an "
                    f"MD5 hash. Full metadata: {metadata}"
                )
                return None
            return file_hash
        logger.error(f"[MinIO] File hash not found for the metadata: {metadata}")
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
        """Extract the last modified date from S3/MinIO metadata.

        Accepts multiple date formats and ensures timezone-aware UTC datetime.

        Args:
            metadata: File metadata dictionary from fsspec

        Returns:
            timezone-aware UTC datetime object or None if not available
        """
        # Check common alternative keys for modified date
        for key in ["LastModified", "last_modified", "modified", "mtime"]:
            last_modified = metadata.get(key)
            if last_modified is not None:
                break
        else:
            logger.debug(
                f"[S3/MinIO] No modified date found in metadata keys: {list(metadata.keys())}"
            )
            return None

        if isinstance(last_modified, datetime):
            # Ensure datetime has timezone info
            if last_modified.tzinfo is None:
                # Naive datetime - assume UTC
                return last_modified.replace(tzinfo=UTC)
            else:
                # Convert to UTC
                return last_modified.astimezone(UTC)

        elif isinstance(last_modified, str):
            # Try ISO-8601 format first
            try:
                dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                # Ensure timezone awareness and convert to UTC
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                else:
                    return dt.astimezone(UTC)
            except ValueError:
                pass

            # Fall back to RFC 1123 format
            try:
                dt = parsedate_to_datetime(last_modified)
                # parsedate_to_datetime returns timezone-aware datetime in UTC
                return dt.astimezone(UTC)
            except (ValueError, TypeError):
                logger.warning(
                    f"[S3/MinIO] Failed to parse datetime '{last_modified}' from metadata keys: {list(metadata.keys())}"
                )
                return None

        elif isinstance(last_modified, (int, float)):
            # Numeric epoch timestamp
            try:
                return datetime.fromtimestamp(last_modified, tz=UTC)
            except (ValueError, OSError):
                logger.warning(f"[S3/MinIO] Invalid epoch timestamp: {last_modified}")
                return None

        logger.debug(
            f"[S3/MinIO] Unsupported datetime type '{type(last_modified)}' in metadata keys: {list(metadata.keys())}"
        )
        return None

    def get_fsspec_fs(self) -> S3FileSystem:
        return self.s3

    def test_credentials(self) -> bool:
        """To test credentials for Minio."""
        try:
            self.get_fsspec_fs().ls("")
        except Exception as e:
            raise handle_s3fs_exception(e) from e
        return True
