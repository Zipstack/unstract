import os
import unittest
from unittest.mock import MagicMock, patch

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.minio.exceptions import handle_s3fs_exception
from unstract.connectors.filesystems.minio.minio import MinioFS


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


class TestMinioFSCredentials(unittest.TestCase):
    """Tests for IRSA / IAM role support — credential omission logic."""

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_empty_key_secret_not_passed(self, mock_s3fs: MagicMock) -> None:
        """Empty key/secret should NOT be forwarded to S3FileSystem."""
        MinioFS({"key": "", "secret": "", "endpoint_url": ""})
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)
        self.assertNotIn("endpoint_url", kwargs)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_missing_key_secret_not_passed(self, mock_s3fs: MagicMock) -> None:
        """Missing key/secret (no keys in settings) should NOT be forwarded."""
        MinioFS({})
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)
        self.assertNotIn("endpoint_url", kwargs)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_real_credentials_passed_through(self, mock_s3fs: MagicMock) -> None:
        """Real credentials should be forwarded to S3FileSystem."""
        MinioFS(
            {
                "key": "fake-access-key-id",
                "secret": "fake-secret-access-key",
                "endpoint_url": "https://s3.amazonaws.com",
            }
        )
        _, kwargs = mock_s3fs.call_args
        self.assertEqual(kwargs["key"], "fake-access-key-id")
        self.assertEqual(kwargs["secret"], "fake-secret-access-key")
        self.assertEqual(kwargs["endpoint_url"], "https://s3.amazonaws.com")

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_endpoint_url_omitted_when_empty(self, mock_s3fs: MagicMock) -> None:
        """Empty endpoint_url should NOT be forwarded."""
        MinioFS(
            {
                "key": "fake-access-key-id",
                "secret": "fake-secret-access-key",
                "endpoint_url": "  ",
            }
        )
        _, kwargs = mock_s3fs.call_args
        self.assertIn("key", kwargs)
        self.assertNotIn("endpoint_url", kwargs)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_endpoint_url_passed_when_present(self, mock_s3fs: MagicMock) -> None:
        """Non-empty endpoint_url should be forwarded."""
        MinioFS(
            {
                "key": "fake-access-key-id",
                "secret": "fake-secret-access-key",
                "endpoint_url": "http://localhost:9000",
            }
        )
        _, kwargs = mock_s3fs.call_args
        self.assertEqual(kwargs["endpoint_url"], "http://localhost:9000")

    # --- Partial credentials tests ---

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_key_only_without_secret_uses_ambient(
        self, mock_s3fs: MagicMock
    ) -> None:
        """Key present but secret absent should fall back to ambient path."""
        MinioFS({"key": "fake-access-key-id", "secret": ""})
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_secret_only_without_key_uses_ambient(
        self, mock_s3fs: MagicMock
    ) -> None:
        """Secret present but key absent should fall back to ambient path."""
        MinioFS({"key": "", "secret": "fake-secret-access-key"})
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)

    # --- Whitespace-only credentials tests ---

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_whitespace_only_key_secret_uses_ambient(
        self, mock_s3fs: MagicMock
    ) -> None:
        """Whitespace-only key/secret should fall back to ambient path."""
        MinioFS({"key": "   ", "secret": "  \t  "})
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_whitespace_key_with_valid_secret_uses_ambient(
        self, mock_s3fs: MagicMock
    ) -> None:
        """Whitespace-only key with valid secret should fall back to ambient."""
        MinioFS(
            {"key": "  ", "secret": "fake-secret-access-key"}
        )
        _, kwargs = mock_s3fs.call_args
        self.assertNotIn("key", kwargs)
        self.assertNotIn("secret", kwargs)

    # --- _using_static_creds flag tests ---

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_using_static_creds_true_when_creds_present(
        self, mock_s3fs: MagicMock
    ) -> None:
        """_using_static_creds should be True when both key and secret are provided."""
        fs = MinioFS(
            {
                "key": "fake-access-key-id",
                "secret": "fake-secret-access-key",
            }
        )
        self.assertTrue(fs._using_static_creds)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_using_static_creds_false_when_creds_absent(
        self, mock_s3fs: MagicMock
    ) -> None:
        """_using_static_creds should be False when key/secret are empty."""
        fs = MinioFS({"key": "", "secret": ""})
        self.assertFalse(fs._using_static_creds)

    @patch(
        "unstract.connectors.filesystems.minio.minio.S3FileSystem",
        return_value=MagicMock(),
    )
    def test_using_static_creds_false_for_partial_creds(
        self, mock_s3fs: MagicMock
    ) -> None:
        """_using_static_creds should be False when only one of key/secret is set."""
        fs = MinioFS({"key": "fake-access-key-id", "secret": ""})
        self.assertFalse(fs._using_static_creds)


