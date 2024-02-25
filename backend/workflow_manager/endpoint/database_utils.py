import datetime
import json
import logging
from typing import Any, Optional

from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.databases.unstract_db import UnstractDB
from utils.constants import Common
from workflow_manager.endpoint.constants import (
    DBConnectionClass,
    Snowflake,
    TableColumns,
)
from workflow_manager.workflow.enums import AgentName, ColumnModes

logger = logging.getLogger(__name__)


class DatabaseUtils:
    @staticmethod
    def make_sql_values_for_query(
        values: dict[str, Any], column_types: dict[str, str], cls: Any = None
    ) -> list[str]:
        """Making Sql Values for Query.

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
        """
        sql_values: list[str] = []
        for column in values:
            if cls == DBConnectionClass.SNOWFLAKE:
                col = column.lower()
                type_x = column_types[col]
                if type_x in Snowflake.COLUMN_TYPES:
                    sql_values.append(f"'{values[column]}'")
                elif type_x == "VARIANT":
                    values[column] = values[column].replace("'", "\\'")
                    sql_values.append(f"parse_json($${values[column]}$$)")
                else:
                    sql_values.append(f"{values[column]}")
            else:
                # Default to Other SQL DBs
                # TODO: Handle numeric types with no quotes
                sql_values.append(f"'{values[column]}'")

        return sql_values

    @staticmethod
    def get_column_types(
        engine: Any, table_name: str, cls: Any = None
    ) -> dict[str, str]:
        """Retrieve column types for a specified table from a database engine.

        Args:
            engine (Any): The database engine used to execute queries.
            table_name (str): The name of the table for which column types
                are retrieved.
            cls (Any, optional): The database connection class (e.g.,
                DBConnectionClass.SNOWFLAKE) for handling database-specific
                queries.
                Defaults to None.

        Returns:
            dict: A dictionary mapping column names to their respective data
            types.

        Raises:
            Exception: If there is an error while retrieving column types,
                an exception is raised. Exit.

        Note:
            - If `cls` is not provided or is None, the function assumes a
                Default SQL database and queries column types accordingly.
            - If `cls` is provided and matches DBConnectionClass.SNOWFLAKE,
                the function queries column types using Snowflake-specific
                syntax.
        """
        try:
            column_types: dict[str, str] = {}
            with engine.cursor() as cursor:
                if cls == DBConnectionClass.SNOWFLAKE:
                    results = cursor.execute(f"describe table {table_name}")
                    for column in results:
                        column_types[column[0].lower()] = column[1].split("(")[
                            0
                        ]
                else:
                    # Default to Other SQL DBs
                    # Postgresql treats the table names as in lowercase
                    # tested only with Postgresql
                    table_name = str.lower(table_name)
                    columns_with_types_query = (
                        "SELECT column_name, data_type FROM "
                        "information_schema.columns WHERE "
                        f"table_name = '{table_name}'"
                    )
                    cursor.execute(columns_with_types_query)
                    columns_with_types = cursor.fetchall()
                    for column_name, data_type in columns_with_types:
                        column_types[column_name] = data_type
        except Exception as e:
            logger.error(
                f"Error getting column types for {table_name}: {str(e)}"
            )
            raise e
        return column_types

    @staticmethod
    def get_columns_and_values(
        column_mode_str: str,
        data: Any,
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

        return values

    @staticmethod
    def get_sql_values_for_query(
        engine: Any, table_name: str, values: dict[str, Any]
    ) -> list[str]:
        """Generate SQL values for an insert query based on the provided values
        and table schema.

        Args:
            engine (Any): The database engine.
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

        if engine.__class__.__name__ == DBConnectionClass.SNOWFLAKE:
            # Handle Snowflake
            column_types: dict[str, str] = DatabaseUtils.get_column_types(
                engine=engine,
                table_name=table_name,
                cls=DBConnectionClass.SNOWFLAKE,
            )
            sql_values = DatabaseUtils.make_sql_values_for_query(
                values=values,
                column_types=column_types,
                cls=DBConnectionClass.SNOWFLAKE,
            )
        else:
            # Default to Other SQL DBs
            column_types = DatabaseUtils.get_column_types(
                engine=engine, table_name=table_name
            )
            sql_values = DatabaseUtils.make_sql_values_for_query(
                values=values, column_types=column_types
            )
        return sql_values

    @staticmethod
    def execute_write_query(
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
        """
        sql = (
            f"INSERT INTO {table_name} ({','.join(sql_keys)}) "
            f"SELECT {','.join(sql_values)}"
        )

        try:
            with engine.cursor() as cursor:
                cursor.execute(sql)
            engine.commit()
        except Exception as e:
            logger.error(f"Error while writing data: {str(e)}")
            raise e

    @staticmethod
    def get_db_engine(
        connector_id: str, connector_settings: dict[str, Any]
    ) -> Any:
        connector = db_connectors[connector_id][Common.METADATA][
            Common.CONNECTOR
        ]
        connector_class: UnstractDB = connector(connector_settings)
        return connector_class.get_engine()
