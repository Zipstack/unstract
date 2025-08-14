import logging
import os
from typing import Any

from s3fs.core import S3FileSystem

from unstract.connectors.filesystems.unstract_file_system import UnstractFileSystem

from .exceptions import handle_s3fs_exception

logger = logging.getLogger(__name__)


# Pure boto3 implementation for gevent compatibility
class Boto3S3FileSystem:
    """Pure boto3-based S3 filesystem implementation for gevent compatibility.

    This bypasses all async/aioboto issues by using only synchronous boto3 calls.
    """

    def __init__(
        self, key: str, secret: str, endpoint_url: str, client_kwargs: dict = None
    ):
        """Initialize with boto3 S3 client."""
        import boto3
        from botocore.config import Config

        # Create gevent-optimized config
        config = Config(
            max_pool_connections=50,
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
            tcp_keepalive=True,
            parameter_validation=False,
        )

        # Merge with any additional client_kwargs
        final_client_kwargs = client_kwargs.copy() if client_kwargs else {}
        final_client_kwargs["config"] = config

        # Create pure boto3 S3 client (no async)
        self.client = boto3.client(
            "s3",
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            endpoint_url=endpoint_url,
            **final_client_kwargs,
        )

        logger.debug("Created pure boto3 S3 client for gevent (no async)")

    def isdir(self, path: str) -> bool:
        """Check if path is a directory using pure boto3."""
        try:
            # Remove leading slash and ensure trailing slash for directory check
            path = path.strip("/")
            if not path.endswith("/"):
                path += "/"

            # Parse bucket and key
            parts = path.split("/", 1)
            bucket = parts[0]
            prefix = parts[1] if len(parts) > 1 else ""

            # Use list_objects_v2 to check if directory exists
            response = self.client.list_objects_v2(
                Bucket=bucket, Prefix=prefix, MaxKeys=1
            )

            # If we get any objects with this prefix, it's a directory
            return "Contents" in response and len(response["Contents"]) > 0

        except Exception as e:
            logger.debug(f"isdir check failed for {path}: {e}")
            return False

    def ls(self, path: str, detail: bool = True, **kwargs):
        """List directory contents using pure boto3."""
        try:
            # Remove leading slash
            path = path.strip("/")

            # Parse bucket and key
            if "/" in path:
                bucket, prefix = path.split("/", 1)
                if not prefix.endswith("/") and prefix:
                    prefix += "/"
            else:
                bucket = path
                prefix = ""

            # List objects
            response = self.client.list_objects_v2(
                Bucket=bucket, Prefix=prefix, Delimiter="/"
            )

            results = []

            # Add directories (CommonPrefixes)
            for prefix_info in response.get("CommonPrefixes", []):
                dir_path = f"{bucket}/{prefix_info['Prefix'].rstrip('/')}"
                if detail:
                    results.append({"name": dir_path, "type": "directory", "size": 0})
                else:
                    results.append(dir_path)

            # Add files (Contents)
            for obj in response.get("Contents", []):
                file_path = f"{bucket}/{obj['Key']}"
                if detail:
                    results.append(
                        {
                            "name": file_path,
                            "type": "file",
                            "size": obj["Size"],
                            "ETag": obj.get("ETag", "").strip('"'),
                        }
                    )
                else:
                    results.append(file_path)

            return results

        except Exception as e:
            logger.error(f"ls failed for {path}: {e}")
            return []

    def listdir(self, path: str, detail: bool = True, **kwargs):
        """List directory contents - alias for ls method."""
        # Always return detailed metadata as the code expects dict objects
        return self.ls(path, detail=True, **kwargs)

    def walk(self, path: str, maxdepth: int = None, **kwargs):
        """Walk directory tree using pure boto3."""
        try:
            # Simple walk implementation
            yield from self._walk_recursive(path, maxdepth, 0)
        except Exception as e:
            logger.error(f"walk failed for {path}: {e}")
            return

    def _walk_recursive(self, path: str, maxdepth: int, current_depth: int):
        """Recursive walk helper."""
        if maxdepth is not None and current_depth >= maxdepth:
            return

        # Get directory listing
        items = self.ls(path, detail=True)

        dirs = []
        files = []

        for item in items:
            if isinstance(item, dict):
                if item["type"] == "directory":
                    dirs.append(item["name"])
                else:
                    files.append(item["name"])

        yield path, dirs, files

        # Recurse into directories
        for dir_path in dirs:
            yield from self._walk_recursive(dir_path, maxdepth, current_depth + 1)

    def open(self, path: str, mode: str = "rb", **kwargs):
        """Open file using pure boto3."""
        import io

        try:
            # Parse bucket and key
            path = path.strip("/")
            bucket, key = path.split("/", 1)

            if "r" in mode:
                # Read mode - download object
                response = self.client.get_object(Bucket=bucket, Key=key)

                if "b" in mode:
                    # Binary mode - return BytesIO
                    return io.BytesIO(response["Body"].read())
                else:
                    # Text mode - return StringIO
                    content = response["Body"].read().decode("utf-8")
                    return io.StringIO(content)

            elif "w" in mode or "a" in mode:
                # Write or append mode - return a buffer that uploads on close
                return S3WriteBuffer(self.client, bucket, key, mode)

            else:
                raise ValueError(f"Unsupported file mode: {mode}")

        except Exception as e:
            logger.error(f"open failed for {path}: {e}")
            raise

    def info(self, path: str, **kwargs):
        """Get file info using pure boto3."""
        try:
            # Parse bucket and key
            path = path.strip("/")
            bucket, key = path.split("/", 1)

            response = self.client.head_object(Bucket=bucket, Key=key)

            return {
                "name": path,
                "size": response["ContentLength"],
                "type": "file",
                "ETag": response.get("ETag", "").strip('"'),
            }

        except Exception as e:
            logger.error(f"info failed for {path}: {e}")
            return None

    def exists(self, path: str, **kwargs) -> bool:
        """Check if file or directory exists using pure boto3."""
        try:
            # Parse bucket and key
            path = path.strip("/")

            if "/" not in path:
                # Just bucket name - check if bucket exists
                try:
                    self.client.head_bucket(Bucket=path)
                    return True
                except Exception:
                    return False

            bucket, key = path.split("/", 1)

            # Try to get object metadata
            try:
                self.client.head_object(Bucket=bucket, Key=key)
                return True
            except Exception:
                # Maybe it's a directory - check for objects with this prefix
                try:
                    if not key.endswith("/"):
                        key += "/"

                    response = self.client.list_objects_v2(
                        Bucket=bucket, Prefix=key, MaxKeys=1
                    )
                    return "Contents" in response and len(response["Contents"]) > 0
                except Exception:
                    return False

        except Exception as e:
            logger.debug(f"exists check failed for {path}: {e}")
            return False

    def rm(self, path: str, recursive: bool = False, **kwargs):
        """Remove file or directory using pure boto3."""
        try:
            # Parse bucket and key
            path = path.strip("/")

            if "/" not in path:
                # Trying to delete entire bucket - not supported
                logger.warning(f"Cannot delete entire bucket: {path}")
                return

            bucket, key = path.split("/", 1)

            if recursive:
                # Delete all objects with this prefix
                if not key.endswith("/"):
                    key += "/"

                # List all objects with this prefix
                paginator = self.client.get_paginator("list_objects_v2")
                objects_to_delete = []

                for page in paginator.paginate(Bucket=bucket, Prefix=key):
                    for obj in page.get("Contents", []):
                        objects_to_delete.append({"Key": obj["Key"]})

                        # Delete in batches of 1000 (S3 limit)
                        if len(objects_to_delete) >= 1000:
                            self.client.delete_objects(
                                Bucket=bucket, Delete={"Objects": objects_to_delete}
                            )
                            objects_to_delete = []

                # Delete remaining objects
                if objects_to_delete:
                    self.client.delete_objects(
                        Bucket=bucket, Delete={"Objects": objects_to_delete}
                    )

            else:
                # Delete single object
                self.client.delete_object(Bucket=bucket, Key=key)

        except Exception as e:
            logger.error(f"rm failed for {path}: {e}")
            # Don't raise - cleanup failures shouldn't break the pipeline

    def glob(self, path: str, **kwargs):
        """Glob pattern matching using pure boto3."""
        try:
            # Simple glob implementation - for now just list all files
            # More sophisticated pattern matching could be added later
            import fnmatch

            # Extract bucket and pattern
            path = path.strip("/")
            if "/" in path:
                bucket, pattern = path.split("/", 1)
            else:
                bucket = path
                pattern = "*"

            # List all objects in bucket
            results = []
            paginator = self.client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents", []):
                    file_path = f"{bucket}/{obj['Key']}"
                    # Simple pattern matching
                    if fnmatch.fnmatch(obj["Key"], pattern):
                        results.append(file_path)

            return results

        except Exception as e:
            logger.error(f"glob failed for {path}: {e}")
            return []


