import os
from typing import Any

import psycopg2
from psycopg2.extensions import connection
from unstract.connectors.databases.unstract_db import UnstractDB


class Redshift(UnstractDB):
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
        return (
            "/api/v1/static/icons/connector-icons/Redshift.png"
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

    def get_engine(self) -> connection:
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            options=f"-c search_path={self.schema}",
        )
