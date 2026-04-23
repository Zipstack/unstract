import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError

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

        print(s3.get_fsspec_fs().ls("/minio-test"))


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "ListObjectsV2")


class TestAccessFilteredS3FileSystem(unittest.TestCase):
    """Unit tests for the bucket-access filter added in UN-3358.

    These tests don't need a live MinIO/S3. They bypass
    `_AccessFilteredS3FileSystem.__init__` and monkey-patch `_call_s3` /
    `S3FileSystem._lsbuckets` to exercise the override end-to-end. If s3fs
    renames or re-signatures either internal, these tests fail loudly in
    CI instead of silently reverting to the unfiltered parent behavior.
    """

    def _make_fs(self) -> _AccessFilteredS3FileSystem:
        # Bypass __init__ to avoid touching the network / event loop.
        return _AccessFilteredS3FileSystem.__new__(_AccessFilteredS3FileSystem)

    def test_accessible_bucket_is_kept(self) -> None:
        fs = self._make_fs()
        with patch.object(fs, "_call_s3", new=AsyncMock(return_value={})):
            self.assertTrue(asyncio.run(fs._is_bucket_accessible("allowed")))

    def test_access_denied_bucket_is_dropped(self) -> None:
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_client_error("AccessDenied")),
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("denied")))

    def test_permanent_redirect_bucket_is_kept(self) -> None:
        # Fail-open: region mismatch keeps the bucket listed.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_client_error("PermanentRedirect")),
        ):
            self.assertTrue(asyncio.run(fs._is_bucket_accessible("other-region")))

    def test_throttling_retries_then_fails_open(self) -> None:
        fs = self._make_fs()

        async def fake_call(_action: str, **_kwargs: object) -> dict[str, object]:
            raise _client_error("SlowDown")

        call = AsyncMock(side_effect=fake_call)
        with (
            patch.object(fs, "_call_s3", new=call),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            self.assertTrue(asyncio.run(fs._is_bucket_accessible("throttled")))
        self.assertEqual(call.await_count, 2)  # initial + one retry

    def test_throttling_then_denied_on_retry_is_dropped(self) -> None:
        fs = self._make_fs()
        codes = ["SlowDown", "AccessDenied"]

        async def fake_call(_action: str, **_kwargs: object) -> dict[str, object]:
            raise _client_error(codes.pop(0))

        with (
            patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call)),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("slow-then-denied")))

    def test_unknown_client_error_propagates(self) -> None:
        # Unknown codes must NOT be silently hidden.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_client_error("SomeWeirdUnknownCode")),
        ):
            with self.assertRaises(ClientError):
                asyncio.run(fs._is_bucket_accessible("mystery"))

    def test_lsbuckets_override_wires_to_filter(self) -> None:
        # Regression guard for s3fs signature drift on `_lsbuckets`/`_call_s3`.
        fs = self._make_fs()
        parent_buckets = [{"name": "allowed"}, {"name": "denied"}]

        async def fake_call(_action: str, **kwargs: object) -> dict[str, object]:
            if kwargs.get("Bucket") == "denied":
                raise _client_error("AccessDenied")
            return {}

        with (
            patch(
                "unstract.connectors.filesystems.minio.minio."
                "S3FileSystem._lsbuckets",
                new=AsyncMock(return_value=parent_buckets),
            ),
            patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call)),
        ):
            result = asyncio.run(fs._lsbuckets(refresh=True))
        self.assertEqual([b["name"] for b in result], ["allowed"])

    def test_default_fs_class_is_filtered(self) -> None:
        # MinioFS defaults to the access-filtered filesystem; subclasses can opt out.
        self.assertIs(MinioFS._FS_CLASS, _AccessFilteredS3FileSystem)


if __name__ == "__main__":
    unittest.main()
