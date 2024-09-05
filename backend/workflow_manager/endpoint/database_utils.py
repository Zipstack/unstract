import datetime
import json
import logging
import uuid
from typing import Any, Optional

from utils.constants import Common
from workflow_manager.endpoint.constants import DBConnectionClass, TableColumns
from workflow_manager.endpoint.exceptions import UnstractDBException
from workflow_manager.workflow.enums import AgentName, ColumnModes

from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.databases.exceptions import UnstractDBConnectorException
from unstract.connectors.databases.unstract_db import UnstractDB
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class DatabaseUtils:
    @staticmethod
    def get_sql_values_for_query(
        values: dict[str, Any], column_types: dict[str, str], cls_name: str
    ) -> dict[str, str]:
        """Making Sql Columns and Values for Query.

        Args:
            values (dict[str, Any]): dictionary of columns and values
            column_types (dict[str,str]): types of columns
            cls (Any, optional): The database connection class (e.g.,
                DBConnectionClass.SNOWFLAKE) for handling database-specific
                queries.
                Defaults to None.

        Returns:
            list[str]: _description_

        Note:
            - If `cls` is not provided or is None, the function assumes a
                Default SQL database and makes values accordingly.
            - If `cls` is provided and matches DBConnectionClass.SNOWFLAKE,
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
        except Exception as e:
            logger.error(f"Error getting column types for {table_name}: {str(e)}")
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
        agent_name: Optional[str] = AgentName.UNSTRACT_DBWRITER.value,
        single_column_name: str = "data",
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

        if column_mode == ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN:
            if isinstance(data, str):
                values[single_column_name] = data
            else:
                values[single_column_name] = json.dumps(data)
        if column_mode == ColumnModes.SPLIT_JSON_INTO_COLUMNS:
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
        cls_name = conn_cls.__class__.__name__
        column_types: dict[str, str] = DatabaseUtils.get_column_types(
            conn_cls=conn_cls, table_name=table_name
        )
        sql_columns_and_values = DatabaseUtils.get_sql_values_for_query(
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
        sql = db_class.get_sql_insert_query(table_name=table_name, sql_keys=sql_keys)

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
    def get_db_class(
        connector_id: str, connector_settings: dict[str, Any]
    ) -> UnstractDB:
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
        sql = db_class.create_table_query(
            table=table_name, database_entry=database_entry
        )
        logger.debug(f"creating table {table_name} with: {sql} query")
        try:
            db_class.execute_query(
                engine=engine, sql_query=sql, sql_values=None, table_name=table_name
            )
        except UnstractDBConnectorException as e:
            raise UnstractDBException(detail=e.detail) from e
        logger.debug(f"successfully created table {table_name} with: {sql} query")
