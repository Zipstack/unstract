import os

from s3fs.core import S3FileSystem

from unstract.connectors.filesystems.minio.minio import MinioFS


class UnstractCloudStorage(MinioFS):
    """Free storage for users.

    Implemented with Google Cloud Storage through Minio.
    """

    # UCS credentials always have full access to UCS buckets, so skip the
    # per-bucket access probe that MinioFS runs on its fsspec filesystem.
    # The probe adds latency and could hide a bucket on a transient S3 error.
    _FS_CLASS = S3FileSystem

    @staticmethod
    def get_id() -> str:
        return "pcs|b8cd25cd-4452-4d54-bd5e-e7d71459b702"

    @staticmethod
    def get_name() -> str:
        return "Unstract Cloud Storage"

    @staticmethod
    def get_description() -> str:
        return "Store and retrieve data on Unstract Cloud Storage"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Unstract%20Storage.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema
