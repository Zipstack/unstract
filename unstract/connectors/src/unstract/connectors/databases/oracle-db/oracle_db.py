import os
from typing import Any

import oracledb
from oracledb.connection import Connection

from unstract.connectors.databases.unstract_db import UnstractDB


class OracleDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("OracleDB")

        self.config_dir = settings["config_dir"]
        self.user = settings["user"]
        self.password = settings["password"]
        self.dsn = settings["dsn"]
        self.wallet_location = settings["wallet_location"]
        self.wallet_password = settings["wallet_password"]
        if not (
            self.config_dir
            and self.user
            and self.password
            and self.dsn
            and self.wallet_location
            and self.wallet_password
        ):
            raise ValueError("Ensure all connection parameters are provided.")

    @staticmethod
    def get_id() -> str:
        return "oracledb|49e3b4c1-9c34-43fc-89a4-96950821ade0"

    @staticmethod
    def get_name() -> str:
        return "OracleDB"

    @staticmethod
    def get_description() -> str:
        return "oracledb Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Oracle.png"

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
        con = oracledb.connect(
            config_dir=self.config_dir,
            user=self.user,
            password=self.password,
            dsn=self.dsn,
            wallet_location=self.wallet_location,
            wallet_password=self.wallet_password,
        )
        return con

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        pass
