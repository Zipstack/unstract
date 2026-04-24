import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError
from s3fs.core import S3FileSystem
from s3fs.errors import translate_boto_error

from unstract.connectors.filesystems.minio.exceptions import s3_error_code
from unstract.connectors.filesystems.minio.minio import (
    MinioFS,
    _AccessFilteredS3FileSystem,
)
from unstract.connectors.filesystems.ucs.ucs import UnstractCloudStorage


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


def _translated_error(code: str) -> BaseException:
    """Mirror what s3fs `_call_s3` actually raises in production.

    s3fs routes every raise through `translate_boto_error`, which converts
    `ClientError` into `PermissionError` / `FileNotFoundError` / `OSError`
    with the original `ClientError` preserved as `__cause__`. Tests must
    raise the translated form or they won't exercise the real catch path.
    """
    ce = ClientError({"Error": {"Code": code, "Message": code}}, "ListObjectsV2")
    translated: BaseException = translate_boto_error(ce)
    return translated


class TestAccessFilteredS3FileSystem(unittest.TestCase):
    """Unit tests for the per-bucket access filter in _AccessFilteredS3FileSystem.

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
        # s3fs translates `AccessDenied` → `PermissionError`; the filter
        # must still drop the bucket by recovering the code from `__cause__`.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_translated_error("AccessDenied")),
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("denied")))

    def test_no_such_bucket_is_dropped(self) -> None:
        # Race: bucket deleted between `list_buckets` and probe → `NoSuchBucket`
        # (translated to `FileNotFoundError`). Drop it rather than surface.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_translated_error("NoSuchBucket")),
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("deleted")))

    def test_permanent_redirect_bucket_is_kept(self) -> None:
        # Fail-open: region mismatch keeps the bucket listed.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_translated_error("PermanentRedirect")),
        ):
            self.assertTrue(asyncio.run(fs._is_bucket_accessible("other-region")))

    def test_throttling_retries_then_fails_open(self) -> None:
        fs = self._make_fs()

        async def fake_call(_action: str, **_kwargs: object) -> dict[str, object]:
            raise _translated_error("SlowDown")

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
            raise _translated_error(codes.pop(0))

        with (
            patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call)),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            self.assertFalse(asyncio.run(fs._is_bucket_accessible("slow-then-denied")))

    def test_throttling_then_unknown_on_retry_propagates(self) -> None:
        # Unknown error on retry (e.g. credentials expire mid-probe) must NOT
        # be silently swallowed — it has to surface as a real failure.
        fs = self._make_fs()
        codes = ["SlowDown", "SomeWeirdUnknownCode"]

        async def fake_call(_action: str, **_kwargs: object) -> dict[str, object]:
            raise _translated_error(codes.pop(0))

        with (
            patch.object(fs, "_call_s3", new=AsyncMock(side_effect=fake_call)),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            with self.assertRaises(OSError):
                asyncio.run(fs._is_bucket_accessible("slow-then-mystery"))

    def test_unknown_error_propagates(self) -> None:
        # Unknown codes must NOT be silently hidden on first probe either.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_translated_error("SomeWeirdUnknownCode")),
        ):
            with self.assertRaises(OSError):
                asyncio.run(fs._is_bucket_accessible("mystery"))

    def test_request_time_too_skewed_propagates(self) -> None:
        # Clock skew is system-wide, not bucket-level; it must surface so
        # `handle_s3fs_exception` can show the clock-skew message.
        fs = self._make_fs()
        with patch.object(
            fs,
            "_call_s3",
            new=AsyncMock(side_effect=_translated_error("RequestTimeTooSkewed")),
        ):
            with self.assertRaises(PermissionError):
                asyncio.run(fs._is_bucket_accessible("any-bucket"))

    def test_lsbuckets_override_wires_to_filter(self) -> None:
        # Regression guard for s3fs signature drift on `_lsbuckets`/`_call_s3`.
        fs = self._make_fs()
        parent_buckets = [{"name": "allowed"}, {"name": "denied"}]

        async def fake_call(_action: str, **kwargs: object) -> dict[str, object]:
            if kwargs.get("Bucket") == "denied":
                raise _translated_error("AccessDenied")
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

    def test_ucs_opts_out_of_access_filter(self) -> None:
        # UCS credentials are expected to have full access, so the per-bucket
        # probe must be skipped. Guards against a future refactor dropping
        # the `_FS_CLASS = S3FileSystem` override in ucs.py.
        self.assertIs(UnstractCloudStorage._FS_CLASS, S3FileSystem)
        self.assertIsNot(UnstractCloudStorage._FS_CLASS, _AccessFilteredS3FileSystem)

    def test_error_code_walks_context_when_cause_absent(self) -> None:
        # Guards against future wrapper layers that use implicit exception
        # chaining (`raise X` inside an `except`). The original `ClientError`
        # lands on `__context__`, not `__cause__` — the helper must still
        # recover the disposition code or we silently propagate AccessDenied.
        client_exc = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "AccessDenied"}},
            "ListObjectsV2",
        )
        try:
            try:
                raise client_exc
            except ClientError:
                # Implicit chaining: no `from` clause, so ClientError lands
                # on __context__ of the OSError below.
                raise OSError("translated")  # noqa: B904
        except OSError as outer:
            self.assertEqual(s3_error_code(outer), "AccessDenied")


if __name__ == "__main__":
    unittest.main()
