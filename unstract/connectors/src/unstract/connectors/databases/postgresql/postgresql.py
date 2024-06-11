import os
from typing import Any

import psycopg2
from psycopg2.extensions import connection

from unstract.connectors.databases.psycopg_handler import PsycoPgHandler
from unstract.connectors.databases.unstract_db import UnstractDB


class PostgreSQL(UnstractDB, PsycoPgHandler):
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
        if self.connection_url:
            con = psycopg2.connect(dsn=self.connection_url)
        else:
            con = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                options=f"-c search_path={self.schema}",
            )
        return con

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        PsycoPgHandler.execute_query(
            engine=engine,
            sql_query=sql_query,
            sql_values=sql_values,
            database=self.database,
        )
