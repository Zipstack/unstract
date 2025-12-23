"""
Integration Test Template

Replace placeholders:
- {ClassName}: PascalCase class name
- {connector_name}: lowercase connector name
- {connector_type}: databases, filesystems, or queues
- {CONNECTOR_PREFIX}: uppercase prefix for env vars (e.g., POSTGRESQL, MINIO)

These tests require real services and are skipped by default.
Set environment variables to enable them.
"""

import os
import unittest

from unstract.connectors.{connector_type}.{connector_name}.{connector_name} import {ClassName}


@unittest.skipUnless(
    os.getenv("{CONNECTOR_PREFIX}_HOST"),
    "Integration tests require {CONNECTOR_PREFIX}_* environment variables. "
    "Set {CONNECTOR_PREFIX}_HOST to enable."
)
class Test{ClassName}Integration(unittest.TestCase):
    """
    Integration tests for {ClassName}.

    Requires real service connection.

    Environment variables:
        {CONNECTOR_PREFIX}_HOST: Server hostname
        {CONNECTOR_PREFIX}_PORT: Server port (optional, uses default)
        {CONNECTOR_PREFIX}_DATABASE: Database name
        {CONNECTOR_PREFIX}_USER: Username
        {CONNECTOR_PREFIX}_PASSWORD: Password
    """

    @classmethod
    def setUpClass(cls):
        """Set up integration test configuration."""
        cls.config = {
            "host": os.getenv("{CONNECTOR_PREFIX}_HOST"),
            "port": os.getenv("{CONNECTOR_PREFIX}_PORT", "{default_port}"),
            "database": os.getenv("{CONNECTOR_PREFIX}_DATABASE", "testdb"),
            "user": os.getenv("{CONNECTOR_PREFIX}_USER", "testuser"),
            "password": os.getenv("{CONNECTOR_PREFIX}_PASSWORD", ""),
        }

        # Validate required vars
        required = ["host", "database", "user"]
        missing = [k for k in required if not cls.config.get(k)]
        if missing:
            raise unittest.SkipTest(
                f"Missing required env vars: {CONNECTOR_PREFIX}_" +
                ", {CONNECTOR_PREFIX}_".join(missing)
            )

    def test_connection(self):
        """Test connecting to real service."""
        connector = {ClassName}(self.config)
        self.assertTrue(connector.test_credentials())

    def test_get_engine(self):
        """Test getting connection engine."""
        connector = {ClassName}(self.config)
        engine = connector.get_engine()
        self.assertIsNotNone(engine)

        # Clean up
        if hasattr(engine, "close"):
            engine.close()

    # ===================
    # Database-Specific Tests
    # ===================

    def test_simple_query(self):
        """Test simple query execution."""
        connector = {ClassName}(self.config)
        engine = connector.get_engine()

        try:
            with engine.cursor() as cursor:
                cursor.execute("SELECT 1 AS test_value")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
        finally:
            engine.close()

    def test_table_operations(self):
        """Test create, insert, select, drop operations."""
        connector = {ClassName}(self.config)
        engine = connector.get_engine()

        test_table = "_unstract_integration_test"

        try:
            with engine.cursor() as cursor:
                # Drop if exists (cleanup from previous failed run)
                cursor.execute(f"DROP TABLE IF EXISTS {test_table}")

                # Create table
                cursor.execute(f"""
                    CREATE TABLE {test_table} (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        value INTEGER
                    )
                """)

                # Insert data
                cursor.execute(
                    f"INSERT INTO {test_table} (name, value) VALUES (%s, %s)",
                    ("test_name", 42)
                )

                # Select data
                cursor.execute(f"SELECT name, value FROM {test_table}")
                result = cursor.fetchone()

                self.assertEqual(result[0], "test_name")
                self.assertEqual(result[1], 42)

                engine.commit()

        finally:
            # Cleanup
            with engine.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {test_table}")
                engine.commit()
            engine.close()

    def test_type_mapping(self):
        """Test type mapping with real data."""
        connector = {ClassName}(self.config)

        # Test various Python types
        test_cases = [
            ("test_string", str),
            (42, str),
            (3.14, str),
            (True, str),
            ({"key": "value"}, str),
            (None, str),
        ]

        for value, expected_type in test_cases:
            result = connector.sql_to_db_mapping(value)
            self.assertIsInstance(
                result,
                expected_type,
                f"Type mapping failed for {type(value).__name__}"
            )

    # ===================
    # Filesystem-Specific Tests (uncomment if filesystem connector)
    # ===================

    # def test_list_files(self):
    #     """Test listing files in bucket/container."""
    #     connector = {ClassName}(self.config)
    #     fs = connector.get_fsspec_fs()
    #
    #     files = fs.ls(self.config.get("bucket", "/"))
    #     self.assertIsInstance(files, list)

    # def test_read_write_file(self):
    #     """Test reading and writing files."""
    #     connector = {ClassName}(self.config)
    #     fs = connector.get_fsspec_fs()
    #
    #     test_path = f"{self.config['bucket']}/_unstract_test.txt"
    #     test_content = b"Hello, World!"
    #
    #     try:
    #         # Write
    #         with fs.open(test_path, "wb") as f:
    #             f.write(test_content)
    #
    #         # Read
    #         with fs.open(test_path, "rb") as f:
    #             content = f.read()
    #
    #         self.assertEqual(content, test_content)
    #
    #     finally:
    #         # Cleanup
    #         if fs.exists(test_path):
    #             fs.rm(test_path)

    # ===================
    # Queue-Specific Tests (uncomment if queue connector)
    # ===================

    # def test_enqueue_dequeue(self):
    #     """Test enqueueing and dequeueing messages."""
    #     connector = {ClassName}(self.config)
    #
    #     test_queue = "_unstract_test_queue"
    #     test_message = "Hello, World!"
    #
    #     try:
    #         # Enqueue
    #         connector.enqueue(test_queue, test_message)
    #
    #         # Dequeue
    #         result = connector.dequeue(test_queue, timeout=5)
    #
    #         self.assertEqual(result, test_message)
    #
    #     finally:
    #         # Cleanup - drain queue
    #         while connector.peek(test_queue):
    #             connector.dequeue(test_queue, timeout=1)


class Test{ClassName}IntegrationSSL(unittest.TestCase):
    """Integration tests with SSL enabled."""

    @classmethod
    def setUpClass(cls):
        """Set up SSL test configuration."""
        if not os.getenv("{CONNECTOR_PREFIX}_SSL_HOST"):
            raise unittest.SkipTest(
                "SSL tests require {CONNECTOR_PREFIX}_SSL_* environment variables"
            )

        cls.config = {
            "host": os.getenv("{CONNECTOR_PREFIX}_SSL_HOST"),
            "port": os.getenv("{CONNECTOR_PREFIX}_SSL_PORT", "{default_port}"),
            "database": os.getenv("{CONNECTOR_PREFIX}_SSL_DATABASE"),
            "user": os.getenv("{CONNECTOR_PREFIX}_SSL_USER"),
            "password": os.getenv("{CONNECTOR_PREFIX}_SSL_PASSWORD"),
            "sslEnabled": True,
        }

    def test_ssl_connection(self):
        """Test SSL connection."""
        connector = {ClassName}(self.config)
        self.assertTrue(connector.test_credentials())


if __name__ == "__main__":
    unittest.main()
