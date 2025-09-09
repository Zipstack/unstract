import datetime
import json
import logging
import os
from typing import Any

import snowflake.connector
import snowflake.connector.errors as SnowflakeError
from snowflake.connector.connection import SnowflakeConnection

from unstract.connectors.databases.exceptions import SnowflakeProgrammingException
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class SnowflakeDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Snowflake")

        self.user = settings["user"]
        self.password = settings["password"]
        self.account = settings["account"]
        self.database = settings["database"]
        self.schema = settings["schema"]
        self.warehouse = settings["warehouse"]
        self.role = settings["role"]

    @staticmethod
    def get_id() -> str:
        return "snowflake|87c5151e-5e41-420a-b1ea-772d9720929b"

    @staticmethod
    def get_name() -> str:
        return "Snowflake"

    @staticmethod
    def get_description() -> str:
        return "Snowflake Data Warehouse"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Snowflake.png"

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
        return "VARCHAR"

    def sql_to_db_mapping(self, value: str) -> str:
        """Gets the python datatype of value and converts python datatype to
        corresponding DB datatype.

        Args:
            value (str): python datatype

        Returns:
            str: database columntype
        """
        python_type = type(value)

        mapping = {
            str: "TEXT",
            int: "INT",
            float: "FLOAT",
            datetime.datetime: "TIMESTAMP",
            dict: "VARIANT",
            list: "VARIANT",
        }
        return mapping.get(python_type, "TEXT")

    def get_engine(self) -> SnowflakeConnection:
        con = snowflake.connector.connect(
            user=self.user,
            password=self.password,
            account=self.account,
            database=self.database,
            schema=self.schema,
            warehouse=self.warehouse,
            role=self.role,
        )
        return con

    def get_create_table_base_query(self, table: str) -> str:
        sql_query = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"(id TEXT ,"
            f"created_by TEXT, created_at TIMESTAMP, "
            f"metadata VARIANT, "
            f"user_field_1 BOOLEAN DEFAULT FALSE, "
            f"user_field_2 INT DEFAULT 0, "
            f"user_field_3 TEXT DEFAULT NULL, "
            f"status VARCHAR, "
            f"error_message VARCHAR, "
        )
        return sql_query

    def prepare_multi_column_migration(self, table_name: str, column_name: str) -> list:
        """Returns a list of separate ALTER TABLE statements for Snowflake.

        Snowflake doesn't support multiple ADD COLUMN clauses in a single statement,
        so we return a list of individual ALTER TABLE statements.
        """
        sql_statements = [
            f"ALTER TABLE {table_name} ADD COLUMN {column_name}_v2 VARIANT",
            f"ALTER TABLE {table_name} ADD COLUMN metadata VARIANT",
            f"ALTER TABLE {table_name} ADD COLUMN user_field_1 BOOLEAN DEFAULT FALSE",
            f"ALTER TABLE {table_name} ADD COLUMN user_field_2 INT DEFAULT 0",
            f"ALTER TABLE {table_name} ADD COLUMN user_field_3 TEXT DEFAULT NULL",
            f"ALTER TABLE {table_name} ADD COLUMN status VARCHAR",
            f"ALTER TABLE {table_name} ADD COLUMN error_message VARCHAR",
        ]
        return sql_statements

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        table_name = kwargs.get("table_name", None)
        logger.debug(f"Snowflake execute_query called with sql_query: {sql_query}")
        logger.debug(f"sql_values: {sql_values}")

        try:
            with engine.cursor() as cursor:
                if sql_values:
                    # Check if we need PARSE_JSON for VARIANT columns
                    sql_keys = kwargs.get("sql_keys", [])

                    if sql_keys:
                        # Get table schema to identify VARIANT columns
                        try:
                            column_types = self.get_information_schema(
                                table_name=table_name
                            )
                        except Exception:
                            column_types = {}

                        # Check if we need to build complete SQL for VARIANT columns
                        has_variant_json = any(
                            column_types.get(key.lower(), "").upper() == "VARIANT"
                            and i < len(sql_values)
                            and isinstance(sql_values[i], str)
                            for i, key in enumerate(sql_keys)
                        )

                        if has_variant_json:
                            # Build complete SQL with PARSE_JSON embedded directly
                            values_list = []
                            for i, key in enumerate(sql_keys):
                                column_type = column_types.get(key.lower(), "").upper()
                                value = sql_values[i] if i < len(sql_values) else None

                                if column_type == "VARIANT" and isinstance(value, str):
                                    try:
                                        # Validate it's JSON
                                        json.loads(value)
                                        # Escape single quotes in JSON for Snowflake
                                        escaped_value = value.replace("'", "''")
                                        values_list.append(
                                            f"PARSE_JSON('{escaped_value}')"
                                        )
                                    except (json.JSONDecodeError, TypeError):
                                        # Not JSON, use quoted string
                                        escaped_value = str(value).replace("'", "''")
                                        values_list.append(f"'{escaped_value}'")
                                else:
                                    # Non-VARIANT columns - quote appropriately
                                    if value is None:
                                        values_list.append("NULL")
                                    else:
                                        escaped_value = str(value).replace("'", "''")
                                        values_list.append(f"'{escaped_value}'")

                            # Extract table and columns part from original SQL
                            # Use SELECT instead of VALUES for Snowflake VARIANT handling
                            if "VALUES (" in sql_query:
                                values_start = sql_query.find("VALUES (")
                                prefix = sql_query[:values_start]
                                # Use SELECT for PARSE_JSON support instead of VALUES
                                complete_sql = f"{prefix}SELECT {', '.join(values_list)}"
                            else:
                                complete_sql = sql_query

                            logger.debug(f"Complete SQL: {complete_sql}")
                            cursor.execute(complete_sql)
                        else:
                            # Use standard parameterized query
                            logger.debug("Using standard parameterized query")
                            cursor.execute(sql_query, sql_values)
                    else:
                        logger.debug("Using standard parameterized query (no sql_keys)")
                        cursor.execute(sql_query, sql_values)
                else:
                    logger.debug("No sql_values, executing query directly")
                    cursor.execute(sql_query)
            engine.commit()
        except SnowflakeError.ProgrammingError as e:
            logger.error(
                f"snowflake programming error in creating/inserting table: "
                f"{e.msg} {e.errno}"
            )
            logger.error(f"SQL Query: {sql_query}")
            logger.error(f"SQL Values: {sql_values}")
            raise SnowflakeProgrammingException(
                detail=f"{e.msg} | SQL: {sql_query} | Values: {sql_values}",
                database=self.database,
                schema=self.schema,
                table_name=table_name,
            ) from e

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        query = f"describe table {table_name}"
        column_types: dict[str, str] = {}
        try:
            results = self.execute(query=query)
            if results:
                for column in results:
                    column_types[column[0].lower()] = column[1].split("(")[0]
        except (SnowflakeError.ProgrammingError, ConnectorError) as e:
            # Handle table not found errors gracefully
            error_str = str(e).lower()
            if (
                "002003" in error_str
                or "does not exist" in error_str
                or "not authorized" in error_str
            ):
                logger.info(f"Table {table_name} does not exist or not authorized: {e}")
                return {}
            else:
                # Re-raise other programming/connector errors
                raise
        return column_types

    def get_sql_insert_query(self, table_name: str, sql_keys: list[str]) -> str:
        """Generate SQL insert query for Snowflake with special handling for VARIANT columns.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names

        Returns:
            str: SQL insert query with VARIANT columns handled appropriately
        """
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"
