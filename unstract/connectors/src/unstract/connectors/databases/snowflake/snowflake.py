import logging
import os
from typing import Any

import snowflake.connector
import snowflake.connector.errors as SnowflakeError
from snowflake.connector.connection import SnowflakeConnection

from unstract.connectors.databases.exceptions import SnowflakeProgrammingException
from unstract.connectors.databases.unstract_db import UnstractDB

logger = logging.getLogger(__name__)


class SnowflakeDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Snowflake")

        self.user = settings["user"]
        self.password = settings["password"]
        self.account = settings["account"]
        self.database = settings["database"]
        self.schema = settings["schema"]
        self.warehouse = settings["warehouse"]
        self.role = settings["role"]

    @staticmethod
    def get_id() -> str:
        return "snowflake|87c5151e-5e41-420a-b1ea-772d9720929b"

    @staticmethod
    def get_name() -> str:
        return "Snowflake"

    @staticmethod
    def get_description() -> str:
        return "Snowflake Data Warehouse"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Snowflake.png"

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

    def get_engine(self) -> SnowflakeConnection:
        con = snowflake.connector.connect(
            user=self.user,
            password=self.password,
            account=self.account,
            database=self.database,
            schema=self.schema,
            warehouse=self.warehouse,
            role=self.role,
        )
        return con

    def get_create_table_base_query(self, table: str) -> str:
        sql_query = (
            f"CREATE TABLE {table} IF NOT EXISTS "
            f"(id TEXT ,"
            f"created_by TEXT, created_at TIMESTAMP, "
        )
        return sql_query

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        table_name = kwargs.get("table_name", None)
        try:
            with engine.cursor() as cursor:
                if sql_values:
                    cursor.execute(sql_query, sql_values)
                else:
                    cursor.execute(sql_query)
            engine.commit()
        except SnowflakeError.ProgrammingError as e:
            logger.error(
                f"snowflake programming error in crearing/inserting table: "
                f"{e.msg} {e.errno}"
            )
            raise SnowflakeProgrammingException(
                detail=e.msg,
                database=self.database,
                schema=self.schema,
                table_name=table_name,
            ) from e

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        query = f"describe table {table_name}"
        column_types: dict[str, str] = {}
        results = self.execute(query=query)
        for column in results:
            column_types[column[0].lower()] = column[1].split("(")[0]
        return column_types
