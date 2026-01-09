# Test Patterns Reference

Patterns for writing connector tests - both mock-based (always runnable) and integration (requires real services).

## Test File Organization

```
tests/
├── __init__.py
├── test_connectorkit.py          # Registry tests
├── databases/
│   ├── __init__.py
│   ├── test_postgresql.py        # Mock tests
│   ├── test_postgresql_integration.py  # Integration tests
│   └── conftest.py               # Shared fixtures
├── filesystems/
│   ├── __init__.py
│   ├── test_google_drive.py
│   └── conftest.py
└── queues/
    ├── __init__.py
    └── test_redis_queue.py
```

---

## Mock-Based Test Template

Always runnable without external dependencies:

```python
import unittest
from unittest.mock import patch, Mock, MagicMock
import os

from unstract.connectors.databases.{connector_name}.{connector_name} import {ClassName}


class Test{ClassName}(unittest.TestCase):
    """Mock-based tests for {ClassName} connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.basic_config = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
        }

        self.url_config = {
            "connection_url": "postgresql://user:pass@localhost:5432/db"
        }

    def test_static_methods(self):
        """Test static connector metadata methods."""
        # These don't require instantiation
        self.assertIsNotNone({ClassName}.get_id())
        self.assertIsNotNone({ClassName}.get_name())
        self.assertIsNotNone({ClassName}.get_description())
        self.assertIsNotNone({ClassName}.get_icon())
        self.assertIsNotNone({ClassName}.get_json_schema())
        self.assertIsInstance({ClassName}.can_write(), bool)
        self.assertIsInstance({ClassName}.can_read(), bool)
        self.assertIsInstance({ClassName}.requires_oauth(), bool)

    def test_connector_id_format(self):
        """Test connector ID follows expected format."""
        connector_id = {ClassName}.get_id()
        self.assertIn("|", connector_id)
        name, uuid = connector_id.split("|", 1)
        self.assertTrue(len(uuid) > 0)

    def test_json_schema_valid(self):
        """Test JSON schema is valid JSON."""
        import json
        schema_str = {ClassName}.get_json_schema()
        schema = json.loads(schema_str)
        self.assertIn("title", schema)
        self.assertEqual(schema["type"], "object")

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_initialization_with_params(self, mock_connect):
        """Test connector initializes with individual parameters."""
        mock_connect.return_value = Mock()

        connector = {ClassName}(self.basic_config)

        self.assertEqual(connector.host, "localhost")
        self.assertEqual(connector.port, "5432")
        self.assertEqual(connector.database, "testdb")

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_initialization_with_url(self, mock_connect):
        """Test connector initializes with connection URL."""
        mock_connect.return_value = Mock()

        connector = {ClassName}(self.url_config)

        self.assertEqual(connector.connection_url, self.url_config["connection_url"])

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_get_engine(self, mock_connect):
        """Test get_engine returns connection."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        engine = connector.get_engine()

        mock_connect.assert_called_once()
        self.assertEqual(engine, mock_connection)

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_test_credentials_success(self, mock_connect):
        """Test test_credentials returns True on success."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        result = connector.test_credentials()

        self.assertTrue(result)

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_test_credentials_failure(self, mock_connect):
        """Test test_credentials raises on failure."""
        mock_connect.side_effect = Exception("Connection failed")

        connector = {ClassName}(self.basic_config)

        from unstract.connectors.exceptions import ConnectorError
        with self.assertRaises(ConnectorError):
            connector.test_credentials()

    @patch("unstract.connectors.databases.{connector_name}.{connector_name}.{connection_lib}.connect")
    def test_execute_query(self, mock_connect):
        """Test query execution."""
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("row1",), ("row2",)]
        mock_connection = Mock()
        mock_connection.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_connection.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        result = connector.execute("SELECT * FROM test")

        mock_cursor.execute.assert_called_with("SELECT * FROM test")

    def test_sql_to_db_mapping_string(self):
        """Test type mapping for strings."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping("test string")
        self.assertIn(result.upper(), ["TEXT", "VARCHAR", "STRING"])

    def test_sql_to_db_mapping_integer(self):
        """Test type mapping for integers."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping(42)
        self.assertIn(result.upper(), ["INTEGER", "INT", "BIGINT", "INT64"])

    def test_sql_to_db_mapping_dict(self):
        """Test type mapping for dictionaries (JSON)."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping({"key": "value"})
        self.assertIn(result.upper(), ["JSON", "JSONB", "VARIANT", "STRING"])


if __name__ == "__main__":
    unittest.main()
```

---

## Integration Test Template

Requires real service - skipped by default:

