from typing import Any

from google.cloud import bigquery
from workflow_manager.endpoint.constants import DBConnectionClass, TableColumns

from unstract.connectors.databases.unstract_db import UnstractDB


class DBConnectorQueryHelper:
    """A class that helps to generate query for connector table operations."""

    @staticmethod
    def create_table_query(
        conn_cls: UnstractDB, table: str, database_entry: dict[str, Any]
    ) -> Any:
        sql_query = ""
        """Generate a SQL query to create a table, based on the provided
        database entry.

        Args:
            conn_cls (str): The database connector class.
                Should be one of 'BIGQUERY', 'SNOWFLAKE', or other.
            table (str): The name of the table to be created.
            database_entry (dict[str, Any]):
                A dictionary containing column names as keys
                and their corresponding values.

                These values are used to determine the data types,
                for the columns in the table.

        Returns:
            str: A SQL query string to create a table with the specified name,
            and column definitions.

        Note:
            - Each conn_cls have it's implementation for SQL create table query
            Based on the implementation, a base SQL create table query will be
            created containing Permanent columns
            - Each conn_cls also has a mapping to convert python datatype to
            corresponding column type (string, VARCHAR etc)
            - keys in database_entry will be converted to column type, and
            column values will be the valus in database_entry
            - base SQL create table will be appended based column type and
            values, and generates a complete SQL create table query
        """
        create_table_query = conn_cls.get_create_table_query(table=table)
        sql_query += create_table_query

        for key, val in database_entry.items():
            if key not in TableColumns.PERMANENT_COLUMNS:
                sql_type = conn_cls.sql_to_db_mapping(val)
                sql_query += f"{key} {sql_type}, "

        return sql_query.rstrip(", ") + ");"

    @staticmethod
    def build_sql_insert_query(
        cls_name: str, table_name: str, sql_keys: list[str]
    ) -> str:
        keys_str = ",".join(sql_keys)
        if cls_name == DBConnectionClass.BIGQUERY:
            values_placeholder = ",".join(["@" + key for key in sql_keys])
        else:
            values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @staticmethod
    def prepare_sql_values(cls_name: str, sql_values: Any, sql_keys: list[str]) -> Any:
        if cls_name == DBConnectionClass.MSSQL:
            return tuple(sql_values)
        elif cls_name == DBConnectionClass.BIGQUERY:
            query_parameters = [
                bigquery.ScalarQueryParameter(key, "STRING", value)
                for key, value in zip(sql_keys, sql_values)
            ]
            return bigquery.QueryJobConfig(query_parameters=query_parameters)
        return sql_values
