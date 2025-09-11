import datetime
import os
from typing import Any

import oracledb
from oracledb.connection import Connection
from workflow_manager.endpoint_v2.exceptions import UnstractDBException

from unstract.connectors.databases.unstract_db import UnstractDB


class OracleDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("OracleDB")

        self.config_dir = settings.get("config_dir", "/opt/OracleCloud/MYDB")
        self.user = settings.get("user", "admin")
        self.password = settings.get("password", "")
        self.dsn = settings.get("dsn", "")
        self.wallet_location = settings.get("wallet_location", "/opt/OracleCloud/MYDB")
        self.wallet_password = settings.get("wallet_password", "")
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

    def get_string_type(self) -> str:
        return "VARCHAR2(32767)"

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
            str: "VARCHAR2(32767)",
            int: "NUMBER",
            float: "LONG",
            datetime.datetime: "TIMESTAMP",
            dict: "CLOB",
            list: "VARCHAR2(32767)",
        }
        return mapping.get(python_type, "VARCHAR2(32767)")

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE {table} "
            f"(id VARCHAR2(32767) , "
            f"created_by VARCHAR2(32767), created_at TIMESTAMP, "
            f"metadata CLOB, "
            f"user_field_1 NUMBER(1) DEFAULT 0, "
            f"user_field_2 NUMBER DEFAULT 0, "
            f"user_field_3 VARCHAR2(32767) DEFAULT NULL, "
            f"status VARCHAR2(10), "
            f"error_message VARCHAR2(32767), "
        )
        return sql_query

    def create_table_query(self, table: str, database_entry: dict[str, Any]) -> str:
        """Function to create a create table sql query with Oracle-specific handling.

        Args:
            table (str): db-connector table name
            database_entry (dict[str, Any]): a dictionary of column name and types

        Returns:
            str: generates a create sql query for all the columns, or empty string if table exists

        Raises:
            UnstractDBException: If there's an error checking table existence
        """
        try:
            # Check if table already exists using Oracle's user_tables
            query = (
                f"SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER('{table}')"
            )
            results = self.execute(query=query)

            # If table exists, return empty string to skip creation
            if results and results[0][0] > 0:
                return ""

            # Table doesn't exist - return CREATE TABLE query
            result = super().create_table_query(table, database_entry)
            return str(result) if result else ""

        except Exception as e:
            # If there's an error checking table existence, raise UnstractDBException
            raise UnstractDBException(
                detail=f"Error checking table existence: {str(e)}"
            ) from e

    def prepare_multi_column_migration(self, table_name: str, column_name: str) -> list:
        """Prepare ALTER TABLE statements for adding new columns to an existing table.

        Args:
            table_name (str): The name of the table to alter
            column_name (str): The base name of the column to add a _v2 version for

        Returns:
            list: List of ALTER TABLE statements, one per column addition

        Note:
            Oracle does not support multiple ADD clauses in a single ALTER TABLE statement.
            Each column addition requires a separate ALTER TABLE statement.
        """
        # Return one ALTER statement per column for Oracle compatibility
        return [
            f"ALTER TABLE {table_name} ADD {column_name}_v2 VARCHAR2(32767)",
            f"ALTER TABLE {table_name} ADD metadata CLOB",
            f"ALTER TABLE {table_name} ADD user_field_1 NUMBER(1) DEFAULT 0",
            f"ALTER TABLE {table_name} ADD user_field_2 NUMBER DEFAULT 0",
            f"ALTER TABLE {table_name} ADD user_field_3 VARCHAR2(32767) DEFAULT NULL",
            f"ALTER TABLE {table_name} ADD status VARCHAR2(10)",
            f"ALTER TABLE {table_name} ADD error_message VARCHAR2(32767)",
        ]

    @staticmethod
    def get_sql_insert_query(
        table_name: str, sql_keys: list[str], sql_values: list[str] | None = None
    ) -> str:
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names
            sql_values (list[str], optional): SQL values for database-specific handling (ignored for Oracle)

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
                params = dict(zip(sql_keys, sql_values, strict=False))
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
