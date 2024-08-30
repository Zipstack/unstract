import datetime
import json
import os
from typing import Any

import pytest  # type: ignore
from dotenv import load_dotenv

from unstract.connectors.databases.bigquery import BigQuery
from unstract.connectors.databases.mariadb import MariaDB
from unstract.connectors.databases.mssql import MSSQL
from unstract.connectors.databases.mysql import MySQL
from unstract.connectors.databases.postgresql import PostgreSQL
from unstract.connectors.databases.redshift import Redshift
from unstract.connectors.databases.snowflake import SnowflakeDB
from unstract.connectors.databases.unstract_db import UnstractDB

load_dotenv("test.env")


class BaseTestDB:
    @pytest.fixture(autouse=True)
    def base_setup(self) -> None:
        self.postgres_creds = {
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "database": os.getenv("DB_NAME"),
        }
        self.redshift_creds = {
            "user": os.getenv("REDSHIFT_USER"),
            "password": os.getenv("REDSHIFT_PASSWORD"),
            "host": os.getenv("REDSHIFT_HOST"),
            "port": os.getenv("REDSHIFT_PORT"),
            "database": os.getenv("REDSHIFT_DB"),
        }
        self.snowflake_creds = {
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "database": os.getenv("SNOWFLAKE_DB"),
            "schema": os.getenv("SNOWFLAKE_SCHEMA"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        }
        self.mssql_creds = {
            "user": os.getenv("MSSQL_USER"),
            "password": os.getenv("MSSQL_PASSWORD"),
            "server": os.getenv("MSSQL_SERVER"),
            "port": os.getenv("MSSQL_PORT"),
            "database": os.getenv("MSSQL_DB"),
        }
        self.mysql_creds = {
            "user": os.getenv("MYSQL_USER"),
            "password": os.getenv("MYSQL_PASSWORD"),
            "host": os.getenv("MYSQL_SERVER"),
            "port": os.getenv("MYSQL_PORT"),
            "database": os.getenv("MYSQL_DB"),
        }
        self.mariadb_creds = {
            "user": os.getenv("MARIADB_USER"),
            "password": os.getenv("MARIADB_PASSWORD"),
            "host": os.getenv("MARIADB_SERVER"),
            "port": os.getenv("MARIADB_PORT"),
            "database": os.getenv("MARIADB_DB"),
        }
        self.database_entry = {
            "created_by": "Unstract/DBWriter",
            "created_at": datetime.datetime(2024, 5, 20, 7, 46, 57, 307998),
            "data": '{"input_file": "simple.pdf", "result": "report"}',
        }
        valid_schema_name = "public"
        invalid_schema_name = "public_1"
        self.valid_postgres_creds = {**self.postgres_creds, "schema": valid_schema_name}
        self.invalid_postgres_creds = {
            **self.postgres_creds,
            "schema": invalid_schema_name,
        }
        self.valid_redshift_creds = {**self.redshift_creds, "schema": valid_schema_name}
        self.invalid_redshift_creds = {
            **self.redshift_creds,
            "schema": invalid_schema_name,
        }
        self.invalid_syntax_table_name = "invalid-syntax.name.test_output"
        self.invalid_wrong_table_name = "database.schema.test_output"
        self.valid_table_name = "test_output"
        bigquery_json_str = os.getenv("BIGQUERY_CREDS", "{}")
        self.bigquery_settings = json.loads(bigquery_json_str)
        self.bigquery_settings["json_credentials"] = bigquery_json_str
        self.valid_bigquery_table_name = "unstract.bigquery_test.bigquery_output"
        self.invalid_snowflake_db = {**self.snowflake_creds, "database": "invalid"}
        self.invalid_snowflake_schema = {**self.snowflake_creds, "schema": "invalid"}
        self.invalid_snowflake_warehouse = {
            **self.snowflake_creds,
            "warehouse": "invalid",
        }

    # Gets all valid db instances except
    # Bigquery (table name needs to be writted separately for bigquery)
    @pytest.fixture(
        params=[
            ("valid_postgres_creds", PostgreSQL),
            ("snowflake_creds", SnowflakeDB),
            ("mssql_creds", MSSQL),
            ("mysql_creds", MySQL),
            ("mariadb_creds", MariaDB),
            ("valid_redshift_creds", Redshift),
        ]
    )
    def valid_dbs_instance(self, request: Any) -> Any:
        return self.get_db_instance(request=request)

    # Gets all valid db instances except:
    # Bigquery (table name needs to be writted separately for bigquery)
    # Redshift (can't process more than 64KB character type)
    @pytest.fixture(
        params=[
            ("valid_postgres_creds", PostgreSQL),
            ("snowflake_creds", SnowflakeDB),
            ("mssql_creds", MSSQL),
            ("mysql_creds", MySQL),
            ("mariadb_creds", MariaDB),
        ]
    )
    def valid_dbs_instance_to_handle_large_doc(self, request: Any) -> Any:
        return self.get_db_instance(request=request)

    def get_db_instance(self, request: Any) -> UnstractDB:
        creds_name, db_class = request.param
        creds = getattr(self, creds_name)
        if not creds:
            pytest.fail(f"Unknown credentials: {creds_name}")
        db_instance = db_class(settings=creds)
        return db_instance

    # Gets all invalid-db instances for postgres, redshift:
    @pytest.fixture(
        params=[
            ("invalid_postgres_creds", PostgreSQL),
            ("invalid_redshift_creds", Redshift),
        ]
    )
    def invalid_dbs_instance(self, request: Any) -> Any:
        return self.get_db_instance(request=request)

    @pytest.fixture
    def valid_bigquery_db_instance(self) -> Any:
        return BigQuery(settings=self.bigquery_settings)

    # Gets all invalid-db instances for snowflake:
    @pytest.fixture(
        params=[
            ("invalid_snowflake_db", SnowflakeDB),
            ("invalid_snowflake_schema", SnowflakeDB),
            ("invalid_snowflake_warehouse", SnowflakeDB),
        ]
    )
    def invalid_snowflake_db_instance(self, request: Any) -> Any:
        return self.get_db_instance(request=request)