class S3WriteBuffer:
    """Buffer for writing files to S3 using pure boto3."""

    def __init__(self, client, bucket: str, key: str, mode: str):
        import io

        self.client = client
        self.bucket = bucket
        self.key = key
        self.mode = mode
        self.buffer = io.BytesIO() if "b" in mode else io.StringIO()
        self.closed = False

        # For append mode, read existing content first
        if "a" in mode:
            try:
                existing_data = self.client.get_object(Bucket=bucket, Key=key)
                if "b" in mode:
                    # Binary append
                    self.buffer.write(existing_data["Body"].read())
                else:
                    # Text append
                    content = existing_data["Body"].read().decode("utf-8")
                    self.buffer.write(content)
            except Exception:
                # File doesn't exist yet, that's fine for append mode
                pass

    def write(self, data):
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self.buffer.write(data)

    def read(self, size=-1):
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self.buffer.read(size)

    def close(self):
        if not self.closed:
            # Upload buffer content to S3
            self.buffer.seek(0)
            if "b" in self.mode:
                content = self.buffer.getvalue()
            else:
                content = self.buffer.getvalue().encode("utf-8")

            self.client.put_object(Bucket=self.bucket, Key=self.key, Body=content)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MinioFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MinioFS/S3")
        key = settings.get("key", "")
        secret = settings.get("secret", "")
        endpoint_url = settings.get("endpoint_url", "")
        client_kwargs = {}
        if "region_name" in settings and settings["region_name"] != "":
            client_kwargs = {"region_name": settings["region_name"]}

        # Check if we're using gevent pool
        celery_pool = os.environ.get("CELERY_POOL", "unknown")

        if celery_pool == "gevent":
            # Use pure boto3 implementation to avoid async/gevent conflicts
            self.s3 = Boto3S3FileSystem(
                key=key,
                secret=secret,
                endpoint_url=endpoint_url,
                client_kwargs=client_kwargs,
            )
            logger.info(
                f"MinioFS: Using pure boto3 implementation for gevent - CELERY_POOL={celery_pool}"
            )
        else:
            # Standard S3FS configuration for other pools
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

    def get_fsspec_fs(self) -> S3FileSystem:
        """Get the fsspec filesystem instance (S3FileSystem or Boto3S3FileSystem)."""
        return self.s3

    def test_credentials(self) -> bool:
        """To test credentials for Minio."""
        try:
            self.get_fsspec_fs().ls("")
        except Exception as e:
            raise handle_s3fs_exception(e) from e
        return True
