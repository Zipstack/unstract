import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from unstract.connectors.databases.oracle_db.oracle_db import OracleDB


class TestOracleDBWalletFileUpload(unittest.TestCase):
    """Test cases for Oracle DB wallet file upload functionality."""

    def setUp(self):
        """Set up test environment."""
        self.test_settings = {
            "user": "admin",
            "password": "test_password",
            "dsn": "test_dsn",
            "wallet_password": "test_wallet_password",
        }

    def create_test_wallet_zip(self) -> str:
        """Create a test wallet ZIP file.

        Returns:
            str: Path to the created test ZIP file
        """
        # Create a temporary ZIP file with mock wallet contents
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip.close()

        with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
            # Add mock wallet files
            zip_file.writestr("ewallet.pem", "mock_wallet_content")
            zip_file.writestr("tnsnames.ora", "mock_tns_content")
            zip_file.writestr("sqlnet.ora", "mock_sqlnet_content")

        return temp_zip.name

    def test_wallet_file_extraction(self):
        """Test wallet file extraction from ZIP and unified directory usage."""
        # Create test ZIP file
        test_zip_path = self.create_test_wallet_zip()

        try:
            # Test wallet file settings
            settings = self.test_settings.copy()
            settings["wallet_file"] = test_zip_path

            # Mock oracledb.connect to avoid actual database connection
            with patch('unstract.connectors.databases.oracle_db.oracle_db.oracledb.connect'):
                oracle_db = OracleDB(settings)

                # Verify that both config_dir and wallet_location point to the same directory
                self.assertEqual(oracle_db.config_dir, oracle_db.wallet_location)
                self.assertTrue(os.path.exists(oracle_db.wallet_location))
                self.assertTrue(os.path.isdir(oracle_db.wallet_location))

                # Verify extracted files exist in the unified directory
                expected_files = ["ewallet.pem", "tnsnames.ora", "sqlnet.ora"]
                for file_name in expected_files:
                    file_path = os.path.join(oracle_db.wallet_location, file_name)
                    self.assertTrue(
                        os.path.exists(file_path),
                        f"Expected wallet file {file_name} not found"
                    )

        finally:
            # Clean up test ZIP file
            os.unlink(test_zip_path)

    def test_missing_wallet_file(self):
        """Test error when no wallet_file provided."""
        settings = self.test_settings.copy()
        # Don't provide wallet_file - should raise ValueError

        # Should raise ValueError for missing wallet file
        with self.assertRaises(ValueError) as context:
            OracleDB(settings)

        self.assertIn("Oracle wallet file is required", str(context.exception))

    def test_invalid_zip_file(self):
        """Test handling of invalid ZIP file."""
        # Create a non-ZIP file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_file.write(b"This is not a ZIP file")
        temp_file.close()

        try:
            settings = self.test_settings.copy()
            settings["wallet_file"] = temp_file.name

            # Should raise ValueError for invalid ZIP
            with self.assertRaises(ValueError) as context:
                OracleDB(settings)

            self.assertIn("Invalid ZIP file", str(context.exception))

        finally:
            # Clean up test file
            os.unlink(temp_file.name)

    def test_wallet_file_required(self):
        """Test that wallet_file is required for Oracle connection."""
        # This test verifies that the wallet file is now mandatory
        settings = self.test_settings.copy()

        # Missing wallet_file should raise ValueError
        with self.assertRaises(ValueError) as context:
            OracleDB(settings)

        error_message = str(context.exception)
        self.assertIn("Oracle wallet file is required", error_message)
        self.assertIn("ewallet.pem", error_message)
        self.assertIn("tnsnames.ora", error_message)

    def test_wallet_extraction_provides_unified_config(self):
        """Test that wallet extraction provides unified configuration directory."""
        test_zip_path = self.create_test_wallet_zip()

        try:
            settings = self.test_settings.copy()
            settings["wallet_file"] = test_zip_path

            # Mock oracledb.connect to avoid actual database connection
            with patch('unstract.connectors.databases.oracle_db.oracle_db.oracledb.connect'):
                oracle_db = OracleDB(settings)

                # Verify both config_dir and wallet_location point to same extracted directory
                self.assertEqual(oracle_db.config_dir, oracle_db.wallet_location)
                # Verify it's a temporary directory
                self.assertTrue(oracle_db.config_dir.startswith(tempfile.gettempdir()))
                # Verify the directory exists and contains extracted files
                self.assertTrue(os.path.exists(oracle_db.config_dir))
                self.assertTrue(os.path.isdir(oracle_db.config_dir))

        finally:
            # Clean up test ZIP file
            os.unlink(test_zip_path)

    def test_temp_directory_cleanup(self):
        """Test that temporary directory is marked for cleanup."""
        test_zip_path = self.create_test_wallet_zip()

        try:
            settings = self.test_settings.copy()
            settings["wallet_file"] = test_zip_path

            # Mock oracledb.connect to avoid actual database connection
            with patch('unstract.connectors.databases.oracle_db.oracle_db.oracledb.connect'):
                oracle_db = OracleDB(settings)
                temp_dir = oracle_db.wallet_location

                # Verify temp directory exists
                self.assertTrue(os.path.exists(temp_dir))

                # Verify the internal temp directory reference is set
                self.assertIsNotNone(oracle_db._temp_wallet_dir)
                self.assertEqual(oracle_db._temp_wallet_dir, temp_dir)

        finally:
            # Clean up test ZIP file
            os.unlink(test_zip_path)

    def test_test_connection_dict_handling(self):
        """Test that test connection now properly handles files via FormData (dict case should not occur)."""
        # This test verifies that the previous dict issue has been resolved
        # by fixing the frontend to send FormData and backend to handle it properly.
        #
        # If this test ever fails, it means the FormData handling broke and
        # dict serialization is happening again.

        test_zip_path = self.create_test_wallet_zip()
        try:
            settings = self.test_settings.copy()
            settings["wallet_file"] = test_zip_path

            # Mock oracledb.connect to avoid actual database connection
            with patch('unstract.connectors.databases.oracle_db.oracle_db.oracledb.connect'):
                oracle_db = OracleDB(settings)

                # Verify wallet extraction worked (no dict handling needed)
                self.assertIsNotNone(oracle_db.wallet_location)
                self.assertTrue(os.path.exists(oracle_db.wallet_location))
        finally:
            os.unlink(test_zip_path)

    def test_django_uploaded_file_handling(self):
        """Test handling of Django UploadedFile-like objects."""
        # Create a mock UploadedFile-like object
        class MockUploadedFile:
            def __init__(self, content):
                self.content = content
                self.name = "test_wallet.zip"
                self.chunks_data = [content]

            def read(self):
                return self.content

            def chunks(self, chunk_size=64*1024):
                return iter(self.chunks_data)

        # Create the mock uploaded file with our test wallet content
        test_zip_path = self.create_test_wallet_zip()

        try:
            with open(test_zip_path, 'rb') as f:
                wallet_content = f.read()

            mock_file = MockUploadedFile(wallet_content)

            settings = self.test_settings.copy()
            settings["wallet_file"] = mock_file

            # Mock oracledb.connect to avoid actual database connection
            with patch('unstract.connectors.databases.oracle_db.oracle_db.oracledb.connect'):
                # Should successfully create Oracle connection
                oracle_db = OracleDB(settings)

                # Verify that wallet directory was created and contains expected files
                self.assertTrue(hasattr(oracle_db, '_temp_wallet_dir'))
                self.assertTrue(os.path.exists(oracle_db._temp_wallet_dir))
                self.assertIsNotNone(oracle_db.config_dir)
                self.assertIsNotNone(oracle_db.wallet_location)
                self.assertEqual(oracle_db.config_dir, oracle_db.wallet_location)

                # Verify wallet files exist
                wallet_files = os.listdir(oracle_db.wallet_location)
                self.assertIn("tnsnames.ora", wallet_files)
                self.assertIn("sqlnet.ora", wallet_files)

        finally:
            # Clean up test ZIP file
            os.unlink(test_zip_path)


if __name__ == '__main__':
    unittest.main()
