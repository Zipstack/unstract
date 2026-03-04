"""
Tests for object storage integration.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from ...integrations.storage_client import RemoteStorageClient


class RemoteStorageClientTest(TestCase):
    """Test cases for RemoteStorageClient."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the FileStorage instance
        self.mock_fs_patcher = patch('lookup.integrations.storage_client.EnvHelper.get_storage')
        self.mock_get_storage = self.mock_fs_patcher.start()

        # Create mock file storage
        self.mock_fs = MagicMock()
        self.mock_get_storage.return_value = self.mock_fs

        # Initialize client
        self.client = RemoteStorageClient(base_path="test/lookup")
        self.project_id = uuid.uuid4()

    def tearDown(self):
        """Clean up patches."""
        self.mock_fs_patcher.stop()

    def test_upload_success(self):
        """Test successful file upload."""
        # Setup mock
        self.mock_fs.write.return_value = None  # Successful write

        # Test upload
        content = b"test content"
        path = "test/file.txt"

        result = self.client.upload(path, content)

        # Verify
        self.assertTrue(result)
        self.mock_fs.mkdir.assert_called_once()
        self.mock_fs.write.assert_called_once_with(
            path=path,
            mode="wb",
            data=content
        )

    def test_upload_failure(self):
        """Test file upload failure."""
        # Setup mock to raise exception
        self.mock_fs.write.side_effect = Exception("Storage error")

        # Test upload
        result = self.client.upload("test/file.txt", b"content")

        # Verify
        self.assertFalse(result)

    def test_download_success(self):
        """Test successful file download."""
        # Setup mock
        expected_content = b"test content"
        self.mock_fs.exists.return_value = True
        self.mock_fs.read.return_value = expected_content

        # Test download
        content = self.client.download("test/file.txt")

        # Verify
        self.assertEqual(content, expected_content)
        self.mock_fs.read.assert_called_once_with(
            path="test/file.txt",
            mode="rb"
        )

    def test_download_file_not_found(self):
        """Test download when file doesn't exist."""
        # Setup mock
        self.mock_fs.exists.return_value = False

        # Test download
        content = self.client.download("nonexistent.txt")

        # Verify
        self.assertIsNone(content)
        self.mock_fs.read.assert_not_called()

    def test_delete_success(self):
        """Test successful file deletion."""
        # Setup mock
        self.mock_fs.exists.return_value = True
        self.mock_fs.delete.return_value = None

        # Test delete
        result = self.client.delete("test/file.txt")

        # Verify
        self.assertTrue(result)
        self.mock_fs.delete.assert_called_once_with("test/file.txt")

    def test_delete_file_not_found(self):
        """Test delete when file doesn't exist."""
        # Setup mock
        self.mock_fs.exists.return_value = False

        # Test delete
        result = self.client.delete("nonexistent.txt")

        # Verify
        self.assertFalse(result)
        self.mock_fs.delete.assert_not_called()

    def test_exists_check(self):
        """Test file existence check."""
        # Test existing file
        self.mock_fs.exists.return_value = True
        self.assertTrue(self.client.exists("test/file.txt"))

        # Test non-existing file
        self.mock_fs.exists.return_value = False
        self.assertFalse(self.client.exists("nonexistent.txt"))

    def test_list_files(self):
        """Test listing files with prefix."""
        # Setup mock
        self.mock_fs.listdir.return_value = ["file1.txt", "file2.txt", ".hidden"]

        # Test list
        files = self.client.list_files("test/prefix")

        # Verify - hidden files should be excluded
        self.assertEqual(len(files), 2)
        self.assertIn("test/prefix/file1.txt", files)
        self.assertIn("test/prefix/file2.txt", files)
        self.assertNotIn("test/prefix/.hidden", files)

    def test_text_content_operations(self):
        """Test text content save and retrieve."""
        # Test save
        text = "Hello, World!"
        self.mock_fs.write.return_value = None

        result = self.client.save_text_content("test.txt", text)
        self.assertTrue(result)
        self.mock_fs.write.assert_called_with(
            path="test.txt",
            mode="wb",
            data=text.encode('utf-8')
        )

        # Test get
        self.mock_fs.exists.return_value = True
        self.mock_fs.read.return_value = text.encode('utf-8')

        retrieved = self.client.get_text_content("test.txt")
        self.assertEqual(retrieved, text)

    def test_upload_reference_data(self):
        """Test uploading reference data with metadata."""
        # Setup
        content = b"reference data"
        filename = "vendors.csv"
        metadata = {"source": "manual", "version": 1}

        # Mock JSON encoding for metadata
        import json
        expected_meta = json.dumps(metadata, indent=2)

        # Test upload
        path = self.client.upload_reference_data(
            self.project_id,
            filename,
            content,
            metadata
        )

        # Verify
        expected_path = f"test/lookup/{self.project_id}/{filename}"
        self.assertEqual(path, expected_path)

        # Check main file upload
        call_args = [call for call in self.mock_fs.write.call_args_list
                     if call[1]['path'] == expected_path]
        self.assertEqual(len(call_args), 1)

        # Check metadata upload
        meta_path = f"{expected_path}.meta.json"
        meta_calls = [call for call in self.mock_fs.write.call_args_list
                      if call[1]['path'] == meta_path]
        self.assertEqual(len(meta_calls), 1)

    def test_get_reference_data(self):
        """Test retrieving reference data."""
        # Setup
        expected_data = "reference content"
        self.mock_fs.exists.return_value = True
        self.mock_fs.read.return_value = expected_data.encode('utf-8')

        # Test
        data = self.client.get_reference_data(self.project_id, "data.txt")

        # Verify
        self.assertEqual(data, expected_data)
        expected_path = f"test/lookup/{self.project_id}/data.txt"
        self.mock_fs.read.assert_called_with(path=expected_path, mode="rb")

    def test_list_project_files(self):
        """Test listing all files for a project."""
        # Setup
        self.mock_fs.listdir.return_value = ["file1.csv", "file2.json"]

        # Test
        files = self.client.list_project_files(self.project_id)

        # Verify
        expected_prefix = f"test/lookup/{self.project_id}"
        self.assertEqual(len(files), 2)
        self.assertIn(f"{expected_prefix}/file1.csv", files)
        self.assertIn(f"{expected_prefix}/file2.json", files)

    def test_delete_project_data(self):
        """Test deleting all project data."""
        # Setup
        project_files = ["file1.csv", "file2.json"]
        self.mock_fs.listdir.return_value = project_files
        self.mock_fs.exists.return_value = True

        # Test
        result = self.client.delete_project_data(self.project_id)

        # Verify
        self.assertTrue(result)

        # Check files were deleted
        expected_prefix = f"test/lookup/{self.project_id}"
        for filename in project_files:
            expected_path = f"{expected_prefix}/{filename}"
            self.mock_fs.delete.assert_any_call(expected_path)

        # Check directory was removed
        self.mock_fs.rmdir.assert_called_once_with(expected_prefix)
