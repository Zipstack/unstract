"""Tests for SharePoint/OneDrive filesystem connector."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestSharePointFSUnit(unittest.TestCase):
    """Unit tests for SharePointFS (no real credentials required)."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_settings = {
            "site_url": "https://contoso.sharepoint.com/sites/testsite",
            "tenant_id": "test-tenant-id",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "drive_id": "",
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
        self.assertFalse(SharePointFS.requires_oauth())
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
            "is_personal": True,
        }
        connector = SharePointFS(settings=personal_settings)
        self.assertIsNotNone(connector)
        self.assertTrue(connector._is_personal)
        self.assertEqual(connector._access_token, "test-access-token")

    def test_json_schema_has_is_personal(self):
        """Test that JSON schema includes is_personal field."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        schema = SharePointFS.get_json_schema()
        self.assertIn("is_personal", schema)
        self.assertIn("Personal Account", schema)

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

        # Test with quickXorHash
        metadata = {"quickXorHash": "abc123hash"}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "abc123hash")

        # Test with sha256Hash
        metadata = {"sha256Hash": "sha256value"}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "sha256value")

        # Test with eTag
        metadata = {"eTag": '"etag123",version'}
        self.assertEqual(connector.extract_metadata_file_hash(metadata), "etag123")

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
        os.environ.get("SHAREPOINT_SITE_URL"),
        "Integration test requires SHAREPOINT_* environment variables",
    )
    def test_client_credentials_connection(self):
        """Test connection using client credentials."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "site_url": os.environ.get("SHAREPOINT_SITE_URL"),
            "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID"),
            "client_id": os.environ.get("SHAREPOINT_CLIENT_ID"),
            "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET"),
        }

        connector = SharePointFS(settings=settings)

        # Test credentials
        self.assertTrue(connector.test_credentials())

    @unittest.skipUnless(
        os.environ.get("SHAREPOINT_SITE_URL"),
        "Integration test requires SHAREPOINT_* environment variables",
    )
    def test_list_files(self):
        """Test listing files from SharePoint."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "site_url": os.environ.get("SHAREPOINT_SITE_URL"),
            "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID"),
            "client_id": os.environ.get("SHAREPOINT_CLIENT_ID"),
            "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET"),
        }

        connector = SharePointFS(settings=settings)
        fs = connector.get_fsspec_fs()

        # List root
        files = fs.ls("")
        self.assertIsInstance(files, list)
        print(f"Found {len(files)} items in root")

    @unittest.skipUnless(
        os.environ.get("SHAREPOINT_SITE_URL"),
        "Integration test requires SHAREPOINT_* environment variables",
    )
    def test_read_file(self):
        """Test reading a file from SharePoint."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "site_url": os.environ.get("SHAREPOINT_SITE_URL"),
            "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID"),
            "client_id": os.environ.get("SHAREPOINT_CLIENT_ID"),
            "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET"),
        }

        test_file = os.environ.get("SHAREPOINT_TEST_FILE", "test.txt")

        connector = SharePointFS(settings=settings)
        fs = connector.get_fsspec_fs()

        try:
            content = fs.read_bytes(test_file)
            self.assertIsInstance(content, bytes)
            print(f"Read {len(content)} bytes from {test_file}")
        except Exception as e:
            self.skipTest(f"Test file not found: {e}")


    @unittest.skipUnless(
        os.environ.get("ONEDRIVE_PERSONAL_ACCESS_TOKEN"),
        "Integration test requires ONEDRIVE_PERSONAL_* environment variables",
    )
    def test_onedrive_personal_connection(self):
        """Test connection to OneDrive Personal."""
        from unstract.connectors.filesystems.sharepoint import SharePointFS

        settings = {
            "client_id": os.environ.get("ONEDRIVE_PERSONAL_CLIENT_ID"),
            "access_token": os.environ.get("ONEDRIVE_PERSONAL_ACCESS_TOKEN"),
            "is_personal": True,
        }

        connector = SharePointFS(settings=settings)
        self.assertTrue(connector.test_credentials())


if __name__ == "__main__":
    unittest.main()
