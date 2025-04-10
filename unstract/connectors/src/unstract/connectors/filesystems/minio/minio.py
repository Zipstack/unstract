import logging
import os
from typing import Any, Optional

from s3fs.core import S3FileSystem

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

from .exceptions import handle_s3fs_exception

logger = logging.getLogger(__name__)


class MinioFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MinioFS/S3")
        key = settings["key"]
        secret = settings["secret"]
        endpoint_url = settings["endpoint_url"]
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

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> Optional[str]:
        """
        Extracts a unique file hash from metadata.

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

    def get_fsspec_fs(self) -> S3FileSystem:
        return self.s3

    def test_credentials(self) -> bool:
        """To test credentials for Minio."""
        try:
            is_dir = bool(self.get_fsspec_fs().isdir(""))
            if not is_dir:
                raise RuntimeError("Could not access root directory.")
        except Exception as e:
            raise handle_s3fs_exception(e) from e
        return True
