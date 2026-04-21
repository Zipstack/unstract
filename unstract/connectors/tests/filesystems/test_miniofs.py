import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from unstract.connectors.filesystems.minio.minio import (
    MinioFS,
    _AccessFilteredS3FileSystem,
)


class TestMinoFS(unittest.TestCase):
    @unittest.skip("")
    def test_s3(self) -> None:
        self.assertEqual(MinioFS.requires_oauth(), False)
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        s3 = MinioFS(
            {
                "key": access_key,
                "secret": secret_key,
                "path": "/",
                "endpoint_url": "https://s3.amazonaws.com",
            }
        )

        print(s3.get_fsspec_fs().ls("unstract-user-storage"))

    # @unittest.skip("Minio is not running")
    def test_minio(self) -> None:
        self.assertEqual(MinioFS.requires_oauth(), False)
        access_key = os.environ.get("MINIO_ACCESS_KEY_ID")
        secret_key = os.environ.get("MINIO_SECRET_ACCESS_KEY")
        print(access_key, secret_key)
        s3 = MinioFS(
            {
                "key": access_key,
                "secret": secret_key,
                "endpoint_url": "http://localhost:9000",
                "path": "/minio-test",
            }
        )

        print(s3.get_fsspec_fs().ls("/minio-test"))  # type:ignore


class TestAccessFilteredS3FileSystem(unittest.TestCase):
    """Unit tests for the bucket-access filter added for UN-3358."""

    def _make_fs(self) -> _AccessFilteredS3FileSystem:
        # Bypass __init__ to avoid touching the network / event loop.
        return _AccessFilteredS3FileSystem.__new__(_AccessFilteredS3FileSystem)

    def test_is_bucket_accessible_true_when_list_succeeds(self) -> None:
        fs = self._make_fs()
        with patch.object(fs, "_call_s3", new=AsyncMock(return_value={})):
            self.assertTrue(asyncio.run(fs._is_bucket_accessible("allowed")))

    def test_is_bucket_accessible_false_on_error(self) -> None:
        fs = self._make_fs()
        with patch.object(
            fs, "_call_s3", new=AsyncMock(side_effect=PermissionError("AccessDenied"))
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("denied")))

    def test_filter_accessible_buckets_drops_denied(self) -> None:
        fs = self._make_fs()
        buckets = [{"name": "allowed"}, {"name": "denied"}, {"name": "also-allowed"}]

        async def fake_call_s3(action: str, **kwargs: object) -> dict[str, object]:
            if kwargs.get("Bucket") == "denied":
                raise PermissionError("AccessDenied")
            return {}

        with patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call_s3)):
            result = asyncio.run(fs._filter_accessible_buckets(buckets))

        self.assertEqual([b["name"] for b in result], ["allowed", "also-allowed"])

    def test_lsbuckets_populates_dircache_with_filtered_list(self) -> None:
        fs = self._make_fs()
        fs.dircache = {}
        parent_buckets = [{"name": "allowed"}, {"name": "denied"}]

        async def fake_call_s3(action: str, **kwargs: object) -> dict[str, object]:
            if kwargs.get("Bucket") == "denied":
                raise PermissionError("AccessDenied")
            return {}

        with (
            patch(
                "unstract.connectors.filesystems.minio.minio."
                "S3FileSystem._lsbuckets",
                new=AsyncMock(return_value=parent_buckets),
            ),
            patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call_s3)),
        ):
            result = asyncio.run(fs._lsbuckets())

        self.assertEqual([b["name"] for b in result], ["allowed"])
        self.assertEqual([b["name"] for b in fs.dircache[""]], ["allowed"])


if __name__ == "__main__":
    unittest.main()
