"""
Mock Test Template

Replace placeholders:
- {ClassName}: PascalCase class name
- {connector_name}: lowercase connector name
- {connector_type}: databases, filesystems, or queues
- {connection_lib}: Python library for connections
"""

import unittest
from unittest.mock import patch, Mock
import json

from unstract.connectors.{connector_type}.{connector_name}.{connector_name} import {ClassName}
from unstract.connectors.exceptions import ConnectorError


class Test{ClassName}(unittest.TestCase):
    """Mock-based tests for {ClassName} connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.basic_config = {
            "host": "localhost",
            "port": "{default_port}",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
        }

        self.url_config = {
            "connection_url": "{protocol}://user:pass@localhost:{default_port}/db"
        }

    # ===================
    # Static Method Tests
    # ===================

    def test_get_id(self):
        """Test connector ID format."""
        connector_id = {ClassName}.get_id()
        self.assertIsNotNone(connector_id)
        self.assertIn("|", connector_id)

        # Validate UUID portion
        name, uuid_part = connector_id.split("|", 1)
        self.assertEqual(name, "{connector_name}")
        self.assertTrue(len(uuid_part) > 0)

    def test_get_name(self):
        """Test connector display name."""
        name = {ClassName}.get_name()
        self.assertIsNotNone(name)
        self.assertIsInstance(name, str)

    def test_get_description(self):
        """Test connector description."""
        description = {ClassName}.get_description()
        self.assertIsNotNone(description)
        self.assertIsInstance(description, str)

    def test_get_icon(self):
        """Test connector icon path."""
        icon = {ClassName}.get_icon()
        self.assertIsNotNone(icon)
        self.assertTrue(icon.startswith("/icons/"))

    def test_get_json_schema(self):
        """Test JSON schema validity."""
        schema_str = {ClassName}.get_json_schema()
        self.assertIsNotNone(schema_str)

        # Parse and validate JSON
        schema = json.loads(schema_str)
        self.assertIn("title", schema)
        self.assertEqual(schema["type"], "object")
        self.assertIn("allOf", schema)

    def test_can_write(self):
        """Test write capability flag."""
        result = {ClassName}.can_write()
        self.assertIsInstance(result, bool)

    def test_can_read(self):
        """Test read capability flag."""
        result = {ClassName}.can_read()
        self.assertIsInstance(result, bool)

    def test_requires_oauth(self):
        """Test OAuth requirement flag."""
        result = {ClassName}.requires_oauth()
        self.assertIsInstance(result, bool)

    def test_get_connector_mode(self):
        """Test connector mode."""
        from unstract.connectors.enums import ConnectorMode
        mode = {ClassName}.get_connector_mode()
        self.assertIsInstance(mode, ConnectorMode)

    # ===================
    # Initialization Tests
    # ===================

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_init_with_basic_config(self, mock_lib):
        """Test initialization with individual parameters."""
        connector = {ClassName}(self.basic_config)

        self.assertEqual(connector.host, "localhost")
        self.assertEqual(connector.port, "{default_port}")
        self.assertEqual(connector.database, "testdb")
        self.assertEqual(connector.user, "testuser")
        self.assertEqual(connector.password, "testpass")

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_init_with_url_config(self, mock_lib):
        """Test initialization with connection URL."""
        connector = {ClassName}(self.url_config)

        self.assertEqual(
            connector.connection_url,
            self.url_config["connection_url"]
        )

    # ===================
    # Connection Tests
    # ===================

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_get_engine_success(self, mock_lib):
        """Test successful connection."""
        mock_connection = Mock()
        mock_lib.connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        engine = connector.get_engine()

        mock_lib.connect.assert_called_once()
        self.assertEqual(engine, mock_connection)

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_get_engine_failure(self, mock_lib):
        """Test connection failure handling."""
        mock_lib.connect.side_effect = Exception("Connection refused")

        connector = {ClassName}(self.basic_config)

        with self.assertRaises(ConnectorError) as ctx:
            connector.get_engine()

        self.assertIn("Connection refused", str(ctx.exception))

    # ===================
    # Credential Tests
    # ===================

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_test_credentials_success(self, mock_lib):
        """Test credential validation success."""
        mock_cursor = Mock()
        mock_connection = Mock()
        mock_connection.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_connection.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_lib.connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        result = connector.test_credentials()

        self.assertTrue(result)

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_test_credentials_failure(self, mock_lib):
        """Test credential validation failure."""
        mock_lib.connect.side_effect = Exception("Authentication failed")

        connector = {ClassName}(self.basic_config)

        with self.assertRaises(ConnectorError):
            connector.test_credentials()

    # ===================
    # Query Tests (Database only)
    # ===================

    @patch("unstract.connectors.{connector_type}.{connector_name}.{connector_name}.{connection_lib}")
    def test_execute_select(self, mock_lib):
        """Test SELECT query execution."""
        mock_cursor = Mock()
        mock_cursor.description = [("col1",)]
        mock_cursor.fetchall.return_value = [("row1",), ("row2",)]

        mock_connection = Mock()
        mock_connection.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_connection.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_lib.connect.return_value = mock_connection

        connector = {ClassName}(self.basic_config)
        result = connector.execute("SELECT * FROM test")

        mock_cursor.execute.assert_called_with("SELECT * FROM test")
        self.assertEqual(len(result), 2)

    # ===================
    # Type Mapping Tests (Database only)
    # ===================

    def test_sql_to_db_mapping_string(self):
        """Test type mapping for strings."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping("test")
        self.assertIsInstance(result, str)

    def test_sql_to_db_mapping_integer(self):
        """Test type mapping for integers."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping(42)
        self.assertIsInstance(result, str)

    def test_sql_to_db_mapping_dict(self):
        """Test type mapping for dicts (JSON)."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping({"key": "value"})
        self.assertIsInstance(result, str)

    def test_sql_to_db_mapping_none(self):
        """Test type mapping for None."""
        connector = {ClassName}.__new__({ClassName})
        result = connector.sql_to_db_mapping(None)
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
