import datetime
import os
from typing import Any

import oracledb
from oracledb.connection import Connection

from unstract.connectors.databases.unstract_db import UnstractDB


class OracleDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("OracleDB")

        self.config_dir = settings.get("config_dir", None)
        self.user = settings.get("user", None)
        self.password = settings.get("password", None)
        self.dsn = settings.get("dsn", None)
        self.wallet_location = settings.get("wallet_location", None)
        self.wallet_password = settings.get("wallet_password", None)
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

    def sql_to_db_mapping(self, value: str) -> str:
        """Function to generate information schema of the corresponding table.

        Args:
            table_name (str): db-connector table name

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        python_type = type(value)
        mapping = {
            str: "CLOB",
            int: "NUMBER",
            float: "LONG",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "CLOB")

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id VARCHAR2(32767) , "
            f"created_by VARCHAR2(32767), created_at TIMESTAMP, "
        )
        return sql_query

    @staticmethod
    def get_sql_insert_query(table_name: str, sql_keys: list[str]) -> str:
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names

        Returns:
            str: returns a string with parameterised insert sql query
        """
        columns = ", ".join(sql_keys)
        values = []
        for key in sql_keys:
            if key == "created_at":
                values.append("TO_TIMESTAMP(:created_at, 'YYYY-MM-DD HH24:MI:SS.FF')")
            else:
                values.append(f":{key}")
        return f"INSERT INTO {table_name} ({columns}) VALUES ({', '.join(values)})"

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        """Executes create/insert query.

        Args:
            engine (Any): oracle db client engine
            sql_query (str): sql create table/insert into table query
            sql_values (Any): sql data to be insertted
        """
        sql_keys = list(kwargs.get("sql_keys", []))
        with engine.cursor() as cursor:
            if sql_values:
                params = dict(zip(sql_keys, sql_values))
                cursor.execute(sql_query, params)
            else:
                cursor.execute(sql_query)
            engine.commit()

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        """Function to generate information schema of the big query table.

        Args:
            table_name (str): db-connector table name

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        query = (
            "SELECT column_name, data_type FROM "
            "user_tab_columns WHERE "
            f"table_name = UPPER('{table_name}')"
        )
        results = self.execute(query=query)
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types
