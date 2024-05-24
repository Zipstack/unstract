import os
import uuid
from typing import Any

import pytest  # type: ignore
from base_test_db import BaseTestDB
from dotenv import load_dotenv
from workflow_manager.endpoint.database_utils import DatabaseUtils
from workflow_manager.endpoint.exceptions import (
    FeatureNotSupportedException,
    InvalidSyntaxException,
    SnowflakeProgrammingException,
    UnderfinedTableException,
    ValueTooLongException,
)

from unstract.connectors.databases.redshift import Redshift
from unstract.connectors.databases.unstract_db import UnstractDB

load_dotenv("test.env")


class TestExecuteWriteQuery(BaseTestDB):
    @pytest.fixture(autouse=True)
    def setup(self, base_setup: Any) -> None:
        self.sql_columns_and_values = {
            "created_by": "Unstract/DBWriter",
            "created_at": "2024-05-20 10:36:25.362609",
            "data": '{"input_file": "simple.pdf", "result": "report"}',
            "id": str(uuid.uuid4()),
        }

    def test_execute_write_query_valid(self, valid_dbs_instance: Any) -> None:
        cls_name = valid_dbs_instance.__class__.__name__
        engine = valid_dbs_instance.get_engine()
        result = DatabaseUtils.execute_write_query(
            engine=engine,
            cls_name=cls_name,
            table_name=self.valid_table_name,
            sql_keys=list(self.sql_columns_and_values.keys()),
            sql_values=list(self.sql_columns_and_values.values()),
        )
        assert result is None

    def test_execute_write_query_invalid_schema(
        self, invalid_dbs_instance: Any
    ) -> None:
        cls_name = invalid_dbs_instance.__class__.__name__
        engine = invalid_dbs_instance.get_engine()
        with pytest.raises(UnderfinedTableException):
            DatabaseUtils.execute_write_query(
                engine=engine,
                cls_name=cls_name,
                table_name=self.valid_table_name,
                sql_keys=list(self.sql_columns_and_values.keys()),
                sql_values=list(self.sql_columns_and_values.values()),
            )

    def test_execute_write_query_invalid_syntax(self, valid_dbs_instance: Any) -> None:
        cls_name = valid_dbs_instance.__class__.__name__
        engine = valid_dbs_instance.get_engine()
        with pytest.raises((InvalidSyntaxException, SnowflakeProgrammingException)):
            DatabaseUtils.execute_write_query(
                engine=engine,
                cls_name=cls_name,
                table_name=self.invalid_syntax_table_name,
                sql_keys=list(self.sql_columns_and_values.keys()),
                sql_values=list(self.sql_columns_and_values.values()),
            )

    def test_execute_write_query_feature_not_supported(
        self, invalid_dbs_instance: Any
    ) -> None:
        cls_name = invalid_dbs_instance.__class__.__name__
        engine = invalid_dbs_instance.get_engine()
        with pytest.raises(FeatureNotSupportedException):
            DatabaseUtils.execute_write_query(
                engine=engine,
                cls_name=cls_name,
                table_name=self.invalid_wrong_table_name,
                sql_keys=list(self.sql_columns_and_values.keys()),
                sql_values=list(self.sql_columns_and_values.values()),
            )

    def load_text_to_sql_values(self) -> dict[str, Any]:
        file_path = os.path.join(os.path.dirname(__file__), "static", "large_doc.txt")
        with open(file_path, encoding="utf-8") as file:
            content = file.read()
        sql_columns_and_values = self.sql_columns_and_values.copy()
        sql_columns_and_values["data"] = content
        return sql_columns_and_values

    @pytest.fixture
    def valid_redshift_db_instance(self) -> Any:
        return Redshift(self.valid_redshift_creds)

    def test_execute_write_query_datatype_too_large_redshift(
        self, valid_redshift_db_instance: Any
    ) -> None:
        sql_columns_and_values = self.load_text_to_sql_values()
        cls_name = valid_redshift_db_instance.__class__.__name__
        engine = valid_redshift_db_instance.get_engine()
        with pytest.raises(ValueTooLongException):
            DatabaseUtils.execute_write_query(
                engine=engine,
                cls_name=cls_name,
                table_name=self.valid_table_name,
                sql_keys=list(sql_columns_and_values.keys()),
                sql_values=list(sql_columns_and_values.values()),
            )

    def test_execute_write_query_bigquery_valid(
        self, valid_bigquery_db_instance: Any
    ) -> None:
        cls_name = valid_bigquery_db_instance.__class__.__name__
        engine = valid_bigquery_db_instance.get_engine()
        result = DatabaseUtils.execute_write_query(
            engine=engine,
            cls_name=cls_name,
            table_name=self.valid_bigquery_table_name,
            sql_keys=list(self.sql_columns_and_values.keys()),
            sql_values=list(self.sql_columns_and_values.values()),
        )
        assert result is None

    def test_execute_write_query_bigquery_large_doc(
        self, valid_bigquery_db_instance: Any
    ) -> None:
        sql_columns_and_values = self.load_text_to_sql_values()
        cls_name = valid_bigquery_db_instance.__class__.__name__
        engine = valid_bigquery_db_instance.get_engine()
        result = DatabaseUtils.execute_write_query(
            engine=engine,
            cls_name=cls_name,
            table_name=self.valid_bigquery_table_name,
            sql_keys=list(sql_columns_and_values.keys()),
            sql_values=list(sql_columns_and_values.values()),
        )
        assert result is None

    def test_execute_write_query_invalid_snowflake_db(
        self, invalid_snowflake_db_instance: UnstractDB
    ) -> None:
        engine = invalid_snowflake_db_instance.get_engine()
        with pytest.raises(SnowflakeProgrammingException):
            DatabaseUtils.create_table_if_not_exists(
                db_class=invalid_snowflake_db_instance,
                engine=engine,
                table_name=self.invalid_wrong_table_name,
                database_entry=self.database_entry,
            )

    # Make this function at last to cover all large doc
    def test_execute_write_query_large_doc(
        self, valid_dbs_instance_to_handle_large_doc: Any
    ) -> None:
        sql_columns_and_values = self.load_text_to_sql_values()
        cls_name = valid_dbs_instance_to_handle_large_doc.__class__.__name__
        engine = valid_dbs_instance_to_handle_large_doc.get_engine()
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
