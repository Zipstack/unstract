"""Worker-Compatible Database Utils

This module provides database utilities for workers that replicate the functionality
of backend/workflow_manager/endpoint_v2/database_utils.py without Django dependencies.
"""

import datetime
import json
from typing import Any

from shared.enums.status_enums import FileProcessingStatus

# Import unstract database connectors
from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.databases.exceptions import UnstractDBConnectorException
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

from ..logging import WorkerLogger

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
    METADATA = "metadata"
    ERROR_MESSAGE = "error_message"
    STATUS = "status"
    USER_FIELD_1 = "user_field_1"
    USER_FIELD_2 = "user_field_2"
    USER_FIELD_3 = "user_field_3"
    PERMANENT_COLUMNS = [
        "created_by",
        "created_at",
        "metadata",
        "error_message",
        "status",
        "user_field_1",
        "user_field_2",
        "user_field_3",
    ]


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
        conn_cls: Any,
        values: dict[str, Any],
        column_types: dict[str, str],
    ) -> dict[str, str]:
        """Making SQL Columns and Values for Query.

        Args:
            conn_cls (Any): DB Connection class
            values (Dict[str, Any]): dictionary of columns and values
            column_types (Dict[str, str]): types of columns

        Returns:
            Dict[str, str]: SQL values formatted for the specific database type

        """
        return conn_cls.get_sql_values_for_query(values=values, column_types=column_types)

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
    def _create_safe_error_json(data_description: str, original_error: Exception) -> dict:
        """Create a standardized error JSON object that can be safely serialized.

        Args:
            data_description (str): Description of the data being serialized
            original_error (Exception): The original exception that occurred

        Returns:
            dict: A safely serializable JSON object with error details
        """
        return {
            "error": "JSON serialization failed",
            "error_type": original_error.__class__.__name__,
            "error_message": str(original_error),
            "data_type": str(type(original_error)),
            "data_description": data_description,
            "timestamp": datetime.datetime.now().isoformat(),
        }

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
        table_info: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
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
            table_info (dict[str, str], optional): Information about the table
                to be used for generating the columns and values.
                Defaults to None.
            metadata (dict[str, Any], optional): Metadata to be included in the
                dictionary. Defaults to None.
            error (str, optional): Error message to be included in the dictionary.
                Defaults to None.

        Returns:
            Dict[str, Any]: A dictionary containing columns and values based on
                the specified parameters.
        """
        values: dict[str, Any] = {}

        # Determine column mode
        column_mode = WorkerDatabaseUtils._determine_column_mode(column_mode_str)

        # Add metadata columns (agent, timestamp)
        WorkerDatabaseUtils._add_metadata_columns(
            values, include_agent, agent_name, include_timestamp
        )

        # Add processing columns (metadata, error, status)
        WorkerDatabaseUtils._add_processing_columns(values, table_info, metadata, error)

        # Process data based on column mode
        WorkerDatabaseUtils._process_data_by_mode(
            values=values,
            column_mode=column_mode,
            data=data,
            single_column_name=single_column_name,
            table_info=table_info,
        )

        # Add required identifier columns
        values[file_path_name] = file_path
        values[execution_id_name] = execution_id

        return values

    @staticmethod
    def _determine_column_mode(column_mode_str: str) -> ColumnModes:
        """Determine column mode from string, defaulting to single column mode."""
        try:
            if column_mode_str == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
                return ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN
            elif column_mode_str == ColumnModes.SPLIT_JSON_INTO_COLUMNS:
                return ColumnModes.SPLIT_JSON_INTO_COLUMNS
            else:
                return ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN
        except Exception:
            # Handle the case where the string is not a valid enum value
            return ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN

    @staticmethod
    def _has_table_column(table_info: dict[str, str] | None, column_name: str) -> bool:
        """Check if a column exists in table info (case-insensitive).

        Args:
            table_info: Dictionary containing table column information
            column_name: Name of the column to check for existence

        Returns:
            bool: True if column exists or table_info is None, False otherwise
        """
        return (
            (table_info is None)
            or any(k.lower() == column_name.lower() for k in table_info)
            if table_info
            else True
        )

    @staticmethod
    def _add_metadata_columns(
        values: dict[str, Any],
        include_agent: bool,
        agent_name: str | None,
        include_timestamp: bool,
    ) -> None:
        """Add metadata columns (agent, timestamp) to values dictionary."""
        if include_agent and agent_name:
            values[TableColumns.CREATED_BY] = agent_name

        if include_timestamp:
            values[TableColumns.CREATED_AT] = datetime.datetime.now()

    @staticmethod
    def _add_processing_columns(
        values: dict[str, Any],
        table_info: dict[str, str] | None,
        metadata: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        """Add metadata, error, and status columns to values dictionary.

        Args:
            values: Dictionary to add columns to
            table_info: Table column information for existence checking
            metadata: Metadata to serialize and store
            error: Error message to store
        """
        # Check column existence once
        has_metadata_col = WorkerDatabaseUtils._has_table_column(
            table_info, TableColumns.METADATA
        )
        has_error_col = WorkerDatabaseUtils._has_table_column(
            table_info, TableColumns.ERROR_MESSAGE
        )
        has_status_col = WorkerDatabaseUtils._has_table_column(
            table_info, TableColumns.STATUS
        )

        # Add metadata with safe JSON serialization
        if metadata and has_metadata_col:
            try:
                values[TableColumns.METADATA] = json.dumps(metadata)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize metadata to JSON: {e}")
                # Create a safe fallback error object
                fallback_metadata = WorkerDatabaseUtils._create_safe_error_json(
                    "metadata", e
                )
                values[TableColumns.METADATA] = json.dumps(fallback_metadata)

        # Add error message
        if error and has_error_col:
            values[TableColumns.ERROR_MESSAGE] = error

        # Add status based on error presence
        if has_status_col:
            values[TableColumns.STATUS] = (
                FileProcessingStatus.ERROR if error else FileProcessingStatus.SUCCESS
            )

    @staticmethod
    def _process_data_by_mode(
        values: dict[str, Any],
        column_mode: ColumnModes,
        data: Any,
        single_column_name: str,
        table_info: dict[str, str] | None = None,
    ) -> None:
        """Process data based on the specified column mode."""
        if column_mode == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
            WorkerDatabaseUtils._process_single_column_mode(
                values=values,
                data=data,
                single_column_name=single_column_name,
                table_info=table_info,
            )
        elif column_mode == ColumnModes.SPLIT_JSON_INTO_COLUMNS:
            # Note: This function is not used in the current implementation
            WorkerDatabaseUtils._process_split_column_mode(
                values=values,
                data=data,
                single_column_name=single_column_name,
            )

    @staticmethod
    def _process_single_column_mode(
        values: dict[str, Any],
        data: Any,
        single_column_name: str,
        table_info: dict[str, str] | None = None,
    ) -> None:
        """Process data for single column mode."""
        v2_col_name = f"{single_column_name}_v2"
        has_v2_col = WorkerDatabaseUtils._has_table_column(table_info, v2_col_name)
        if isinstance(data, str):
            wrapped_dict = {"result": data}
            values[single_column_name] = wrapped_dict
            if has_v2_col:
                values[v2_col_name] = wrapped_dict
        else:
            values[single_column_name] = data
            if has_v2_col:
                values[v2_col_name] = data

    @staticmethod
    def _process_split_column_mode(
        values: dict[str, Any], data: Any, single_column_name: str
    ) -> None:
        """Process data for split column mode."""
        if isinstance(data, dict):
            values.update(data)
        elif isinstance(data, str):
            values[single_column_name] = data
        else:
            try:
                values[single_column_name] = json.dumps(data)
            except (TypeError, ValueError) as e:
                logger.error(
                    f"Failed to serialize data to JSON in split column mode: {e}"
                )
                # Create a safe fallback error object
                fallback_data = WorkerDatabaseUtils._create_safe_error_json(
                    "split_column_data", e
                )
                values[single_column_name] = json.dumps(fallback_data)

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
        """
        column_types: dict[str, str] = WorkerDatabaseUtils.get_column_types(
            conn_cls=conn_cls, table_name=table_name
        )
        sql_columns_and_values = WorkerDatabaseUtils.get_sql_values_for_query(
            conn_cls=conn_cls,
            values=values,
            column_types=column_types,
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

        """
        sql = db_class.get_sql_insert_query(
            table_name=table_name, sql_keys=sql_keys, sql_values=sql_values
        )

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
                table=table_name,
                database_entry=database_entry,
                permanent_columns=TableColumns.PERMANENT_COLUMNS,
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

    @staticmethod
    def migrate_table_to_v2(
        db_class: UnstractDB,
        engine: Any,
        table_name: str,
        column_name: str,
    ) -> dict[str, str]:
        """Migrate table to v2 by adding _v2 columns.

        Args:
            db_class (UnstractDB): DB Connection class
            engine (Any): Database engine
            table_name (str): Name of the table to migrate
            column_name (str): Base column name for v2 migration
        Returns:
            dict[str, str]: Updated table information schema
        Raises:
            UnstractDBException: If migration fails
        """
        try:
            result: dict[str, str] = db_class.migrate_table_to_v2(
                table_name=table_name,
                column_name=column_name,
                engine=engine,
            )
            return result
        except UnstractDBConnectorException as e:
            raise WorkerDBException(detail=e.detail) from e
