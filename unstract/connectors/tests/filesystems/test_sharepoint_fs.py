"""Tests for SharePoint/OneDrive filesystem connector."""

import logging
import os
import unittest
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TestSharePointFSUnit(unittest.TestCase):
    """Unit tests for SharePointFS (no real credentials required)."""

    def setUp(self):
        """Set up test fixtures from environment variables."""
        self.test_settings = {
            "site_url": os.getenv(
                "SHAREPOINT_SITE_URL", "https://contoso.sharepoint.com/sites/testsite"
            ),
            "tenant_id": os.getenv("SHAREPOINT_TENANT_ID", "test-tenant-id"),
            "client_id": os.getenv("SHAREPOINT_CLIENT_ID", "test-client-id"),
            "client_secret": os.getenv(
                "SHAREPOINT_CLIENT_SECRET", "test-client-secret"
            ),
            "drive_id": os.getenv("SHAREPOINT_DRIVE_ID", ""),
        }

    def test_connector_metadata(self):
        """Test connector static metadata."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        self.assertEqual(
            SharePointFS.get_id(),
            "sharepoint|c8f4a9e2-7b3d-4e5f-a1c6-9d8e7f6b5a4c",
        )
        self.assertEqual(SharePointFS.get_name(), "SharePoint / OneDrive")
        self.assertIn("SharePoint", SharePointFS.get_description())
        self.assertTrue(SharePointFS.can_read())
        self.assertTrue(SharePointFS.can_write())
        self.assertTrue(SharePointFS.requires_oauth())  # Now supports OAuth button
        self.assertEqual(
            SharePointFS.python_social_auth_backend(),
            "azuread-tenant-oauth2",
        )

    def test_json_schema_exists(self):
        """Test that JSON schema file exists and is valid."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        schema = SharePointFS.get_json_schema()
        self.assertIsInstance(schema, str)
        self.assertIn("SharePoint", schema)
        self.assertIn("tenant_id", schema)
        self.assertIn("client_id", schema)
        self.assertIn("site_url", schema)

    def test_icon_path(self):
        """Test that icon path is correct."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        icon = SharePointFS.get_icon()
        self.assertEqual(icon, "/icons/connector-icons/SharePoint.png")

    def test_connector_initialization(self):
        """Test connector can be initialized with settings."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        connector = SharePointFS(settings=self.test_settings)
        self.assertIsNotNone(connector)
        self.assertEqual(connector._site_url, self.test_settings["site_url"])
        self.assertEqual(connector._tenant_id, self.test_settings["tenant_id"])
        self.assertEqual(connector._client_id, self.test_settings["client_id"])

    def test_connector_initialization_oauth(self):
        """Test connector initialization with OAuth tokens."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        oauth_settings = {
            "site_url": "https://contoso.sharepoint.com/sites/testsite",
            "tenant_id": "test-tenant-id",
            "client_id": "test-client-id",
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        }
        connector = SharePointFS(settings=oauth_settings)
        self.assertIsNotNone(connector)
        self.assertEqual(connector._access_token, "test-access-token")

    def test_connector_initialization_personal(self):
        """Test connector initialization for OneDrive Personal."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        personal_settings = {
            "client_id": "test-client-id",
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",  # Required for OAuth
            "is_personal": True,
        }
        connector = SharePointFS(settings=personal_settings)
        self.assertIsNotNone(connector)
        self.assertTrue(connector._is_personal)
        self.assertEqual(connector._access_token, "test-access-token")

    def test_connector_initialization_missing_auth(self):
        """Test connector raises error when no authentication method is provided."""
        from unstract.connectors.exceptions import ConnectorError
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        # No OAuth tokens and no client credentials
        invalid_settings = {
            "site_url": "https://contoso.sharepoint.com/sites/testsite",
            "is_personal": False,
        }
        with self.assertRaises(ConnectorError) as context:
            SharePointFS(settings=invalid_settings)
        self.assertIn("requires authentication", str(context.exception))

    def test_json_schema_has_is_personal(self):
        """Test that JSON schema includes is_personal field."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        schema = SharePointFS.get_json_schema()
        self.assertIn("is_personal", schema)
        self.assertIn("Personal Account", schema)

    def test_json_schema_has_oneof_pattern(self):
        """Test that JSON schema uses dependencies/oneOf pattern for dual auth methods."""
        import json

        from unstract.connectors.filesystems.sharepoint import SharePointFS

        schema_str = SharePointFS.get_json_schema()
        schema = json.loads(schema_str)

        # Verify dependencies structure with auth_type
        self.assertIn("dependencies", schema)
        self.assertIn("auth_type", schema["dependencies"])

        # Verify oneOf with two auth methods
        auth_deps = schema["dependencies"]["auth_type"]
        self.assertIn("oneOf", auth_deps)
        self.assertEqual(len(auth_deps["oneOf"]), 2)

        # Verify OAuth option
        oauth_option = auth_deps["oneOf"][0]
        self.assertIn("properties", oauth_option)
        self.assertEqual(oauth_option["properties"]["auth_type"]["enum"], ["oauth"])

        # Verify Client Credentials option
        client_creds_option = auth_deps["oneOf"][1]
        self.assertEqual(
            client_creds_option["properties"]["auth_type"]["enum"], ["client_credentials"]
        )
        self.assertIn("client_id", client_creds_option["properties"])
        self.assertIn("client_secret", client_creds_option["properties"])
        self.assertIn("tenant_id", client_creds_option["properties"])

        # Verify main properties have site_url and drive_id
        self.assertIn("properties", schema)
        self.assertIn("site_url", schema["properties"])
        self.assertIn("drive_id", schema["properties"])
        self.assertIn("auth_type", schema["properties"])

    def test_is_dir_by_metadata(self):
        """Test directory detection from metadata."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        connector = SharePointFS(settings=self.test_settings)

        # Test directory
        dir_metadata = {"type": "directory", "name": "folder"}
        self.assertTrue(connector.is_dir_by_metadata(dir_metadata))

        # Test file
        file_metadata = {"type": "file", "name": "document.pdf"}
        self.assertFalse(connector.is_dir_by_metadata(file_metadata))

    def test_extract_metadata_file_hash(self):
        """Test file hash extraction from metadata."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        connector = SharePointFS(settings=self.test_settings)

        # Test with quickXorHash (preferred)
        metadata = {"quickXorHash": "abc123hash"}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "abc123hash")

        # Test with cTag
        metadata = {"cTag": "ctag123value"}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "ctag123value")

        # Test with eTag
        metadata = {"eTag": '"etag123",version'}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "etag123")

        # Test with id as fallback
        metadata = {"id": "item-id-123"}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "item-id-123")

        # Test with no hash
        metadata = {"name": "file.txt"}
        self.assertIsNone(connector.extract_metadata_file_hash(metadata))

    def test_extract_modified_date(self):
        """Test modified date extraction from metadata."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        connector = SharePointFS(settings=self.test_settings)

        # Test with ISO string (Z suffix)
        metadata = {"lastModifiedDateTime": "2024-01-15T10:30:00Z"}
        result = connector.extract_modified_date(metadata)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

        # Test with datetime object
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        metadata = {"lastModifiedDateTime": dt}
        result = connector.extract_modified_date(metadata)
        self.assertEqual(result, dt)

        # Test with no date
        metadata = {"name": "file.txt"}
        result = connector.extract_modified_date(metadata)
        self.assertIsNone(result)

    def test_get_connector_root_dir(self):
        """Test root directory path formatting."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        # Normal path
        result = SharePointFS.get_connector_root_dir("/Documents/Folder")
        self.assertEqual(result, "Documents/Folder/")

        # Path with trailing slash
        result = SharePointFS.get_connector_root_dir("/Documents/Folder/")
        self.assertEqual(result, "Documents/Folder/")

        # Empty path
        result = SharePointFS.get_connector_root_dir("")
        self.assertEqual(result, "")


class TestSharePointFSIntegration(unittest.TestCase):
    """Integration tests for SharePointFS (require real credentials)."""

    @unittest.skipUnless(
        os.environ.get("SHAREPOINT_CLIENT_SECRET"),
        "Integration test requires SHAREPOINT_* environment variables",
    )
    def test_write_file_to_folder(self):
        """Test creating a folder and writing a PDF file."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "site_url": os.environ.get("SHAREPOINT_SITE_URL", ""),
            "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID"),
            "client_id": os.environ.get("SHAREPOINT_CLIENT_ID"),
            "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET"),
            "user_email": os.environ.get("SHAREPOINT_USER_EMAIL"),
        }

        connector = SharePointFS(settings=settings)
        fs = connector.get_fsspec_fs()

        # Use simple folder name for easy verification
        folder_name = "test-unit"
        file_name = "sample.pdf"
        file_path = f"{folder_name}/{file_name}"

        # Create a simple PDF with one line of text
        pdf_content = b"this is test pdf"

        try:
            # Create folder (this will happen automatically when writing file)
            logger.info("Creating file: %s", file_path)
            fs.write_bytes(file_path, pdf_content)
            logger.info("Successfully wrote file to: %s", file_path)
            logger.info("Folder: %s", folder_name)
            logger.info("File: %s", file_name)
            logger.info(
                "Verify in browser: Look for folder 'test-unit' in your OneDrive/SharePoint"
            )

            # Verify file exists
            self.assertTrue(fs.exists(file_path))
            logger.info("Verified file exists")

        except Exception as e:
            self.fail(f"Failed to write file: {e}")

    @unittest.skipUnless(
        os.environ.get("SHAREPOINT_CLIENT_SECRET"),
        "Integration test requires SHAREPOINT_* environment variables",
    )
    def test_read_file_from_folder(self):
        """Test reading the PDF file from the folder."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "site_url": os.environ.get(
                "SHAREPOINT_SITE_URL", "https://contoso.sharepoint.com/sites/testsite"
            ),
            "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID"),
            "client_id": os.environ.get("SHAREPOINT_CLIENT_ID"),
            "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET"),
            "user_email": os.environ.get("SHAREPOINT_USER_EMAIL"),
        }

        connector = SharePointFS(settings=settings)
        fs = connector.get_fsspec_fs()

        # Use same folder/file name as write test
        folder_name = "test-unit"
        file_name = "sample.pdf"
        file_path = f"{folder_name}/{file_name}"

        try:
            # Read the file
            logger.info("Reading file: %s", file_path)
            content = fs.cat_file(file_path)

            # Verify content
            self.assertEqual(content, b"this is test pdf")
            logger.info("Successfully read file from: %s", file_path)
            logger.info("File size: %d bytes", len(content))
            logger.info("Content: %s", content.decode())

        except FileNotFoundError:
            self.skipTest(
                f"File not found: {file_path}. Run test_write_file_to_folder first."
            )
        except Exception as e:
            self.fail(f"Failed to read file: {e}")


if __name__ == "__main__":
    unittest.main()
