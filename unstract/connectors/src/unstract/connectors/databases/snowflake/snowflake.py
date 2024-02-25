import os
from typing import Any

import snowflake.connector
from snowflake.connector.connection import SnowflakeConnection
from unstract.connectors.databases.unstract_db import UnstractDB


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
        return (
            "https://storage.googleapis.com/pandora-static"
            "/connector-icons/Snowflake.png"
        )

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
