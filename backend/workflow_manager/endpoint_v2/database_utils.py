import datetime
import json
import logging
from typing import Any

from utils.constants import Common
from workflow_manager.endpoint_v2.constants import TableColumns
from workflow_manager.endpoint_v2.enums import FileProcessingStatus
from workflow_manager.endpoint_v2.exceptions import UnstractDBException
from workflow_manager.workflow_v2.enums import AgentName, ColumnModes

from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.databases.exceptions import UnstractDBConnectorException
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class DatabaseUtils:
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
    def get_column_types(
        conn_cls: Any,
        table_name: str,
    ) -> Any:
        """Function to return connector db column and types by calling
        connector table information schema.

        Args:
            conn_cls (Any): DB Connection class
            table_name (str): DB table-name

        Raises:
            UnstractDBException: _description_

        Returns:
            Any: db column name and db column types of corresponding table
        """
        try:
            return conn_cls.get_information_schema(table_name=table_name)
        except ConnectorError as e:
            raise UnstractDBException(detail=e.message) from e

    @staticmethod
    def get_sql_values_for_query(
        conn_cls: Any,
        values: dict[str, Any],
        column_types: dict[str, str],
    ) -> dict[str, Any]:
        """Function to prepare SQL values by calling connector method.

        Args:
            conn_cls (Any): DB Connection class
            values (dict[str, Any]): dictionary of columns and values
            column_types (dict[str, str]): types of columns from database schema

        Returns:
            dict[str, Any]: Dictionary of column names to SQL values
        """
        return conn_cls.get_sql_values_for_query(values=values, column_types=column_types)

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
        agent_name: str | None = AgentName.UNSTRACT_DBWRITER.value,
        single_column_name: str = "data",
        table_info: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Generate a dictionary of columns and values based on specified
        parameters.

        Args:
            column_mode_str (str): The string representation of the column mode,
                which determines how data is stored in the dictionary.
            data (Any): The data to be stored in the dictionary.
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
            dict: A dictionary containing columns and values based on
                the specified parameters.
        """
        values: dict[str, Any] = {}
        try:
            column_mode = ColumnModes(column_mode_str)
        except ValueError:
            # Handle the case where the string is not a valid enum value
            column_mode = ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN

        if include_agent and agent_name:
            values[TableColumns.CREATED_BY] = agent_name

        if include_timestamp:
            values[TableColumns.CREATED_AT] = datetime.datetime.now()

        has_metadata_col = (
            (table_info is None)
            or any(k.lower() == TableColumns.METADATA.lower() for k in table_info)
            if table_info
            else True
        )
        has_error_col = (
            (table_info is None)
            or any(k.lower() == TableColumns.ERROR_MESSAGE.lower() for k in table_info)
            if table_info
            else True
        )
        has_status_col = (
            (table_info is None)
            or any(k.lower() == TableColumns.STATUS.lower() for k in table_info)
            if table_info
            else True
        )

        if metadata and has_metadata_col:
            try:
                values[TableColumns.METADATA] = json.dumps(metadata)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize metadata to JSON: {e}")
                # Create a safe fallback error object
                fallback_metadata = DatabaseUtils._create_safe_error_json("metadata", e)
                values[TableColumns.METADATA] = json.dumps(fallback_metadata)

        if error and has_error_col:
            values[TableColumns.ERROR_MESSAGE] = error
        if has_status_col:
            values[TableColumns.STATUS] = (
                FileProcessingStatus.ERROR if error else FileProcessingStatus.SUCCESS
            )
        if column_mode == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
            if isinstance(data, str):
                wrapped_dict = {"result": data}
                values[single_column_name] = wrapped_dict
                values[f"{single_column_name}_v2"] = wrapped_dict
            else:
                values[single_column_name] = data
                values[f"{single_column_name}_v2"] = data
        values[file_path_name] = file_path
        values[execution_id_name] = execution_id
        logger.debug(f"database_utils.py get_columns_and_values  values: {values}")
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
            connector_cls: DB connection class
            table_name (str): The name of the target table for the insert query.
            values (dict[str, Any]): A dictionary containing column-value pairs
                for the insert query.

        Returns:
            list[str]: A list of SQL values suitable for use in an insert query.

        Note:
            - This function determines the database type based on the
                `engine` parameter.
            - If the database is Snowflake (DBConnectionClass.SNOWFLAKE),
                it handles Snowflake-specific SQL generation.
            - For other SQL databases, it uses default SQL generation
                based on column types.
        """
        column_types: dict[str, str] = DatabaseUtils.get_column_types(
            conn_cls=conn_cls, table_name=table_name
        )
        logger.debug(f"database_utils.py get_sql_query_data column_types: {column_types}")

        sql_columns_and_values = DatabaseUtils.get_sql_values_for_query(
            conn_cls=conn_cls,
            values=values,
            column_types=column_types,
        )
        logger.debug(
            f"database_utils.py get_sql_query_data sql_columns_and_values: {sql_columns_and_values}"
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
            engine (Any): _description_
            table_name (str): table name
            sql_keys (list[str]): columns
            sql_values (list[str]): values
        Notes:
        - Snowflake does not support INSERT INTO ... VALUES ...
          syntax when VARIANT columns are present (JSON).
          So we need to use INSERT INTO ... SELECT ... syntax
        - sql values can contain data with single quote. It needs to
        """
        sql = db_class.get_sql_insert_query(
            table_name=table_name, sql_keys=sql_keys, sql_values=sql_values
        )

        logger.debug(f"inserting into table {table_name} with: {sql} query")
        logger.debug(f"sql_values: {sql_values}")

        try:
            db_class.execute_query(
                engine=engine,
                sql_query=sql,
                sql_values=sql_values,
                table_name=table_name,
                sql_keys=sql_keys,
            )
        except UnstractDBConnectorException as e:
            raise UnstractDBException(detail=e.detail) from e
        logger.debug(f"sucessfully inserted into table {table_name} with: {sql} query")

    @staticmethod
    def get_db_class(connector_id: str, connector_settings: dict[str, Any]) -> UnstractDB:
        connector = db_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        connector_class: UnstractDB = connector(connector_settings)
        return connector_class

    @staticmethod
    def create_table_if_not_exists(
        db_class: UnstractDB,
        engine: Any,
        table_name: str,
        database_entry: dict[str, Any],
    ) -> None:
        """Creates table if not exists.

        Args:
            class_name (UnstractDB): Type of Unstract DB connector
            table_name (str): _description_
            database_entry (dict[str, Any]): _description_

        Raises:
            e: _description_
        """
        sql = db_class.create_table_query(table=table_name, database_entry=database_entry)
        logger.debug(f"creating table {table_name} with: {sql} query")

        try:
            db_class.execute_query(
                engine=engine, sql_query=sql, sql_values=None, table_name=table_name
            )
        except UnstractDBConnectorException as e:
            raise UnstractDBException(detail=e.detail) from e
        logger.debug(f"successfully created table {table_name} with: {sql} query")
