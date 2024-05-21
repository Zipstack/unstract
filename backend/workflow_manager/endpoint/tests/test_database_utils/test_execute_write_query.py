import datetime
import os
import uuid
from typing import Any

import pytest  # type: ignore
from workflow_manager.endpoint.database_utils import DatabaseUtils

from unstract.connectors.databases.postgresql import PostgreSQL
from unstract.connectors.databases.redshift import Redshift
from unstract.connectors.databases.unstract_db import UnstractDB


class TestExecuteWriteQuery:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
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

    @pytest.fixture(
        params=[
            ("valid_postgres_creds", PostgreSQL),
            ("valid_redshift_creds", Redshift),
        ]
    )
    def valid_dbs_instance(self, request: Any) -> Any:
        return self.get_db_instance(request=request)

    def get_db_instance(self, request: Any) -> UnstractDB:
        creds_name, db_class = request.param
        creds = getattr(self, creds_name)
        if not creds:
            pytest.fail(f"Unknown credentials: {creds_name}")
        db_instance = db_class(settings=creds)
        return db_instance

    @pytest.fixture(
        params=[
            ("invalid_postgres_creds", PostgreSQL),
            ("invalid_redshift_creds", Redshift),
        ]
    )
    def invalid_dbs_instance(self, request: Any) -> Any:
        return self.get_db_instance(request=request)

    def test_execute_write_query(self, valid_dbs_instance: Any) -> None:
        cls_name = valid_dbs_instance.__class__.__name__
        sql_columns_and_values = {
            "created_by": "Unstract/DBWriter",
            "created_at": "2024-05-20 10:36:25.362609",
            "data": '{"input_file": "simple.pdf", "result": "report"}',
            "id": str(uuid.uuid4()),
        }
        engine = valid_dbs_instance.get_engine()

        result = DatabaseUtils.execute_write_query(
            engine=engine,
            cls_name=cls_name,
            table_name=self.valid_table_name,
            sql_keys=list(sql_columns_and_values.keys()),
            sql_values=list(sql_columns_and_values.values()),
        )

        assert result is None


if __name__ == "__main__":
    pytest.main()
