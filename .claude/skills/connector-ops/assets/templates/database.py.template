"""
Database Connector Template

Replace placeholders:
- {ClassName}: PascalCase class name (e.g., PostgreSQL, MongoDB)
- {connector_name}: lowercase connector name (e.g., postgresql, mongodb)
- {display_name}: Display name (e.g., "PostgreSQL", "MongoDB")
- {description}: Brief description
- {uuid}: Generated UUID (use uuid4())
- {icon_name}: Icon filename (e.g., "Postgresql.png")
- {connection_lib}: Python library for connections (e.g., psycopg2, pymongo)
"""

import os
from typing import Any

from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError


class {ClassName}(UnstractDB):
    """
    {display_name} database connector.

    {description}
    """

    def __init__(self, settings: dict[str, Any]):
        super().__init__("{display_name}")

        # Connection URL mode
        self.connection_url = settings.get("connection_url", "")

        # Individual parameters mode
        self.host = settings.get("host", "")
        self.port = settings.get("port", "{default_port}")
        self.database = settings.get("database", "")
        self.user = settings.get("user", "")
        self.password = settings.get("password", "")

        # Optional settings
        self.schema = settings.get("schema", "")
        self.ssl_enabled = settings.get("sslEnabled", False)

    @staticmethod
    def get_id() -> str:
        return "{connector_name}|{uuid}"

    @staticmethod
    def get_name() -> str:
        return "{display_name}"

    @staticmethod
    def get_description() -> str:
        return "{description}"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/{icon_name}"

    @staticmethod
    def get_json_schema() -> str:
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "json_schema.json"
        )
        with open(schema_path, "r") as f:
            return f.read()

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    def get_engine(self) -> Any:
        """
        Return database connection.

        Returns:
            Database connection object
        """
        # Import here for fork safety
        import {connection_lib}

        try:
            conn_params = {
                # TCP keepalive for long-running queries
                "connect_timeout": 30,
            }

            if self.connection_url:
                # URL mode
                conn_params["dsn"] = self.connection_url
            else:
                # Individual params mode
                conn_params.update({
                    "host": self.host,
                    "port": int(self.port),
                    "database": self.database,
                    "user": self.user,
                    "password": self.password,
                })

            # Add SSL if enabled
            if self.ssl_enabled:
                conn_params["ssl"] = True
                # Add more SSL options as needed:
                # conn_params["ssl_ca"] = self.ssl_ca
                # conn_params["ssl_cert"] = self.ssl_cert
                # conn_params["ssl_key"] = self.ssl_key

            return {connection_lib}.connect(**conn_params)

        except Exception as e:
            raise ConnectorError(
                f"Failed to connect to {display_name}: {str(e)}",
                treat_as_user_message=True
            ) from e

    def test_credentials(self) -> bool:
        """
        Test database credentials.

        Returns:
            True if connection successful

        Raises:
            ConnectorError: If connection fails
        """
        try:
            conn = self.get_engine()
            # Execute simple test query
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            raise ConnectorError(
                f"Connection test failed: {str(e)}",
                treat_as_user_message=True
            ) from e

    def execute(self, query: str) -> list[tuple]:
        """
        Execute SQL query.

        Args:
            query: SQL query string

        Returns:
            List of result tuples
        """
        conn = self.get_engine()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                if cursor.description:  # SELECT query
                    return cursor.fetchall()
                else:  # INSERT/UPDATE/DELETE
                    conn.commit()
                    return []
        finally:
            conn.close()

    def sql_to_db_mapping(self, value: Any, column_name: str | None = None) -> str:
        """
        Map Python types to database types.

        Args:
            value: Python value to map
            column_name: Optional column name hint

        Returns:
            Database type string
        """
        if value is None:
            return "TEXT"

        if isinstance(value, bool):
            return "BOOLEAN"
        elif isinstance(value, int):
            return "INTEGER"
        elif isinstance(value, float):
            return "DOUBLE PRECISION"
        elif isinstance(value, dict):
            return "JSON"  # or JSONB for PostgreSQL
        elif isinstance(value, list):
            return "JSON"
        elif isinstance(value, bytes):
            return "BYTEA"
        else:
            return "TEXT"
