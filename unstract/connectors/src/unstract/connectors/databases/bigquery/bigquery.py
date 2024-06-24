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
)
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class BigQuery(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("BigQuery")
        self.json_credentials = json.loads(settings.get("json_credentials", "{}"))

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

    @staticmethod
    def sql_to_db_mapping(value: str) -> str:
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

    @staticmethod
    def get_create_table_query(table: str) -> str:
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id string,"
            f"created_by string, created_at TIMESTAMP, "
        )
        return sql_query

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