class TestHandleS3fsException(unittest.TestCase):
    """Tests for context-aware auth error messages in exceptions.py."""

    def test_invalid_key_static_creds_message(self) -> None:
        """Static creds mode: invalid key error references key/secret."""
        exc = Exception(
            "The AWS Access Key Id you provided does not exist in our records"
        )
        result = handle_s3fs_exception(exc, using_static_creds=True)
        self.assertIsInstance(result, ConnectorError)
        self.assertIn("Invalid Key", str(result))

    def test_invalid_secret_static_creds_message(self) -> None:
        """Static creds mode: signature mismatch references secret."""
        exc = Exception(
            "The request signature we calculated does not match "
            "the signature you provided"
        )
        result = handle_s3fs_exception(exc, using_static_creds=True)
        self.assertIsInstance(result, ConnectorError)
        self.assertIn("Invalid Secret", str(result))

    def test_invalid_key_ambient_creds_message(self) -> None:
        """Ambient creds mode: invalid key error references IAM/IRSA."""
        exc = Exception(
            "The AWS Access Key Id you provided does not exist in our records"
        )
        result = handle_s3fs_exception(exc, using_static_creds=False)
        self.assertIsInstance(result, ConnectorError)
        msg = str(result)
        self.assertIn("IAM role", msg)
        self.assertIn("IRSA", msg)
        self.assertNotIn("Invalid Key", msg)

    def test_invalid_secret_ambient_creds_message(self) -> None:
        """Ambient creds mode: signature mismatch references IAM/IRSA."""
        exc = Exception(
            "The request signature we calculated does not match "
            "the signature you provided"
        )
        result = handle_s3fs_exception(exc, using_static_creds=False)
        self.assertIsInstance(result, ConnectorError)
        msg = str(result)
        self.assertIn("IAM role", msg)
        self.assertIn("IRSA", msg)
        self.assertNotIn("Invalid Secret", msg)

    def test_common_error_unaffected_by_creds_mode(self) -> None:
        """Common errors (port, endpoint) should be the same regardless."""
        exc = Exception("[Errno 22] S3 API Requests must be made to API port")
        result_static = handle_s3fs_exception(exc, using_static_creds=True)
        result_ambient = handle_s3fs_exception(exc, using_static_creds=False)
        self.assertIn("invalid port", str(result_static))
        self.assertIn("invalid port", str(result_ambient))

    def test_unknown_error_passes_through(self) -> None:
        """Unknown errors should pass through the original message."""
        exc = Exception("Something completely unexpected happened")
        result = handle_s3fs_exception(exc, using_static_creds=True)
        self.assertIn("Something completely unexpected happened", str(result))

    def test_connector_error_passes_through(self) -> None:
        """ConnectorError should be returned as-is."""
        exc = ConnectorError(message="Already wrapped")
        result = handle_s3fs_exception(exc, using_static_creds=True)
        self.assertIs(result, exc)

    def test_default_using_static_creds_is_true(self) -> None:
        """Default value for using_static_creds should be True."""
        exc = Exception(
            "The AWS Access Key Id you provided does not exist in our records"
        )
        result = handle_s3fs_exception(exc)
        self.assertIn("Invalid Key", str(result))


# --- JSON schema validation tests ---


class TestMinioJsonSchema(unittest.TestCase):
    """Tests for the JSON schema configuration."""

    def test_schema_required_fields(self) -> None:
        """Schema should require connectorName, endpoint_url, region_name."""
        import json

        schema_str = MinioFS.get_json_schema()
        schema = json.loads(schema_str)
        required = schema["required"]
        self.assertIn("connectorName", required)
        self.assertIn("endpoint_url", required)
        self.assertIn("region_name", required)
        # key and secret should NOT be required (IRSA support)
        self.assertNotIn("key", required)
        self.assertNotIn("secret", required)

    def test_schema_has_default_for_endpoint_url(self) -> None:
        """endpoint_url should have a default value."""
        import json

        schema = json.loads(MinioFS.get_json_schema())
        self.assertIn("default", schema["properties"]["endpoint_url"])

    def test_schema_has_default_for_region_name(self) -> None:
        """region_name should have a default value."""
        import json

        schema = json.loads(MinioFS.get_json_schema())
        self.assertIn("default", schema["properties"]["region_name"])


if __name__ == "__main__":
    unittest.main()
