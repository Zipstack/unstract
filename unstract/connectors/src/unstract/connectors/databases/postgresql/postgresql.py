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

    def get_engine(self) -> connection:
        """
        Returns a connection to the PostgreSQL database.

        Returns:
            connection: A connection to the PostgreSQL database.
        """
        conn_params = {
            "keepalives": 1,
            "keepalives_idle": self.KEEPALIVE_IDLE,
            "keepalives_interval": self.KEEPALIVE_INTERVAL,
            "keepalives_count": self.KEEPALIVE_COUNT,
            "connect_timeout": self.CONNECT_TIMEOUT,
            "application_name": "unstract_connector",
            "sslmode": "prefer",
        }

        if self.connection_url:
            # Use the URL directly without adding extra options
            conn_params["dsn"] = self.connection_url
        else:
            # For non-URL connections
            conn_params.update(
                {
                    "host": self.host,
                    "port": self.port,
                    "database": self.database,
                    "user": self.user,
                    "password": self.password,
                }
            )

        con = psycopg2.connect(**conn_params)

        # Set schema explicitly only if schema is specified (avoids PgBouncer issues)
        if self.schema:
            with con.cursor() as cur:
                cur.execute(f"SET search_path TO {self.schema};")

        return con

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
