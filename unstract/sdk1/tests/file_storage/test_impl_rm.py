"""Tests for FileStorage.rm and the MissingContentMD5 fallback path.

Regression coverage for UN-3421: MinIO 2024-12-18 rejects bulk
``DeleteObjects`` with ``MissingContentMD5``; the fallback must route
through singular ``DeleteObject`` via ``s3fs.rm_file``, not through
``s3fs.rm`` (which still dispatches to ``_bulk_delete``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.exceptions import FileOperationError
from unstract.sdk1.file_storage.impl import FileStorage
from unstract.sdk1.file_storage.provider import FileStorageProvider


@pytest.fixture
def s3_file_storage() -> FileStorage:
    """FileStorage with a mocked fsspec filesystem stand-in for s3fs."""
    with patch(
        "unstract.sdk1.file_storage.impl.FileStorageHelper.file_storage_init"
    ) as mock_init:
        mock_fs = MagicMock()
        mock_init.return_value = mock_fs
        storage = FileStorage(provider=FileStorageProvider.MINIO)
    # Expose the mocked fs for per-test assertions/configuration.
    storage.fs = mock_fs  # type: ignore[assignment]
    return storage


def _missing_md5_error() -> Exception:
    return OSError(
        "[Errno 5] An error occurred (MissingContentMD5) when calling the "
        "DeleteObjects operation: Missing required header for this request: "
        "Content-Md5."
    )


class TestRmHappyPath:
    def test_bulk_delete_succeeds(self, s3_file_storage: FileStorage) -> None:
        """When ``fs.rm`` succeeds, fallback must NOT be invoked."""
        s3_file_storage.fs.rm.return_value = None

        s3_file_storage.rm("bucket/prefix/", recursive=True)

        s3_file_storage.fs.rm.assert_called_once_with(
            path="bucket/prefix/", recursive=True
        )
        s3_file_storage.fs.find.assert_not_called()
        s3_file_storage.fs.rm_file.assert_not_called()


class TestRmFallback:
    def test_missing_md5_triggers_individual_delete_via_rm_file(
        self, s3_file_storage: FileStorage
    ) -> None:
        """On MissingContentMD5, fallback uses singular ``rm_file``.

        Asserts we do NOT re-enter ``fs.rm`` (which would again hit the
        broken ``DeleteObjects`` API).
        """
        s3_file_storage.fs.rm.side_effect = _missing_md5_error()
        s3_file_storage.fs.find.return_value = [
            "bucket/prefix/a.txt",
            "bucket/prefix/b.txt",
            "bucket/prefix/nested/c.txt",
        ]

        s3_file_storage.rm("bucket/prefix/", recursive=True)

        # Bulk path was attempted exactly once.
        s3_file_storage.fs.rm.assert_called_once_with(
            path="bucket/prefix/", recursive=True
        )
        # Each file removed individually via singular DeleteObject.
        assert s3_file_storage.fs.rm_file.call_count == 3
        s3_file_storage.fs.rm_file.assert_any_call("bucket/prefix/a.txt")
        s3_file_storage.fs.rm_file.assert_any_call("bucket/prefix/b.txt")
        s3_file_storage.fs.rm_file.assert_any_call("bucket/prefix/nested/c.txt")
        # Directory prefix cleanup attempted.
        s3_file_storage.fs.rmdir.assert_called_once_with("bucket/prefix/")

    def test_fallback_continues_on_per_file_error(
        self, s3_file_storage: FileStorage
    ) -> None:
        """A single failing delete must not abort the rest of the cleanup."""
        s3_file_storage.fs.rm.side_effect = _missing_md5_error()
        s3_file_storage.fs.find.return_value = [
            "bucket/prefix/a.txt",
            "bucket/prefix/b.txt",
            "bucket/prefix/c.txt",
        ]
        s3_file_storage.fs.rm_file.side_effect = [None, RuntimeError("boom"), None]

        # Must not raise — best-effort semantics.
        s3_file_storage.rm("bucket/prefix/", recursive=True)

        assert s3_file_storage.fs.rm_file.call_count == 3
        s3_file_storage.fs.rmdir.assert_called_once_with("bucket/prefix/")

    def test_fallback_swallows_rmdir_error(self, s3_file_storage: FileStorage) -> None:
        """Missing directory prefix after cleanup is expected; don't raise."""
        s3_file_storage.fs.rm.side_effect = _missing_md5_error()
        s3_file_storage.fs.find.return_value = ["bucket/prefix/a.txt"]
        s3_file_storage.fs.rmdir.side_effect = FileNotFoundError("no prefix")

        # Must not raise.
        s3_file_storage.rm("bucket/prefix/", recursive=True)

        s3_file_storage.fs.rm_file.assert_called_once_with("bucket/prefix/a.txt")

    def test_non_md5_error_propagates(self, s3_file_storage: FileStorage) -> None:
        """Errors unrelated to MissingContentMD5 must bubble up."""
        s3_file_storage.fs.rm.side_effect = PermissionError("denied")

        with pytest.raises(FileOperationError):
            s3_file_storage.rm("bucket/prefix/", recursive=True)

        s3_file_storage.fs.rm_file.assert_not_called()

    def test_md5_error_without_recursive_propagates(
        self, s3_file_storage: FileStorage
    ) -> None:
        """Non-recursive calls must not silently fall back to directory walk."""
        s3_file_storage.fs.rm.side_effect = _missing_md5_error()

        with pytest.raises(FileOperationError):
            s3_file_storage.rm("bucket/prefix/file.txt", recursive=False)

        s3_file_storage.fs.find.assert_not_called()
        s3_file_storage.fs.rm_file.assert_not_called()


class TestFallbackDoesNotReenterBulkDelete:
    """End-to-end check that the fix eliminates the original bug.

    Simulates the s3fs boto3 layer: bulk ``DeleteObjects`` always fails with
    MissingContentMD5; singular ``DeleteObject`` succeeds. Before the fix,
    ``_rm_files_individually`` still ended up calling ``DeleteObjects`` via
    ``fs.rm(recursive=False)`` and crashed. After the fix, only singular
    ``DeleteObject`` is invoked.
    """

    def test_only_singular_delete_called(self, s3_file_storage: FileStorage) -> None:
        boto3_client = MagicMock()
        boto3_client.delete_objects.side_effect = _missing_md5_error()
        boto3_client.delete_object.return_value = {"ResponseMetadata": {}}

        # Top-level fs.rm routes to bulk DeleteObjects (broken on MinIO).
        s3_file_storage.fs.rm.side_effect = (
            lambda path, recursive: boto3_client.delete_objects(  # noqa: ARG005
                Bucket="bucket", Delete={"Objects": []}
            )
        )
        # rm_file routes to singular DeleteObject.
        s3_file_storage.fs.rm_file.side_effect = lambda p: boto3_client.delete_object(
            Bucket=p.split("/", 1)[0], Key=p.split("/", 1)[1]
        )
        s3_file_storage.fs.find.return_value = [
            "bucket/prefix/a.txt",
            "bucket/prefix/b.txt",
        ]

        s3_file_storage.rm("bucket/prefix/", recursive=True)

        # The broken bulk API was only attempted once (the initial call).
        assert boto3_client.delete_objects.call_count == 1
        # Fallback used singular DeleteObject for every file.
        assert boto3_client.delete_object.call_count == 2
        boto3_client.delete_object.assert_any_call(Bucket="bucket", Key="prefix/a.txt")
        boto3_client.delete_object.assert_any_call(Bucket="bucket", Key="prefix/b.txt")
