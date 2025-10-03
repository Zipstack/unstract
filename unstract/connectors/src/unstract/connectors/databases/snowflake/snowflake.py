import datetime
import json
import logging
import os
import uuid
from enum import Enum
from typing import Any

from unstract.connectors.constants import DatabaseTypeConstants
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

    def sql_to_db_mapping(self, value: Any, column_name: str | None = None) -> str:
        """Gets the python datatype of value and converts python datatype to
        corresponding DB datatype.

        Args:
            value (Any): python value of any datatype
            column_name (str | None): name of the column being mapped

        Returns:
            str: database columntype
        """
        data_type = type(value)

        if data_type in (dict, list):
            if column_name and column_name.endswith("_v2"):
                return str(DatabaseTypeConstants.SNOWFLAKE_VARIANT)
            else:
                return str(DatabaseTypeConstants.SNOWFLAKE_TEXT)

        mapping = {
            str: DatabaseTypeConstants.SNOWFLAKE_TEXT,
            int: DatabaseTypeConstants.SNOWFLAKE_INT,
            float: DatabaseTypeConstants.SNOWFLAKE_FLOAT,
            datetime.datetime: DatabaseTypeConstants.SNOWFLAKE_TIMESTAMP,
        }
        return str(mapping.get(data_type, DatabaseTypeConstants.SNOWFLAKE_TEXT))

    def get_engine(self) -> Any:
        from snowflake.connector import connect

        con = connect(
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
        import snowflake.connector.errors as SnowflakeError

        table_name = kwargs.get("table_name", None)
        logger.debug(f"Snowflake execute_query called with sql_query: {sql_query}")
        logger.debug(f"sql_values: {sql_values}")

        try:
            with engine.cursor() as cursor:
                # Check if the SQL query is already complete (contains SELECT)
                if "SELECT" in sql_query.upper():
                    # Complete SQL query - execute directly
                    logger.debug("Executing complete SQL query")
                    cursor.execute(sql_query)
                elif sql_values:
                    # Parameterized query - execute with values
                    logger.debug("Executing parameterized query")
                    cursor.execute(sql_query, sql_values)
                else:
                    # Direct SQL execution (used for DDL statements)
                    logger.debug("Executing SQL directly (no parameters)")
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
        import snowflake.connector.errors as SnowflakeError

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

    def get_sql_values_for_query(
        self, values: dict[str, Any], column_types: dict[str, str]
    ) -> dict[str, str]:
        """Prepare SQL values for Snowflake queries with VARIANT column support.

        Args:
            values (dict[str, Any]): dictionary of columns and values
            column_types (dict[str, str]): types of columns from database schema

        Returns:
            dict[str, str]: Dictionary of column names to SQL values or SQL fragments

        Note:
            For VARIANT columns, this returns SQL fragments like PARSE_JSON('...')
            instead of parameterized values, since Snowflake needs special handling
            for JSON data in VARIANT columns.
        """
        sql_values: dict[str, Any] = {}
        has_variant_columns = any(
            column_types.get(col.lower(), "").upper() == "VARIANT"
            for col in values.keys()
        )

        for column in values:
            value = values[column]
            col = column.lower()
            type_x = column_types.get(col, "")

            if isinstance(value, Enum):
                if has_variant_columns and type_x.upper() == "VARIANT":
                    # For VARIANT Enum values, create SQL fragment
                    escaped_value = str(value.value).replace("'", "''")
                    sql_values[column] = f"'{escaped_value}'"
                else:
                    # For non-VARIANT Enum values, create SQL fragment when we have VARIANT columns
                    if has_variant_columns:
                        escaped_value = str(value.value).replace("'", "''")
                        sql_values[column] = f"'{escaped_value}'"
                    else:
                        sql_values[column] = value.value
            elif isinstance(value, (dict, list)):
                # For dict/list values, check if this is a VARIANT column
                try:
                    json_str = json.dumps(value)
                    if has_variant_columns and type_x.upper() == "VARIANT":
                        # For VARIANT columns, return SQL fragment with PARSE_JSON
                        escaped_value = json_str.replace("'", "''")
                        sql_values[column] = f"PARSE_JSON('{escaped_value}')"
                    else:
                        # For non-VARIANT columns with VARIANT columns present, create quoted SQL fragment
                        if has_variant_columns:
                            escaped_value = json_str.replace("'", "''")
                            sql_values[column] = f"'{escaped_value}'"
                        else:
                            # No VARIANT columns, use regular parameterization
                            sql_values[column] = json_str
                except (TypeError, ValueError) as e:
                    logger.error(
                        f"Failed to serialize value to JSON for column {column}: {e}"
                    )
                    fallback_value = {
                        "error": "JSON serialization failed",
                        "error_type": e.__class__.__name__,
                        "error_message": str(e),
                        "data_type": str(type(value)),
                        "data_description": f"column_{column}",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                    fallback_json = json.dumps(fallback_value)
                    if has_variant_columns and type_x.upper() == "VARIANT":
                        escaped_value = fallback_json.replace("'", "''")
                        sql_values[column] = f"PARSE_JSON('{escaped_value}')"
                    else:
                        # For non-VARIANT columns with VARIANT columns present, create quoted SQL fragment
                        if has_variant_columns:
                            escaped_value = fallback_json.replace("'", "''")
                            sql_values[column] = f"'{escaped_value}'"
                        else:
                            # No VARIANT columns, use regular parameterization
                            sql_values[column] = fallback_json
            elif type_x.upper() == "VARIANT" and isinstance(value, str):
                if has_variant_columns:
                    try:
                        # For VARIANT columns with string values, validate if it's already valid JSON
                        json.loads(value)
                        escaped_value = value.replace("'", "''")
                        sql_values[column] = f"PARSE_JSON('{escaped_value}')"
                    except (json.JSONDecodeError, TypeError):
                        # Not JSON, convert to JSON string and create SQL fragment
                        json_str = json.dumps(value)
                        escaped_value = json_str.replace("'", "''")
                        sql_values[column] = f"PARSE_JSON('{escaped_value}')"
                else:
                    # No VARIANT columns, use regular parameterization
                    try:
                        json.loads(value)
                        sql_values[column] = value
                    except (json.JSONDecodeError, TypeError):
                        sql_values[column] = json.dumps(value)
            else:
                # All other values
                if has_variant_columns:
                    # When we have VARIANT columns, create SQL fragments for consistency
                    if value is None:
                        sql_values[column] = "NULL"
                    else:
                        escaped_value = str(value).replace("'", "''")
                        sql_values[column] = f"'{escaped_value}'"
                else:
                    # No VARIANT columns, use regular parameterization
                    sql_values[column] = f"{value}"

        # If table has a column 'id', unstract inserts a unique value to it
        if any(key in column_types for key in ["id", "ID"]):
            uuid_id = str(uuid.uuid4())
            if has_variant_columns:
                sql_values["id"] = f"'{uuid_id}'"
            else:
                sql_values["id"] = uuid_id

        return sql_values

    def get_sql_insert_query(
        self, table_name: str, sql_keys: list[str], sql_values: list[str] = None
    ) -> str:
        """Generate SQL insert query for Snowflake with special handling for VARIANT columns.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names
            sql_values (list[str], optional): SQL values, may contain fragments like PARSE_JSON(...)

        Returns:
            str: Complete SQL insert query with VARIANT columns handled appropriately
        """
        keys_str = ",".join(sql_keys)

        if sql_values:
            # Check if we have SQL fragments that need SELECT format
            has_sql_fragments = any(
                isinstance(v, str)
                and ("PARSE_JSON(" in v or "NULL" == v or v.startswith("'"))
                for v in sql_values
            )

            if has_sql_fragments:
                # Build complete SQL with SELECT format for VARIANT columns
                values_str = ",".join(str(v) for v in sql_values)
                return f"INSERT INTO {table_name} ({keys_str}) SELECT {values_str}"

        # Fall back to parameterized format for standard queries
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"
