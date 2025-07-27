"""Worker-Compatible Database Utils

This module provides database utilities for workers that replicate the functionality
of backend/workflow_manager/endpoint_v2/database_utils.py without Django dependencies.
"""

import datetime
import json
import uuid
from typing import Any

# Import unstract database connectors
from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.databases.exceptions import UnstractDBConnectorException
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class DBConnectionClass:
    """Database connection class constants."""

    SNOWFLAKE = "SnowflakeDB"
    POSTGRESQL = "PostgreSQLDB"
    MYSQL = "MySQLDB"
    BIGQUERY = "BigQueryDB"


class TableColumns:
    """Common table column names."""

    CREATED_BY = "created_by"
    CREATED_AT = "created_at"


class ColumnModes:
    """Column mode enumeration for data storage."""

    WRITE_JSON_TO_A_SINGLE_COLUMN = "WRITE_JSON_TO_A_SINGLE_COLUMN"
    SPLIT_JSON_INTO_COLUMNS = "SPLIT_JSON_INTO_COLUMNS"


class AgentName:
    """Agent name constants."""

    UNSTRACT_DBWRITER = "UNSTRACT_DBWRITER"


class WorkerDBException(Exception):
    """Worker database exception."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class WorkerDatabaseUtils:
    """Worker-compatible database utilities following production patterns."""

    @staticmethod
    def get_sql_values_for_query(
        values: dict[str, Any], column_types: dict[str, str], cls_name: str
    ) -> dict[str, str]:
        """Making SQL Columns and Values for Query.

        Args:
            values (Dict[str, Any]): dictionary of columns and values
            column_types (Dict[str, str]): types of columns
            cls_name (str): The database connection class name for handling database-specific queries.

        Returns:
            Dict[str, str]: SQL values formatted for the specific database type

        Note:
            - If `cls_name` is not provided or is None, the function assumes a
                Default SQL database and makes values accordingly.
            - If `cls_name` matches DBConnectionClass.SNOWFLAKE,
                the function makes values using Snowflake-specific syntax.
            - Unstract creates id by default if table not exists.
                If there is column 'id' in db table, it will insert
                    'id' as uuid into the db table.
                Else it will GET table details from INFORMATION SCHEMA and
                    insert into the table accordingly
        """
        sql_values: dict[str, Any] = {}
        for column in values:
            if cls_name == DBConnectionClass.SNOWFLAKE:
                col = column.lower()
                type_x = column_types.get(col, "")
                if type_x == "VARIANT":
                    values[column] = values[column].replace("'", "\\'")
                    sql_values[column] = f"parse_json($${values[column]}$$)"
                else:
                    sql_values[column] = f"{values[column]}"
            else:
                # Default to Other SQL DBs
                # TODO: Handle numeric types with no quotes
                sql_values[column] = f"{values[column]}"

        # If table has a column 'id', unstract inserts a unique value to it
        # Oracle db has column 'ID' instead of 'id'
        if any(key in column_types for key in ["id", "ID"]):
            uuid_id = str(uuid.uuid4())
            sql_values["id"] = f"{uuid_id}"

        return sql_values

    @staticmethod
    def get_column_types(conn_cls: Any, table_name: str) -> Any:
        """Function to return connector db column and types by calling
        connector table information schema.

        Args:
            conn_cls (Any): DB Connection class
            table_name (str): DB table-name

        Raises:
            WorkerDBException: Database operation error

        Returns:
            Any: db column name and db column types of corresponding table
        """
        try:
            return conn_cls.get_information_schema(table_name=table_name)
        except ConnectorError as e:
            raise WorkerDBException(detail=e.message) from e
        except Exception as e:
            logger.error(
                f"Error getting db-column-name and db-column-type "
                f"for {table_name}: {str(e)}"
            )
            raise

    @staticmethod
    def get_columns_and_values(
        column_mode_str: str,
        data: Any,
        file_path: str,
        execution_id: str,
        file_path_name: str = "file_path",
        execution_id_name: str = "execution_id",
        include_timestamp: bool = False,
        include_agent: bool = False,
        agent_name: str | None = AgentName.UNSTRACT_DBWRITER,
        single_column_name: str = "data",
    ) -> dict[str, Any]:
        """Generate a dictionary of columns and values based on specified parameters.

        Args:
            column_mode_str (str): The string representation of the column mode,
                which determines how data is stored in the dictionary.
            data (Any): The data to be stored in the dictionary.
            file_path (str): The file path to include in the data.
            execution_id (str): The execution ID to include in the data.
            file_path_name (str, optional): Column name for file path. Defaults to "file_path".
            execution_id_name (str, optional): Column name for execution ID. Defaults to "execution_id".
            include_timestamp (bool, optional): Whether to include the
                current timestamp in the dictionary. Defaults to False.
            include_agent (bool, optional): Whether to include the agent's name
                in the dictionary. Defaults to False.
            agent_name (str, optional): The name of the agent when include_agent
                is true. Defaults to AgentName.UNSTRACT_DBWRITER.
            single_column_name (str, optional): The name of the single column
                when using 'WRITE_JSON_TO_A_SINGLE_COLUMN' mode.
                Defaults to "data".

        Returns:
            Dict[str, Any]: A dictionary containing columns and values based on
                the specified parameters.
        """
        values: dict[str, Any] = {}

        # Determine column mode (default to single column if invalid)
        try:
            if column_mode_str == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
                column_mode = ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN
            elif column_mode_str == ColumnModes.SPLIT_JSON_INTO_COLUMNS:
                column_mode = ColumnModes.SPLIT_JSON_INTO_COLUMNS
            else:
                column_mode = ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN
        except Exception:
            # Handle the case where the string is not a valid enum value
            column_mode = ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN

        if include_agent and agent_name:
            values[TableColumns.CREATED_BY] = agent_name

        if include_timestamp:
            values[TableColumns.CREATED_AT] = datetime.datetime.now()

        if column_mode == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
            if isinstance(data, str):
                values[single_column_name] = data
            else:
                values[single_column_name] = json.dumps(data)
        elif column_mode == ColumnModes.SPLIT_JSON_INTO_COLUMNS:
            if isinstance(data, dict):
                values.update(data)
            elif isinstance(data, str):
                values[single_column_name] = data
            else:
                values[single_column_name] = json.dumps(data)

        values[file_path_name] = file_path
        values[execution_id_name] = execution_id
        return values

    @staticmethod
    def get_sql_query_data(
        conn_cls: Any,
        table_name: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate SQL columns and values for an insert query based on the
        provided values and table schema.

        Args:
            conn_cls: DB connection class
            table_name (str): The name of the target table for the insert query.
            values (Dict[str, Any]): A dictionary containing column-value pairs
                for the insert query.

        Returns:
            Dict[str, Any]: A dictionary of SQL values suitable for use in an insert query.

        Note:
            - This function determines the database type based on the class name.
            - If the database is Snowflake (DBConnectionClass.SNOWFLAKE),
                it handles Snowflake-specific SQL generation.
            - For other SQL databases, it uses default SQL generation
                based on column types.
        """
        cls_name = conn_cls.__class__.__name__
        column_types: dict[str, str] = WorkerDatabaseUtils.get_column_types(
            conn_cls=conn_cls, table_name=table_name
        )
        sql_columns_and_values = WorkerDatabaseUtils.get_sql_values_for_query(
            values=values,
            column_types=column_types,
            cls_name=cls_name,
        )
        return sql_columns_and_values

    @staticmethod
    def execute_write_query(
        db_class: UnstractDB,
        engine: Any,
        table_name: str,
        sql_keys: list[str],
        sql_values: list[str],
    ) -> None:
        """Execute Insert Query.

        Args:
            db_class (UnstractDB): Database connection class
            engine (Any): Database engine
            table_name (str): table name
            sql_keys (list[str]): columns
            sql_values (list[str]): values

        Notes:
        - Snowflake does not support INSERT INTO ... VALUES ...
          syntax when VARIANT columns are present (JSON).
          So we need to use INSERT INTO ... SELECT ... syntax
        - sql values can contain data with single quote. It needs to be handled properly
        """
        sql = db_class.get_sql_insert_query(table_name=table_name, sql_keys=sql_keys)

        logger.debug(f"Inserting into table {table_name} with: {sql} query")
        logger.debug(f"SQL values: {sql_values}")

        try:
            db_class.execute_query(
                engine=engine,
                sql_query=sql,
                sql_values=sql_values,
                table_name=table_name,
                sql_keys=sql_keys,
            )
        except UnstractDBConnectorException as e:
            raise WorkerDBException(detail=e.detail) from e

        logger.debug(f"Successfully inserted into table {table_name} with: {sql} query")

    @staticmethod
    def get_db_class(connector_id: str, connector_settings: dict[str, Any]) -> UnstractDB:
        """Get database class instance for the given connector.

        Args:
            connector_id (str): The connector identifier (may include UUID or be simple name)
            connector_settings (Dict[str, Any]): Connector configuration settings

        Returns:
            UnstractDB: Database connector instance
        """
        try:
            # Use the constant 'CONNECTOR' key to access connector metadata
            CONNECTOR_KEY = "connector"  # Following backend pattern

            logger.debug(f"Looking for connector: {connector_id}")
            logger.debug(f"Available connectors: {list(db_connectors.keys())}")

            # First try exact match
            if connector_id in db_connectors:
                connector_metadata = db_connectors[connector_id]
            else:
                # If exact match fails, try to find by prefix (for simple names like 'postgresql')
                matching_connectors = [
                    key
                    for key in db_connectors.keys()
                    if key.startswith(f"{connector_id}|")
                ]

                if not matching_connectors:
                    available_types = [key.split("|")[0] for key in db_connectors.keys()]
                    raise WorkerDBException(
                        f"Database connector '{connector_id}' not found. "
                        f"Available types: {available_types}"
                    )

                # Use the first matching connector
                full_connector_id = matching_connectors[0]
                connector_metadata = db_connectors[full_connector_id]
                logger.info(
                    f"Resolved connector '{connector_id}' to '{full_connector_id}'"
                )

            if "metadata" not in connector_metadata:
                raise WorkerDBException(
                    f"No metadata found for connector '{connector_id}'"
                )

            if CONNECTOR_KEY not in connector_metadata["metadata"]:
                raise WorkerDBException(f"No connector class found for '{connector_id}'")

            connector = connector_metadata["metadata"][CONNECTOR_KEY]
            connector_class: UnstractDB = connector(connector_settings)
            logger.info(
                f"Successfully created database connector instance for '{connector_id}'"
            )
            return connector_class

        except Exception as e:
            logger.error(
                f"Failed to get database class for connector '{connector_id}': {str(e)}"
            )
            raise WorkerDBException(
                f"Failed to initialize database connector: {str(e)}"
            ) from e

    @staticmethod
    def create_table_if_not_exists(
        db_class: UnstractDB,
        engine: Any,
        table_name: str,
        database_entry: dict[str, Any],
    ) -> None:
        """Creates table if not exists.

        Args:
            db_class (UnstractDB): Type of Unstract DB connector
            engine (Any): Database engine
            table_name (str): Name of the table to create
            database_entry (Dict[str, Any]): Sample data entry for table schema creation

        Raises:
            WorkerDBException: Database operation error
        """
        try:
            sql = db_class.create_table_query(
                table=table_name, database_entry=database_entry
            )
            logger.debug(f"Creating table {table_name} with: {sql} query")

            db_class.execute_query(
                engine=engine, sql_query=sql, sql_values=None, table_name=table_name
            )

            logger.debug(f"Successfully created table {table_name} with: {sql} query")

        except UnstractDBConnectorException as e:
            raise WorkerDBException(detail=e.detail) from e
        except Exception as e:
            logger.error(f"Failed to create table {table_name}: {str(e)}")
            raise WorkerDBException(f"Table creation failed: {str(e)}") from e