```python
import unittest
import os

from unstract.connectors.databases.{connector_name}.{connector_name} import {ClassName}


@unittest.skipUnless(
    os.getenv("{CONNECTOR_PREFIX}_HOST"),
    "Integration tests require {CONNECTOR_PREFIX}_* environment variables"
)
class Test{ClassName}Integration(unittest.TestCase):
    """Integration tests for {ClassName} - requires real database."""

    @classmethod
    def setUpClass(cls):
        """Set up integration test configuration from environment."""
        cls.config = {
            "host": os.getenv("{CONNECTOR_PREFIX}_HOST"),
            "port": os.getenv("{CONNECTOR_PREFIX}_PORT", "5432"),
            "database": os.getenv("{CONNECTOR_PREFIX}_DATABASE"),
            "user": os.getenv("{CONNECTOR_PREFIX}_USER"),
            "password": os.getenv("{CONNECTOR_PREFIX}_PASSWORD"),
        }

        # Validate all required vars present
        missing = [k for k, v in cls.config.items() if not v]
        if missing:
            raise unittest.SkipTest(f"Missing env vars: {missing}")

    def test_real_connection(self):
        """Test connecting to real database."""
        connector = {ClassName}(self.config)
        self.assertTrue(connector.test_credentials())

    def test_real_query(self):
        """Test executing query on real database."""
        connector = {ClassName}(self.config)
        engine = connector.get_engine()

        with engine.cursor() as cursor:
            cursor.execute("SELECT 1 AS test")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)

        engine.close()

    def test_real_table_operations(self):
        """Test table operations on real database."""
        connector = {ClassName}(self.config)
        engine = connector.get_engine()

        try:
            with engine.cursor() as cursor:
                # Create test table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _unstract_test_table (
                        id SERIAL PRIMARY KEY,
                        name TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                # Insert data
                cursor.execute(
                    "INSERT INTO _unstract_test_table (name) VALUES (%s)",
                    ("test_value",)
                )

                # Query data
                cursor.execute("SELECT name FROM _unstract_test_table WHERE name = %s", ("test_value",))
                result = cursor.fetchone()
                self.assertEqual(result[0], "test_value")

                engine.commit()
        finally:
            # Cleanup
            with engine.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS _unstract_test_table")
                engine.commit()
            engine.close()


if __name__ == "__main__":
    unittest.main()
```

---

## Filesystem Test Template (Mock)

```python
import unittest
from unittest.mock import patch, Mock, MagicMock
from io import BytesIO

from unstract.connectors.filesystems.{connector_name}.{connector_name} import {ClassName}


class Test{ClassName}(unittest.TestCase):
    """Mock-based tests for {ClassName} filesystem connector."""

    def setUp(self):
        self.config = {
            "access_key": "test_key",
            "secret_key": "test_secret",
            "bucket": "test-bucket",
            "endpoint_url": "https://s3.example.com",
        }

    def test_static_methods(self):
        """Test static connector metadata."""
        self.assertIsNotNone({ClassName}.get_id())
        self.assertIsNotNone({ClassName}.get_name())
        self.assertEqual({ClassName}.get_connector_mode().value, "FILESYSTEM")

    @patch("unstract.connectors.filesystems.{connector_name}.{connector_name}.{fsspec_class}")
    def test_get_fsspec_fs(self, mock_fs_class):
        """Test fsspec filesystem creation."""
        mock_fs = Mock()
        mock_fs_class.return_value = mock_fs

        connector = {ClassName}(self.config)
        fs = connector.get_fsspec_fs()

        self.assertEqual(fs, mock_fs)

    @patch("unstract.connectors.filesystems.{connector_name}.{connector_name}.{fsspec_class}")
    def test_test_credentials_success(self, mock_fs_class):
        """Test credentials validation success."""
        mock_fs = Mock()
        mock_fs.ls.return_value = ["file1.txt", "file2.txt"]
        mock_fs_class.return_value = mock_fs

        connector = {ClassName}(self.config)
        result = connector.test_credentials()

        self.assertTrue(result)

    @patch("unstract.connectors.filesystems.{connector_name}.{connector_name}.{fsspec_class}")
    def test_test_credentials_failure(self, mock_fs_class):
        """Test credentials validation failure."""
        mock_fs_class.side_effect = Exception("Access denied")

        connector = {ClassName}(self.config)

        from unstract.connectors.exceptions import ConnectorError
        with self.assertRaises(ConnectorError):
            connector.test_credentials()

    def test_extract_metadata_file_hash(self):
        """Test file hash extraction from metadata."""
        connector = {ClassName}.__new__({ClassName})

        metadata = {"ETag": "abc123", "size": 1024}
        result = connector.extract_metadata_file_hash(metadata)

        self.assertEqual(result, "abc123")

    def test_is_dir_by_metadata(self):
        """Test directory detection from metadata."""
        connector = {ClassName}.__new__({ClassName})

        dir_metadata = {"type": "directory"}
        file_metadata = {"type": "file"}

        self.assertTrue(connector.is_dir_by_metadata(dir_metadata))
        self.assertFalse(connector.is_dir_by_metadata(file_metadata))


if __name__ == "__main__":
    unittest.main()
```

