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
            value (str): python datatype

        Returns:
            str: database columntype
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
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id TEXT , "
            f"created_by TEXT, created_at TIMESTAMP, "
        )
        return sql_query

    def create_table_query(self, table: str, database_entry: dict[str, Any]) -> Any:
        """Function to create a create table sql query.

        Args:
            table (str): db-connector table name
            database_entry (dict[str, Any]): a dictionary of column name and types

        Returns:
            Any: generates a create sql query for all the columns
        """
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
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names

        Returns:
            str: returns a string with parameterised insert sql query
        """
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @abstractmethod
    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        """Executes create/insert query.

        Args:
            engine (Any): big query client engine
            sql_query (str): sql create table/insert into table query
            sql_values (Any): sql data to be insertteds
        """
        pass

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        """Function to generate information schema of the corresponding table.

        Args:
            table_name (str): db-connector table name

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        table_name = str.lower(table_name)
        query = (
            "SELECT column_name, data_type FROM "
            "information_schema.columns WHERE "
            f"table_name = '{table_name}'"
        )
        results = self.execute(query=query)
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types

    def get_db_column_types(self, columns_with_types: Any) -> dict[str, str]:
        """Converts db results columns_with_types to dict.

        Args:
            columns_with_types (Any): database information schema array

        Returns:
            dict[str, str]: a dictionary containing db column-name and column-type
        """
        column_types: dict[str, str] = {}
        for column_name, data_type in columns_with_types:
            column_types[column_name] = data_type
        return column_types
