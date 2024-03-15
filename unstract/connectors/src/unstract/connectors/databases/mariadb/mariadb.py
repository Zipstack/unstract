import os
from typing import Any

import pymysql
from pymysql.connections import Connection

from unstract.connectors.databases.unstract_db import UnstractDB


class MariaDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("MariaDB")

        self.user = settings.get("user")
        self.password = settings.get("password", "")
        self.host = settings.get("host")
        self.port = settings.get("port", 3306)
        self.database = settings.get("database")

    @staticmethod
    def get_id() -> str:
        return "mariadb|146b0124-b9fc-466f-8e68-098ff60703e8"

    @staticmethod
    def get_name() -> str:
        return "MariaDB"

    @staticmethod
    def get_description() -> str:
        return "MariaDB Database"

    @staticmethod
    def get_icon() -> str:
        return "https://storage.googleapis.com/\
            pandora-static/connector-icons/MariaDB.png"

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
