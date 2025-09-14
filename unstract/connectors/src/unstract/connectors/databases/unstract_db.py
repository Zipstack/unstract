import datetime
import json
import logging
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from unstract.connectors.base import UnstractConnector
from unstract.connectors.databases.constants import TableColumns
from unstract.connectors.databases.exceptions import UnstractDBConnectorException
from unstract.connectors.enums import ConnectorMode
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class UnstractDB(UnstractConnector, ABC):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return False

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.DATABASE

    @staticmethod
    def requires_oauth() -> bool:
        return False

    # TODO: Can be removed if removed from base class
    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @abstractmethod
    def get_engine(self) -> Any:
        pass

    def test_credentials(self) -> bool:
        """To test credentials for a DB connector."""
        try:
            self.get_engine()
        except Exception as e:
            raise ConnectorError(f"Error while connecting to DB: {str(e)}") from e
        return True

    def execute(self, query: str) -> Any:
        try:
            with self.get_engine().cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            raise ConnectorError(str(e)) from e

    # TO DO: Remove if needed
    def sql_to_db_mapping(self, value: str) -> str:
        """Gets the python datatype of value and converts python datatype
        to corresponding DB datatype
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
        }
        return mapping.get(python_type, "TEXT")

    @abstractmethod
    def prepare_multi_column_migration(
        self, table_name: str, column_name: str
    ) -> str | list:
        """Returns the ALTER TABLE query specific to the database.

        Args:
            table_name (str): The name of the table to alter
            column_name (str): The base name of the column to add a _v2 version for

        Returns:
            str | list: Either a single SQL ALTER TABLE statement (str) or
                       a list of separate ALTER TABLE statements for databases
                       that don't support multiple column additions in one statement
        """
        pass

    @abstractmethod
    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """

    def create_table_query(self, table: str, database_entry: dict[str, Any]) -> Any:
        """Function to create a create table sql query.

        Args:
            table (str): db-connector table name
            database_entry (dict[str, Any]): a dictionary of column name and types

        Returns:
            Any: generates a create sql query for all the columns
        """
        PERMANENT_COLUMNS = TableColumns.PERMANENT_COLUMNS

        sql_query = ""
        create_table_query = self.get_create_table_base_query(table=table)
        logger.info(f"Create table base query {create_table_query}")

        sql_query += create_table_query

        for key, val in database_entry.items():
            if key not in PERMANENT_COLUMNS:
                sql_type = self.sql_to_db_mapping(val)
                sql_query += f"{key} {sql_type}, "

        return sql_query.rstrip(", ") + ")"

    @staticmethod
    def get_sql_insert_query(
        table_name: str, sql_keys: list[str], sql_values: list[str] = None
    ) -> str:
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names
            sql_values (list[str], optional): SQL values for database-specific handling

        Returns:
            str: returns a string with parameterised insert sql query
        """
        # Base implementation ignores sql_values and returns parameterized query
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @abstractmethod
    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        """Executes create/insert query.

        Args:
            engine (Any): big query client engine
            sql_query (str): sql create table/insert into table query
            sql_values (Any): sql data to be insertteds
        """
        pass

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        """Function to generate information schema of the corresponding table.

        Args:
            table_name (str): db-connector table name

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        table_name = str.lower(table_name)
        query = (
            "SELECT column_name, data_type FROM "
            "information_schema.columns WHERE "
            f"table_name = '{table_name}'"
        )
        results = self.execute(query=query)
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types

    def get_db_column_types(self, columns_with_types: Any) -> dict[str, str]:
        """Converts db results columns_with_types to dict.

        Args:
            columns_with_types (Any): database information schema array

        Returns:
            dict[str, str]: a dictionary containing db column-name and column-type
        """
        column_types: dict[str, str] = {}
        for column_name, data_type in columns_with_types:
            column_types[column_name] = data_type
        return column_types

    def has_no_metadata(self, table_info: dict[str, str]) -> bool:
        """Check if metadata field exists in table_info (case-insensitive).

        Args:
            table_info: Dictionary containing table field names and their types

        Returns:
            bool: False if metadata exists, True if metadata does not exist
        """
        logger.info("Checking if column 'metadata' exists in table_info")
        metadata_exists = any(key.lower() == "metadata" for key in table_info.keys())
        if metadata_exists:
            logger.info(
                "column 'metadata' exists for corresponding table. No migration needed"
            )
        return not metadata_exists

    def migrate_table_to_v2(
        self, table_name: str, column_name: str, engine: Any
    ) -> dict[str, str]:
        """Retruns the information schema of table after alteraring table
        This will add column _v2 to the table and return the information schema

        Args:
            table_name (str): _description_
            column_name (str): _description_
            engine (Any): _description_

        Raises:
            UnstractDBException: _description_

        Returns:
            dict[str, str]: _description_
        """
        sql_query_or_list = self.prepare_multi_column_migration(
            table_name=table_name, column_name=column_name
        )
        logger.info(
            "Running table migration for table %s by adding following columns %s",
            table_name,
            sql_query_or_list,
        )

        try:
            if isinstance(sql_query_or_list, list):
                for sql_query in sql_query_or_list:
                    self.execute_query(
                        engine=engine,
                        sql_query=sql_query,
                        sql_values=None,
                        table_name=table_name,
                    )
            else:
                self.execute_query(
                    engine=engine,
                    sql_query=sql_query_or_list,
                    sql_values=None,
                    table_name=table_name,
                )
                logger.info(
                    "successfully migrated table %s with: %s query",
                    table_name,
                    sql_query_or_list,
                )
            return self.get_information_schema(table_name=table_name)
        except Exception as e:
            raise UnstractDBConnectorException(detail=str(e)) from e

    def get_sql_values_for_query(
        self, values: dict[str, Any], column_types: dict[str, str]
    ) -> dict[str, str]:
        """Prepare SQL values for query execution.

        Args:
            values (dict[str, Any]): dictionary of columns and values
            column_types (dict[str, str]): types of columns from database schema

        Returns:
            dict[str, str]: Dictionary of column names to SQL values for parameterized queries

        Note:
            This is the base implementation for standard databases.
            Database-specific connectors can override this method for custom logic.
        """
        sql_values: dict[str, Any] = {}
        for column in values:
            value = values[column]
            # Handle JSON and Enum types for standard databases
            if isinstance(value, (dict, list)):
                try:
                    sql_values[column] = json.dumps(value)
                except (TypeError, ValueError) as e:
                    logger.error(
                        f"Failed to serialize value to JSON for column {column}: {e}"
                    )
                    # Create a safe fallback error object
                    fallback_value = {
                        "error": "JSON serialization failed",
                        "error_type": e.__class__.__name__,
                        "error_message": str(e),
                        "data_type": str(type(value)),
                        "data_description": f"column_{column}",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                    sql_values[column] = json.dumps(fallback_value)
            elif isinstance(value, Enum):
                sql_values[column] = value.value
            else:
                sql_values[column] = f"{value}"

        # If table has a column 'id', unstract inserts a unique value to it
        # Oracle db has column 'ID' instead of 'id'
        if any(key in column_types for key in ["id", "ID"]):
            uuid_id = str(uuid.uuid4())
            sql_values["id"] = f"{uuid_id}"

        return sql_values
