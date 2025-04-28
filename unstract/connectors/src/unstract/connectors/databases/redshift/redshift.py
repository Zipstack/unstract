import datetime
import os
from typing import Any

import psycopg2
from psycopg2.extensions import connection

from unstract.connectors.databases.psycopg_handler import PsycoPgHandler
from unstract.connectors.databases.unstract_db import UnstractDB


class Redshift(UnstractDB, PsycoPgHandler):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Redshift")

        self.user = settings.get("user")
        self.password = settings.get("password")
        self.host = settings.get("host")
        self.port = settings.get("port")
        self.database = settings.get("database")
        self.schema = settings.get("schema", "public")
        if not self.schema:
            self.schema = "public"

    @staticmethod
    def get_id() -> str:
        return "redshift|6c6af35c-9498-4bd6-9258-23b5337e068b"

    @staticmethod
    def get_name() -> str:
        return "Redshift"

    @staticmethod
    def get_description() -> str:
        return "Redshift Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Redshift.png"

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
        return "varchar"

    def get_engine(self) -> connection:
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            options=f"-c search_path={self.schema}",
        )

    def sql_to_db_mapping(self, value: str) -> str:
        python_type = type(value)
        mapping = {
            str: "VARCHAR(MAX)",
            int: "BIGINT",
            float: "DOUBLE PRECISION",
            datetime.datetime: "TIMESTAMP",
            dict: "VARCHAR(MAX)",
            list: "VARCHAR(MAX)",
        }
        return mapping.get(python_type, "VARCHAR(MAX)")

    def get_create_table_base_query(self, table: str) -> str:
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id VARCHAR(65535) ,"
            f"created_by VARCHAR(65535), created_at TIMESTAMP, "
            f"metadata VARCHAR(65535), "
            f"user_field_1 BOOLEAN DEFAULT FALSE, "
            f"user_field_2 INTEGER DEFAULT 0, "
            f"user_field_3 VARCHAR(65535) DEFAULT NULL, "
            f"status VARCHAR(10) CHECK (status IN ('ERROR', 'STATUS')), "
            f"error_message VARCHAR(65535), "
        )
        return sql_query

    def migrate_table_to_v2_query(self, table_name: str, column_name: str) -> str:
        sql_query = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name}_v2 VARCHAR(65535), "
            f"ADD COLUMN metadata VARCHAR(65535), "
            f"ADD COLUMN user_field_1 BOOLEAN DEFAULT FALSE, "
            f"ADD COLUMN user_field_2 INTEGER DEFAULT 0, "
            f"ADD COLUMN user_field_3 VARCHAR(65535) DEFAULT NULL, "
            f"ADD COLUMN status VARCHAR(10) CHECK (status IN ('ERROR', 'STATUS')), "
            f"ADD COLUMN error_message VARCHAR(65535)"
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

    def migrate_table_to_v2(self, table_name: str, column_name: str, engine: Any) -> None:
        
        sql_query = self.special_migration_query(table_name, column_name)
        super().migrate_table_to_v2(table_name, column_name, engine)
