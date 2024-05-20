import datetime
import os
import uuid
from typing import Any

import pytest  # type: ignore
from workflow_manager.endpoint.constants import DBConnectionClass
from workflow_manager.endpoint.database_utils import DatabaseUtils

from unstract.connectors.databases.postgresql import PostgreSQL
from unstract.connectors.databases.unstract_db import UnstractDB


class TestDatabaseUtils:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.postgres_creds = {
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "database": os.getenv("DB_NAME"),
            "schema": "public",
        }
        self.snowflake_creds = {
            "user": os.getenv("DB_USER_1"),
            "password": os.getenv("DB_PASSWORD_1"),
        }
        self.table_name = "test_output"

    @pytest.fixture
    def db_instance(self) -> Any:
        if self.postgres_creds:
            return PostgreSQL(settings=self.postgres_creds)
        # elif self.snowflake_creds:
        #     return Snowflake(settings=self.snowflake_creds)
        else:
            raise ValueError("Unknown credentials")

    def test_create_table_if_not_exists(self, db_instance: UnstractDB) -> None:
        engine = db_instance.get_engine()

        database_entry = {
            "created_by": "Unstract/DBWriter",
            "created_at": datetime.datetime(2024, 5, 20, 7, 46, 57, 307998),
            "data": '{"input_file": "simple.pdf", "result": "report"}',
        }
        result = DatabaseUtils.create_table_if_not_exists(
            db_class=db_instance,
            engine=engine,
            table_name=self.table_name,
            database_entry=database_entry,
        )

        assert result is None

    def test_execute_write_query(self, db_instance: Any) -> None:
        cls_name = DBConnectionClass.PostgreSQL
        sql_columns_and_values = {
            "created_by": "Unstract/DBWriter",
            "created_at": "2024-05-20 10:36:25.362609",
            "data": '{"input_file": "simple.pdf", "result": "report"}',
            "id": str(uuid.uuid4()),
        }
        engine = db_instance.get_engine()

        result = DatabaseUtils.execute_write_query(
            engine=engine,
            cls_name=cls_name,
            table_name=self.table_name,
            sql_keys=list(sql_columns_and_values.keys()),
            sql_values=list(sql_columns_and_values.values()),
        )

        assert result is None


if __name__ == "__main__":
    pytest.main()
