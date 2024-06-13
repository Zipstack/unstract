import logging
import os
from typing import Any

import pymssql
import pymssql._pymssql as PyMssql
from pymssql import Connection  # type: ignore

from unstract.connectors.databases.exceptions import InvalidSyntaxException
from unstract.connectors.databases.exceptions_helper import ExceptionHelper
from unstract.connectors.databases.unstract_db import UnstractDB

logger = logging.getLogger(__name__)


class MSSQL(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MSSQL")

        self.user = settings.get("user")
        self.password = settings.get("password")
        self.server = settings.get("server")
        self.port = settings.get("port")
        self.database = settings.get("database")

    @staticmethod
    def get_id() -> str:
        return "mssql|6c6af35c-9498-4bd6-9258-23b5337e068b"

    @staticmethod
    def get_name() -> str:
        return "MSSQL"

    @staticmethod
    def get_description() -> str:
        return "MSSQL Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/MSSQL.png"

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

    def get_engine(self) -> Connection:
        return pymssql.connect(  # type: ignore
            server=self.server,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
        )

    @staticmethod
    def get_create_table_query(table: str) -> str:
        sql_query = (
            f"IF NOT EXISTS ("
            f"SELECT * FROM sysobjects WHERE name='{table}' and xtype='U')"
            f" CREATE TABLE {table} "
            f"(id TEXT ,"
            f"created_by TEXT, created_at DATETIMEOFFSET, "
        )
        return sql_query

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        try:
            with engine.cursor() as cursor:
                if sql_values:
                    cursor.execute(sql_query, sql_values)
                else:
                    cursor.execute(sql_query)
            engine.commit()
        except (PyMssql.ProgrammingError, PyMssql.OperationalError) as e:
            error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(
                f"Invalid syntax in creating/inserting mssql data: {error_details}"
            )
            raise InvalidSyntaxException(
                detail=error_details, database=self.database
            ) from e
