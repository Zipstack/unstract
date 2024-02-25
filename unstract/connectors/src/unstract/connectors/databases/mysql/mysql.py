import os
from typing import Any

import pymysql
from pymysql.connections import Connection
from unstract.connectors.databases.unstract_db import UnstractDB


class MySQL(UnstractDB):
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
        return "https://storage.googleapis.com/pandora-static/connector-icons/MySql.png"

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

    def get_engine(self) -> Connection:  # type: ignore[type-arg]
        con = pymysql.connect(
            host=self.host,
            port=int(self.port),
            database=self.database,
            user=self.user,
            password=self.password,
        )
        return con