---

## Queue Test Template (Mock)

```python
import unittest
from unittest.mock import patch, Mock

from unstract.connectors.queues.{connector_name}.{connector_name} import {ClassName}


class Test{ClassName}(unittest.TestCase):
    """Mock-based tests for {ClassName} queue connector."""

    def setUp(self):
        self.config = {
            "host": "localhost",
            "port": "6379",
            "password": "testpass",
        }

    def test_static_methods(self):
        """Test static connector metadata."""
        self.assertIsNotNone({ClassName}.get_id())
        self.assertEqual({ClassName}.get_connector_mode().value, "MANUAL_REVIEW")

    @patch("unstract.connectors.queues.{connector_name}.{connector_name}.{queue_lib}")
    def test_enqueue(self, mock_client):
        """Test message enqueueing."""
        mock_connection = Mock()
        mock_client.return_value = mock_connection

        connector = {ClassName}(self.config)
        connector.enqueue("test_queue", "test_message")

        # Assert enqueue was called
        mock_connection.lpush.assert_called()  # or appropriate method

    @patch("unstract.connectors.queues.{connector_name}.{connector_name}.{queue_lib}")
    def test_dequeue(self, mock_client):
        """Test message dequeueing."""
        mock_connection = Mock()
        mock_connection.brpop.return_value = ("test_queue", b"test_message")
        mock_client.return_value = mock_connection

        connector = {ClassName}(self.config)
        result = connector.dequeue("test_queue")

        self.assertEqual(result, "test_message")

    @patch("unstract.connectors.queues.{connector_name}.{connector_name}.{queue_lib}")
    def test_peek(self, mock_client):
        """Test message peeking."""
        mock_connection = Mock()
        mock_connection.lindex.return_value = b"test_message"
        mock_client.return_value = mock_connection

        connector = {ClassName}(self.config)
        result = connector.peek("test_queue")

        self.assertEqual(result, "test_message")


if __name__ == "__main__":
    unittest.main()
```

---

## Shared Fixtures (conftest.py)

```python
import pytest
import os


@pytest.fixture
def mock_db_config():
    """Standard database test configuration."""
    return {
        "host": "localhost",
        "port": "5432",
        "database": "testdb",
        "user": "testuser",
        "password": "testpass",
    }


@pytest.fixture
def mock_fs_config():
    """Standard filesystem test configuration."""
    return {
        "access_key": "test_key",
        "secret_key": "test_secret",
        "bucket": "test-bucket",
    }


@pytest.fixture
def integration_db_config():
    """Integration test database configuration from environment."""
    config = {
        "host": os.getenv("TEST_DB_HOST"),
        "port": os.getenv("TEST_DB_PORT", "5432"),
        "database": os.getenv("TEST_DB_DATABASE"),
        "user": os.getenv("TEST_DB_USER"),
        "password": os.getenv("TEST_DB_PASSWORD"),
    }

    if not all(config.values()):
        pytest.skip("Integration test requires TEST_DB_* environment variables")

    return config
```

---

## Running Tests

```bash
# Run all mock tests (always works)
cd unstract/connectors
python -m pytest tests/ -v --ignore=tests/**/test_*_integration.py

# Run specific connector tests
python -m pytest tests/databases/test_postgresql.py -v

# Run integration tests (requires env vars)
export POSTGRESQL_HOST=localhost
export POSTGRESQL_PORT=5432
export POSTGRESQL_DATABASE=testdb
export POSTGRESQL_USER=testuser
export POSTGRESQL_PASSWORD=testpass
python -m pytest tests/databases/test_postgresql_integration.py -v

# Run with coverage
python -m pytest tests/ -v --cov=src/unstract/connectors --cov-report=html
```

---

## Common Test Assertions

```python
# Connector ID format
self.assertRegex(connector.get_id(), r"^[a-z_]+\|[a-f0-9-]+$")

# JSON schema validity
import json
schema = json.loads(connector.get_json_schema())
self.assertIn("title", schema)
self.assertIn("type", schema)

# Connection returns correct type
from psycopg2.extensions import connection
self.assertIsInstance(connector.get_engine(), connection)

# Exception handling
from unstract.connectors.exceptions import ConnectorError
with self.assertRaises(ConnectorError) as ctx:
    connector.test_credentials()
self.assertIn("expected message", str(ctx.exception))
```
