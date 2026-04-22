import asyncio
import logging
import os
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from s3fs.core import S3FileSystem

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

from .exceptions import handle_s3fs_exception

logger = logging.getLogger(__name__)

# Cap concurrent per-bucket probes to avoid S3 503 SlowDown on large accounts.
_MAX_CONCURRENT_BUCKET_PROBES = 16


class _AccessFilteredS3FileSystem(S3FileSystem):  # type: ignore[misc]
    """S3FileSystem that lists only buckets the credentials can browse.

    `s3:ListAllMyBuckets` (account-level) returns every bucket in the
    account, which is wider than `s3:ListBucket` (per-bucket). We probe
    each bucket with a 1-key `list_objects_v2` and drop any that fail.
    """

    async def _lsbuckets(self, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh and "" in self.dircache:
            return self.dircache[""]  # type: ignore[no-any-return]
        buckets: list[dict[str, Any]] = await super()._lsbuckets(refresh=refresh)
        if not buckets:
            return buckets
        accessible = await self._filter_accessible_buckets(buckets)
        self.dircache[""] = accessible
        return accessible

    async def _filter_accessible_buckets(
        self, buckets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(_MAX_CONCURRENT_BUCKET_PROBES)

        async def _probe(name: str) -> bool:
            async with sem:
                return await self._is_bucket_accessible(name)

        results = await asyncio.gather(*(_probe(b["name"]) for b in buckets))
        return [b for b, ok in zip(buckets, results, strict=True) if ok]

    async def _is_bucket_accessible(self, name: str) -> bool:
        try:
            await self._call_s3("list_objects_v2", Bucket=name, MaxKeys=1)
            return True
        except Exception as exc:
            logger.debug("[S3/MinIO] Dropping inaccessible bucket '%s': %s", name, exc)
            return False


class MinioFS(UnstractFileSystem):
    # Override with plain S3FileSystem in a subclass when the credentials are
    # known to have full access to every bucket they list, so the per-bucket
    # access probe in _AccessFilteredS3FileSystem can be skipped.
    _FS_CLASS: type[S3FileSystem] = _AccessFilteredS3FileSystem

    def __init__(self, settings: dict[str, Any]):
        super().__init__("MinioFS/S3")
        key = (settings.get("key") or "").strip()
        secret = (settings.get("secret") or "").strip()
        endpoint_url = (settings.get("endpoint_url") or "").strip()
        client_kwargs = {}
        if "region_name" in settings and settings["region_name"] != "":
            client_kwargs = {"region_name": settings["region_name"]}

        creds: dict[str, str] = {}
        if key and secret:
            creds["key"] = key
            creds["secret"] = secret
        if endpoint_url:
            creds["endpoint_url"] = endpoint_url

        self.s3 = self._FS_CLASS(
            anon=False,
            use_listings_cache=False,
            default_fill_cache=False,
            default_cache_type="none",
            skip_instance_cache=True,
            client_kwargs=client_kwargs,
            **creds,
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
    def get_doc_url() -> str:
        return "https://docs.unstract.com/unstract/unstract_platform/connectors/filesystems/s3_minio_filesystem/"

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
        file_hash: str | None = metadata.get("ETag")
        if file_hash:
            file_hash = file_hash.strip('"')
            if "-" in file_hash:
                logger.warning(
                    "[S3/MinIO] Multipart upload detected. ETag may not be an "
                    "MD5 hash. Full metadata: %s",
                    metadata,
                )
                return None
            return file_hash
        logger.error("[MinIO] File hash not found for the metadata: %s", metadata)
        return None

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if the given path is a directory.

        Args:
            metadata (dict): Metadata dictionary obtained from fsspec or cloud API.

        Returns:
            bool: True if the path is a directory, False otherwise.
        """
        return metadata.get("type") == "directory"

    def _find_modified_date_value(self, metadata: dict[str, Any]) -> Any | None:
        """Find the modified date value from metadata using common keys."""
        for key in ["LastModified", "last_modified", "modified", "mtime"]:
            last_modified = metadata.get(key)
            if last_modified is not None:
                return last_modified

        logger.debug(
            "[S3/MinIO] No modified date found in metadata keys: %s",
            list(metadata.keys()),
        )
        return None

    def _normalize_datetime_to_utc(self, dt: datetime) -> datetime:
        """Normalize datetime object to timezone-aware UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _parse_string_datetime(
        self, date_str: str, metadata_keys: list[str]
    ) -> datetime | None:
        """Parse string datetime using multiple formats."""
        # Try ISO-8601 format first
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return self._normalize_datetime_to_utc(dt)
        except ValueError:
            pass

        # Fall back to RFC 1123 format
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(UTC)
        except (ValueError, TypeError):
            logger.warning(
                "[S3/MinIO] Failed to parse datetime '%s' from metadata keys: %s",
                date_str,
                metadata_keys,
            )
            return None

    def _parse_numeric_timestamp(self, timestamp: float) -> datetime | None:
        """Parse numeric epoch timestamp."""
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (ValueError, OSError):
            logger.warning("[S3/MinIO] Invalid epoch timestamp: %s", timestamp)
            return None

    def extract_modified_date(self, metadata: dict[str, Any]) -> datetime | None:
        """Extract the last modified date from S3/MinIO metadata.

        Accepts multiple date formats and ensures timezone-aware UTC datetime.

        Args:
            metadata: File metadata dictionary from fsspec

        Returns:
            timezone-aware UTC datetime object or None if not available
        """
        last_modified = self._find_modified_date_value(metadata)
        if last_modified is None:
            return None

        if isinstance(last_modified, datetime):
            return self._normalize_datetime_to_utc(last_modified)

        if isinstance(last_modified, str):
            return self._parse_string_datetime(last_modified, list(metadata.keys()))

        if isinstance(last_modified, (int, float)):
            return self._parse_numeric_timestamp(last_modified)

        logger.debug(
            "[S3/MinIO] Unsupported datetime type '%s' in metadata keys: %s",
            type(last_modified),
            list(metadata.keys()),
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
