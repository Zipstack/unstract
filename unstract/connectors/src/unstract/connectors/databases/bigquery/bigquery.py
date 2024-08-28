import datetime
import json
import logging
import os
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
            str: "string",
            int: "INT64",
            float: "FLOAT64",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "string")

    def get_create_table_base_query(self, table: str) -> str:
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id string,"
            f"created_by string, created_at TIMESTAMP, "
        )
        return sql_query

    @staticmethod
    def get_sql_insert_query(table_name: str, sql_keys: list[str]) -> str:
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["@" + key for key in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @staticmethod
    def get_sql_insert_values(sql_values: list[Any], **kwargs: Any) -> Any:
        sql_keys = str(kwargs.get("sql_keys"))
        query_parameters = [
            bigquery.ScalarQueryParameter(key, "STRING", value)
            for key, value in zip(sql_keys, sql_values)
        ]
        return bigquery.QueryJobConfig(query_parameters=query_parameters)

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        table_name = str(kwargs.get("table_name"))
        try:
            if sql_values:
                query_job = engine.query(sql_query, job_config=sql_values)
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
        bigquery_table_name = str.lower(table_name).split(".")
        if len(bigquery_table_name) != self.big_query_table_size:
            raise ValueError(
                f"Invalid table name format: '{table_name}'. "
                f"Expected {self.big_query_table_size} components separated by '.'"
            )
        database = bigquery_table_name[0]
        schema = bigquery_table_name[1]
        table = bigquery_table_name[2]
        query = (
            "SELECT column_name, data_type FROM "
            f"{database}.{schema}.INFORMATION_SCHEMA.COLUMNS WHERE "
            f"table_name = '{table}'"
        )
        results = self.execute(query=query)
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types
