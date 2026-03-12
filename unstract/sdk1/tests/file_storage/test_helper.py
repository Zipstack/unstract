from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.file_storage.helper import FileStorageHelper
from unstract.sdk1.file_storage.provider import FileStorageProvider


@pytest.fixture
def mock_fsspec() -> Generator[MagicMock, None, None]:
    with patch("unstract.sdk1.file_storage.helper.fsspec") as mock:
        mock.filesystem.return_value = MagicMock()
        yield mock


class TestFileStorageHelperStripping:
    """Tests for empty string stripping in file_storage_init."""

    def test_s3_empty_strings_stripped(self, mock_fsspec: MagicMock) -> None:
        """Empty string credentials should be stripped for S3 provider."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.S3,
            key="",
            secret="  ",
            endpoint_url="https://s3.us-east-1.amazonaws.com/",
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert "key" not in kwargs
        assert "secret" not in kwargs
        assert kwargs["endpoint_url"] == "https://s3.us-east-1.amazonaws.com/"

    def test_minio_empty_strings_stripped(self, mock_fsspec: MagicMock) -> None:
        """Empty string credentials should be stripped for MINIO provider."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.MINIO,
            key="",
            secret="",
            endpoint_url="http://minio:9000",
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert "key" not in kwargs
        assert "secret" not in kwargs
        assert kwargs["endpoint_url"] == "http://minio:9000"

    def test_s3_nonempty_credentials_preserved(self, mock_fsspec: MagicMock) -> None:
        """Non-empty credentials should be passed through unchanged."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.S3,
            key="fake-access-key-id",
            secret="fake-secret-access-key",
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert kwargs["key"] == "fake-access-key-id"
        assert kwargs["secret"] == "fake-secret-access-key"

    def test_local_provider_unaffected(self, mock_fsspec: MagicMock) -> None:
        """LOCAL provider should not have stripping applied."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.LOCAL,
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        # LOCAL adds auto_mkdir, verify it's there
        assert kwargs["auto_mkdir"] is True

    def test_s3_protocol_used(self, mock_fsspec: MagicMock) -> None:
        """S3 provider should use 's3' protocol."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.S3,
            key="test-key",
            secret="test-secret",
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert kwargs["protocol"] == "s3"

    def test_minio_uses_s3_protocol(self, mock_fsspec: MagicMock) -> None:
        """MINIO provider should use 's3' protocol."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.MINIO,
            key="minio",
            secret="minio123",
            endpoint_url="http://minio:9000",
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert kwargs["protocol"] == "s3"

    def test_s3_non_string_values_preserved(self, mock_fsspec: MagicMock) -> None:
        """Non-string config values (booleans, ints) should not be stripped."""
        FileStorageHelper.file_storage_init(
            provider=FileStorageProvider.S3,
            key="test-key",
            secret="test-secret",
            anon=False,
            max_retries=3,
        )
        _, kwargs = mock_fsspec.filesystem.call_args
        assert kwargs["anon"] is False
        assert kwargs["max_retries"] == 3
