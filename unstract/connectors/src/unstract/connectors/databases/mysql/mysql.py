import os
from typing import Any

import pymysql
from pymysql.connections import Connection

from unstract.connectors.databases.mysql_handler import MysqlHandler
from unstract.connectors.databases.unstract_db import UnstractDB


class MySQL(UnstractDB, MysqlHandler):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MySQL")

        self.user = settings.get("user")
        self.password = settings.get("password", "")
        self.host = settings.get("host")
        self.port = settings.get("port", 3306)
        self.database = settings.get("database")

    @staticmethod
    def get_id() -> str:
        return "mysql|db709852-fa51-4aa6-9b91-afc45f111bec"

    @staticmethod
    def get_name() -> str:
        return "MySQL"

    @staticmethod
    def get_description() -> str:
        return "MySQL Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/MySql.png"

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
        return "longtext"

    def get_engine(self) -> Connection:  # type: ignore[type-arg]
        con = pymysql.connect(
            host=self.host,
            port=int(self.port),
            database=self.database,
            user=self.user,
            password=self.password,
        )
        return con

    def sql_to_db_mapping(self, value: str) -> str:
        return str(MysqlHandler.sql_to_db_mapping(value=value))

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query with MySQL specific types.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id LONGTEXT, "
            f"created_by LONGTEXT, created_at TIMESTAMP, "
            f"metadata JSON, "
            f"user_field_1 BOOLEAN DEFAULT FALSE, "
            f"user_field_2 BIGINT DEFAULT 0, "
            f"user_field_3 LONGTEXT DEFAULT NULL, "
            f"status ENUM('ERROR', 'STATUS'), "
            f"error_message LONGTEXT, "
        )
        return sql_query

    def migrate_table_to_v2_query(self, table_name: str, column_name: str) -> str:
        sql_query = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name}_v2 JSON, "
            f"ADD COLUMN metadata JSON, "
            f"ADD COLUMN user_field_1 BOOLEAN DEFAULT FALSE, "
            f"ADD COLUMN user_field_2 BIGINT DEFAULT 0, "
            f"ADD COLUMN user_field_3 LONGTEXT DEFAULT NULL, "
            f"ADD COLUMN status ENUM('ERROR', 'STATUS'), "
            f"ADD COLUMN error_message LONGTEXT"
        )
        return sql_query

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        table_name = kwargs.get("table_name", None)
        MysqlHandler.execute_query(
            engine=engine,
            sql_query=sql_query,
            sql_values=sql_values,
            database=self.database,
            host=self.host,
            table_name=table_name,
        )
