import datetime
import json
import os
from typing import Any

from google.cloud import bigquery
from google.cloud.bigquery import Client

from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError


class BigQuery(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("BigQuery")
        self.json_credentials = json.loads(
            settings.get("json_credentials", "{}")
        )

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
