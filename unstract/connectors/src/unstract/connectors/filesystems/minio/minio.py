import logging
import os
from typing import Any

from s3fs.core import S3FileSystem
from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.unstract_file_system import (
    UnstractFileSystem,
)

logger = logging.getLogger(__name__)


class MinioFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MinioFS/S3")
        key = settings["key"]
        secret = settings["secret"]
        endpoint_url = settings["endpoint_url"]
        self.bucket = settings["bucket"]
        self.path = settings["path"]
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
        return "MinioFS/S3"

    @staticmethod
    def get_description() -> str:
        return "All MinioFS compatible, including AWS S3"

    @staticmethod
    def get_icon() -> str:
        return (
            "/icons/connector-icons/S3.png"
        )

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

    def get_fsspec_fs(self) -> S3FileSystem:
        return self.s3

    def test_credentials(self) -> bool:
        """To test credentials for Minio."""
        try:
            self.get_fsspec_fs().isdir(f"{self.bucket}")
        except Exception as e:
            raise ConnectorError(str(e))
        return True
