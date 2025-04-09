import datetime
import os
from typing import Any

import psycopg2
from psycopg2.extensions import connection

from unstract.connectors.databases.psycopg_handler import PsycoPgHandler
from unstract.connectors.databases.unstract_db import UnstractDB


class PostgreSQL(UnstractDB, PsycoPgHandler):
    # Connection timeout settings (in seconds)
    CONNECT_TIMEOUT = 30  # Time to establish connection
    STATEMENT_TIMEOUT = 300  # Time for query execution (5 minutes)
    KEEPALIVE_IDLE = 30  # Time before sending keepalive
    KEEPALIVE_INTERVAL = 10  # Time between keepalive probes
    KEEPALIVE_COUNT = 3  # Number of keepalive failures before dropping

    def __init__(self, settings: dict[str, Any]):
        super().__init__("PostgreSQL")

        self.user = settings.get("user", "")
        self.password = settings.get("password", "")
        self.host = settings.get("host", "")
        self.port = settings.get("port", "")
        self.database = settings.get("database", "")
        self.schema = settings.get("schema", "public")
        self.connection_url = settings.get("connection_url", "")
        if not self.schema:
            self.schema = "public"
        if not self.connection_url and not (
            self.user and self.password and self.host and self.port and self.database
        ):
            raise ValueError(
                "Either ConnectionURL or connection parameters must be provided."
            )

    @staticmethod
    def get_id() -> str:
        return "postgresql|6db35f45-be11-4fd5-80c5-85c48183afbb"

    @staticmethod
    def get_name() -> str:
        return "PostgreSQL"

    @staticmethod
    def get_description() -> str:
        return "postgresql Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Postgresql.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_string_type(self) -> str:
        return "text"

    def sql_to_db_mapping(self, value: str) -> str:
        """Gets the python datatype of value and converts python datatype to
        corresponding DB datatype.

        Args:
            value (str): python datatype

        Returns:
            str: database columntype
        """
        python_type = type(value)

        mapping = {
            str: "TEXT",
            int: "INTEGER",
            float: "DOUBLE PRECISION",
            datetime.datetime: "TIMESTAMP",
            dict: "JSONB",
            list: "JSONB",
        }
        return mapping.get(python_type, "TEXT")

    def get_engine(self) -> connection:
        # Set timeouts via options
        timeout_options = (
            f"-c connect_timeout={self.CONNECT_TIMEOUT} "
            f"-c statement_timeout={self.STATEMENT_TIMEOUT * 1000} "
            f"-c tcp_keepalives_idle={self.KEEPALIVE_IDLE} "
            f"-c tcp_keepalives_interval={self.KEEPALIVE_INTERVAL} "
            f"-c tcp_keepalives_count={self.KEEPALIVE_COUNT}"
        )

        # Base connection parameters
        conn_params = {
            "keepalives": 1,
            "keepalives_idle": self.KEEPALIVE_IDLE,
            "keepalives_interval": self.KEEPALIVE_INTERVAL,
            "keepalives_count": self.KEEPALIVE_COUNT,
            "connect_timeout": self.CONNECT_TIMEOUT,
            "application_name": "unstract_connector",
        }

        # Determine SSL mode based on connection URL
        if self.connection_url and (
            "neon.tech" in self.connection_url or "amazonaws.com" in self.connection_url
        ):
            # Cloud hosted PostgreSQL (Neon, AWS RDS etc)
            conn_params.update({"sslmode": "verify-full", "sslrootcert": "system"})
        else:
            # Standard PostgreSQL - use basic SSL if available
            conn_params["sslmode"] = "prefer"

        if self.connection_url:
            conn_params.update({"dsn": self.connection_url, "options": timeout_options})
            con = psycopg2.connect(**conn_params)
        else:
            conn_params.update(
                {
                    "host": self.host,
                    "port": self.port,
                    "database": self.database,
                    "user": self.user,
                    "password": self.password,
                    "options": f"{timeout_options} -c search_path={self.schema}",
                }
            )
            con = psycopg2.connect(**conn_params)

        return con

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query with PostgreSQL specific types.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id TEXT, "
            f"created_by TEXT, created_at TIMESTAMP, "
            f"metadata JSONB, "
            f"user_field_1 BOOLEAN DEFAULT FALSE, "
            f"user_field_2 INTEGER DEFAULT 0, "
            f"user_field_3 TEXT DEFAULT NULL, "
        )
        return sql_query

    def migrate_table_to_v2_query(self, table_name: str, column_name: str) -> str:
        sql_query = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name}_v2 JSONB, "
            f"ADD COLUMN metadata JSONB, "
            f"ADD COLUMN user_field_1 BOOLEAN DEFAULT FALSE, "
            f"ADD COLUMN user_field_2 INTEGER DEFAULT 0, "
            f"ADD COLUMN user_field_3 TEXT DEFAULT NULL"
        )
        return sql_query

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        table_name = kwargs.get("table_name", None)
        PsycoPgHandler.execute_query(
            engine=engine,
            sql_query=sql_query,
            sql_values=sql_values,
            database=self.database,
            schema=self.schema,
            table_name=table_name,
        )
