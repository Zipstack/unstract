import os
from typing import Any

import pymssql
from pymssql import Connection

from unstract.connectors.databases.unstract_db import UnstractDB


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
        if self.port:
            return pymssql.connect(
                server=self.server,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
        return pymssql.connect(
            server=self.server,
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
