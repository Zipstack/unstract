import datetime
import logging
from abc import ABC, abstractmethod
from typing import Any

from unstract.connectors.base import UnstractConnector
from unstract.connectors.enums import ConnectorMode
from unstract.connectors.exceptions import ConnectorError


class UnstractDB(UnstractConnector, ABC):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return False

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.DATABASE

    @staticmethod
    def requires_oauth() -> bool:
        return False

    # TODO: Can be removed if removed from base class
    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @abstractmethod
    def get_engine(self) -> Any:
        pass

    def test_credentials(self) -> bool:
        """To test credentials for a DB connector."""
        try:
            self.get_engine()
        except Exception as e:
            raise ConnectorError(f"Error while connecting to DB: {str(e)}") from e
        return True

    def execute(self, query: str) -> Any:
        try:
            with self.get_engine().cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            raise ConnectorError(str(e)) from e

    def sql_to_db_mapping(self, value: str) -> str:
        """
        Gets the python datatype of value and converts python datatype
        to corresponding DB datatype
        Args:
            value (str): _description_

        Returns:
            str: _description_
        """
        python_type = type(value)
        mapping = {
            str: "TEXT",
            int: "INT",
            float: "FLOAT",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "TEXT")

    def get_create_table_base_query(self, table: str) -> str:
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id TEXT , "
            f"created_by TEXT, created_at TIMESTAMP, "
        )
        return sql_query

    def create_table_query(self, table: str, database_entry: dict[str, Any]) -> Any:
        PERMANENT_COLUMNS = ["created_by", "created_at"]

        sql_query = ""
        create_table_query = self.get_create_table_base_query(table=table)
        sql_query += create_table_query

        for key, val in database_entry.items():
            if key not in PERMANENT_COLUMNS:
                sql_type = self.sql_to_db_mapping(val)
                sql_query += f"{key} {sql_type}, "

        return sql_query.rstrip(", ") + ")"

    @staticmethod
    def get_sql_insert_query(table_name: str, sql_keys: list[str]) -> str:
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @staticmethod
    def get_sql_insert_values(sql_values: list[Any], **kwargs: Any) -> Any:
        return sql_values

    @abstractmethod
    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        pass
