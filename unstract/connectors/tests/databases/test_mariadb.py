import os
import unittest
from typing import Any
from unittest.mock import Mock, patch

import pymysql.err as MysqlError

from unstract.connectors.databases.mariadb.mariadb import MariaDB
from unstract.connectors.exceptions import ConnectorError


class TestMariaDB(unittest.TestCase):
    def setUp(self) -> None:
        """Set up test configuration from environment variables"""

        # SSL enabled config for testing SSL scenarios
        self.mariadb_config_ssl_enabled = {
            "host": os.getenv("MARIADB_HOST", "localhost"),
            "port": os.getenv("MARIADB_PORT", "3306"),
            "database": os.getenv("MARIADB_DATABASE", "testdb"),
            "user": os.getenv("MARIADB_USER", "root"),
            "password": os.getenv("MARIADB_PASSWORD", ""),
            "sslEnabled": True,
        }

        # SSL disabled config for testing non-SSL scenarios
        self.mariadb_config_ssl_disabled = {
            "host": os.getenv("MARIADB_HOST", "localhost"),
            "port": os.getenv("MARIADB_PORT", "3306"),
            "database": os.getenv("MARIADB_DATABASE", "testdb"),
            "user": os.getenv("MARIADB_USER", "root"),
            "password": os.getenv("MARIADB_PASSWORD", ""),
            "sslEnabled": False,
        }

    def test_ssl_config_from_environment(self) -> None:
        """Test SSL configuration is loaded from environment variables"""
        # Use existing config but override SSL to read from environment
        config = {**self.mariadb_config_ssl_enabled, "sslEnabled": os.getenv("MARIADB_SSL_ENABLED", "false").lower() == "true"}

        mariadb = MariaDB(config)
        expected_ssl = os.getenv("MARIADB_SSL_ENABLED", "false").lower() == "true"
        self.assertEqual(mariadb.ssl_enabled, expected_ssl)

    @patch("unstract.connectors.databases.mariadb.mariadb.pymysql.connect")
    def test_connection_params_ssl_enabled(self, mock_connect: Any) -> None:
        """Test that SSL parameters are passed when SSL is enabled"""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        mariadb = MariaDB(self.mariadb_config_ssl_enabled)

        result = mariadb.get_engine()

        # Verify pymysql.connect was called with SSL parameters
        mock_connect.assert_called_once()
        call_args = mock_connect.call_args[1]
        self.assertIn("ssl", call_args)
        self.assertEqual(call_args["ssl"], {"ssl_disabled": False})
        self.assertEqual(result, mock_connection)

    @patch("unstract.connectors.databases.mariadb.mariadb.pymysql.connect")
    def test_connection_params_ssl_disabled(self, mock_connect: Any) -> None:
        """Test that no SSL parameters are passed when SSL is disabled"""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        mariadb = MariaDB(self.mariadb_config_ssl_disabled)
        result = mariadb.get_engine()

        mock_connect.assert_called_once()
        call_args = mock_connect.call_args[1]
        self.assertNotIn("ssl", call_args)
        self.assertEqual(result, mock_connection)

    @patch("unstract.connectors.databases.mariadb.mariadb.pymysql.connect")
    def test_authentication_error_handling(self, mock_connect: Any) -> None:
        """Test authentication error (1045) produces proper error message"""
        mock_connect.side_effect = MysqlError.OperationalError(
            1045, "Access denied for user 'test'@'localhost'"
        )

        mariadb = MariaDB(self.mariadb_config_ssl_enabled)

        with self.assertRaises(ConnectorError) as context:
            mariadb.get_engine()

        error_message = str(context.exception)
        self.assertIn("Authentication failed", error_message)
        self.assertIn("username, password and ssl-settings", error_message)
        self.assertIn("localhost:3306", error_message)
        self.assertIn("SSL enabled", error_message)

    @patch("unstract.connectors.databases.mariadb.mariadb.pymysql.connect")
    def test_network_error_handling_ssl_enabled(self, mock_connect: Any) -> None:
        """Test network error (2003) with SSL enabled includes SSL context"""
        mock_connect.side_effect = MysqlError.OperationalError(
            2003, "Can't connect to MySQL server"
        )

        mariadb = MariaDB(self.mariadb_config_ssl_enabled)

        with self.assertRaises(ConnectorError) as context:
            mariadb.get_engine()

        error_message = str(context.exception)
        self.assertIn("Cannot connect to server", error_message)
        self.assertIn("localhost:3306", error_message)
        self.assertIn("SSL enabled", error_message)

    @patch("unstract.connectors.databases.mariadb.mariadb.pymysql.connect")
    def test_network_error_handling_ssl_disabled(self, mock_connect: Any) -> None:
        """Test network error (2003) with SSL disabled includes SSL context"""
        mock_connect.side_effect = MysqlError.OperationalError(
            2003, "Can't connect to MySQL server"
        )

        mariadb = MariaDB(self.mariadb_config_ssl_disabled)

        with self.assertRaises(ConnectorError) as context:
            mariadb.get_engine()

        error_message = str(context.exception)
        self.assertIn("Cannot connect to server", error_message)
        self.assertIn("localhost:3306", error_message)
        self.assertIn("SSL disabled", error_message)


if __name__ == "__main__":
    unittest.main()
