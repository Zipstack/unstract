import datetime
import json
import logging
import os
import uuid
from enum import Enum
from typing import Any

import google.api_core.exceptions
from google.cloud import bigquery
from google.cloud.bigquery import Client

from unstract.connectors.databases.exceptions import (
    BigQueryForbiddenException,
    BigQueryNotFoundException,
    ColumnMissingException,
)
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)

# BigQuery table format 'database.schema.table' splits into an array of size 3
BIG_QUERY_TABLE_SIZE = 3


class BigQuery(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("BigQuery")
        self.json_credentials = json.loads(settings.get("json_credentials", "{}"))
        self.big_query_table_size = BIG_QUERY_TABLE_SIZE

    @staticmethod
    def get_id() -> str:
        return "bigquery|79e1d681-9b8b-4f6b-b972-1a6a095312f4"

    @staticmethod
    def get_name() -> str:
        return "BigQuery"

    @staticmethod
    def get_description() -> str:
        return "BigQuery Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Bigquery.png"

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

    def get_engine(self) -> Client:
        return bigquery.Client.from_service_account_info(  # type: ignore
            info=self.json_credentials
        )

    def execute(self, query: str) -> Any:
        try:
            query_job = self.get_engine().query(query)
            return query_job.result()
        except Exception as e:
            raise ConnectorError(str(e))

    def sql_to_db_mapping(self, value: Any, column_name: str | None = None) -> str:
        """Gets the python datatype of value and converts python datatype to
        corresponding DB datatype.

        Args:
            value (str): python datatype
            column_name (str | None): name of the column being mapped

        Returns:
            str: database columntype
        """
        python_type = type(value)

        if python_type in (dict, list):
            if column_name and column_name.endswith("_v2"):
                return "JSON"
            else:
                return "STRING"

        mapping = {
            str: "STRING",
            int: "INT64",
            float: "FLOAT64",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "STRING")

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name
            Format  {database}.{schema}.{table}

        Returns:
            str: generates a create sql base query with the constant columns
        """
        bigquery_table_parts = table.split(".")
        if len(bigquery_table_parts) != self.big_query_table_size:
            raise ValueError(
                f"Invalid table name format: '{table}'. "
                "Please ensure the BigQuery table is in the form of "
                "{database}.{schema}.{table}."
            )
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id STRING,"
            f"created_by STRING, created_at TIMESTAMP, "
            f"metadata JSON, "
            f"user_field_1 BOOL DEFAULT FALSE, "
            f"user_field_2 INT64 DEFAULT 0, "
            f"user_field_3 STRING DEFAULT NULL, "
            f"status STRING, "
            f"error_message STRING, "
        )
        return sql_query

    def prepare_multi_column_migration(self, table_name: str, column_name: str) -> str:
        sql_query = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name}_v2 JSON, "
            f"ADD COLUMN metadata JSON, "
            f"ADD COLUMN user_field_1 BOOL, "
            f"ADD COLUMN user_field_2 INT64, "
            f"ADD COLUMN user_field_3 STRING, "
            f"ADD COLUMN status STRING, "
            f"ADD COLUMN error_message STRING"
        )
        return sql_query

    @staticmethod
    def get_sql_insert_query(
        table_name: str, sql_keys: list[str], sql_values: list[str] | None = None
    ) -> str:
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names
            sql_values (list[str], optional): SQL values for database-specific handling

        Returns:
            str: returns a string with parameterised insert sql query
        """
        # BigQuery uses @ parameterization, ignore sql_values for now
        # Escape column names with backticks to handle special characters like underscores
        escaped_keys = [f"`{key}`" for key in sql_keys]
        keys_str = ",".join(escaped_keys)

        # Also escape parameter names with backticks to handle underscores in parameter names
        escaped_params = [f"@`{key}`" for key in sql_keys]
        values_placeholder = ",".join(escaped_params)
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        """Executes create/insert query.

        Args:
            engine (Any): big query client engine
            sql_query (str): sql create table/insert into table query
            sql_values (Any): sql data to be insertted

        Raises:
            BigQueryForbiddenException: raised due to insufficient permission
            BigQueryNotFoundException: raised due to unavailable resource
            ColumnMissingException: raised due to missing columns in table query
        """
        table_name = kwargs.get("table_name", None)
        if table_name is None:
            raise ValueError("Please enter a valid table_name to to create/insert table")

        sql_keys = list(kwargs.get("sql_keys", []))
        column_types = self.get_information_schema(table_name=table_name)

        try:
            if sql_values:
                query_parameters = []
                # Modify SQL query to use PARSE_JSON for JSON columns
                modified_sql = sql_query

                for key, value in zip(sql_keys, sql_values, strict=False):
                    column_type = column_types.get(key.lower(), "").upper()

                    if isinstance(value, (dict, list)) and column_type == "JSON":
                        # For JSON objects in JSON columns, convert to string and use PARSE_JSON
                        json_str = json.dumps(value) if value else None
                        if json_str:
                            # Replace @`key` with PARSE_JSON(@`key`) in the SQL query
                            modified_sql = modified_sql.replace(
                                f"@`{key}`", f"PARSE_JSON(@`{key}`)"
                            )
                        query_parameters.append(
                            bigquery.ScalarQueryParameter(key, "STRING", json_str)
                        )
                    elif isinstance(value, (dict, list)):
                        # For dict/list values in STRING columns, serialize to JSON string
                        json_str = json.dumps(value) if value else None
                        query_parameters.append(
                            bigquery.ScalarQueryParameter(key, "STRING", json_str)
                        )
                    else:
                        # For other values, use STRING as before
                        query_parameters.append(
                            bigquery.ScalarQueryParameter(key, "STRING", value)
                        )

                query_params = bigquery.QueryJobConfig(query_parameters=query_parameters)
                query_job = engine.query(modified_sql, job_config=query_params)
            else:
                query_job = engine.query(sql_query)
            query_job.result()
        except google.api_core.exceptions.Forbidden as e:
            logger.error(f"Forbidden exception in creating/inserting data: {str(e)}")
            raise BigQueryForbiddenException(
                detail=e.message,
                table_name=table_name,
            ) from e
        except google.api_core.exceptions.NotFound as e:
            logger.error(f"Resource not found in creating/inserting table: {str(e)}")
            raise BigQueryNotFoundException(
                detail=e.message, table_name=table_name
            ) from e
        except google.api_core.exceptions.BadRequest as e:
            logger.error(f"Column missing in inserting data: {str(e)}")
            db, schema, table = table_name.split(".")
            raise ColumnMissingException(
                detail=e.message,
                database=db,
                schema=schema,
                table_name=table,
            ) from e

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        """Function to generate information schema of the big query table.

        Args:
            table_name (str): db-connector table name
                              Format  {database}.{schema}.{table}

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        # Split table name but preserve case for table name part
        bigquery_table_parts = table_name.split(".")
        if len(bigquery_table_parts) != self.big_query_table_size:
            raise ValueError(
                f"Invalid table name format: '{table_name}'. "
                "Please ensure the BigQuery table is in the form of "
                "{database}.{schema}.{table}."
            )
        # Convert database and schema to lowercase, but preserve table name case
        database = bigquery_table_parts[0].lower()
        schema = bigquery_table_parts[1].lower()
        table = bigquery_table_parts[2]  # Preserve original case
        query = (
            "SELECT column_name, data_type FROM "
            f"{database}.{schema}.INFORMATION_SCHEMA.COLUMNS WHERE "
            f"table_name = '{table}'"
        )
        results = self.execute(query=query)

        # If table doesn't exist, execute returns None
        if results is None:
            logger.info(f"Table {table_name} does not exist, returning empty schema")
            return {}

        # Process the schema results
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types

    def get_sql_values_for_query(
        self, values: dict[str, Any], column_types: dict[str, str]
    ) -> dict[str, str]:
        """Prepare SQL values for BigQuery queries with JSON column support.

        Args:
            values (dict[str, Any]): dictionary of columns and values
            column_types (dict[str, str]): types of columns from database schema

        Returns:
            dict[str, str]: Dictionary of column names to SQL values for parameterized queries
        """
        sql_values: dict[str, Any] = {}
        for column in values:
            value = values[column]
            if isinstance(value, (dict, list)):
                # For BigQuery, keep dict/list objects as-is for JSON columns
                sql_values[column] = value
            elif isinstance(value, str):
                # Try to parse JSON strings back to objects for BigQuery
                try:
                    parsed_value = json.loads(value)
                    sql_values[column] = parsed_value
                except (TypeError, ValueError, json.JSONDecodeError):
                    # Not a JSON string, keep as string
                    sql_values[column] = f"{value}"
            elif isinstance(value, Enum):
                sql_values[column] = value.value
            else:
                sql_values[column] = f"{value}"

        # If table has a column 'id', unstract inserts a unique value to it
        if any(key in column_types for key in ["id", "ID"]):
            uuid_id = str(uuid.uuid4())
            sql_values["id"] = f"{uuid_id}"

        return sql_values
