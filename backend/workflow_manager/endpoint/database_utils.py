import datetime
import json
import logging
import uuid
from typing import Any, Optional

import google.api_core.exceptions
import pymssql._pymssql as PyMssql
import pymysql.err as MysqlError
import snowflake.connector.errors as SnowflakeError
from google.cloud import bigquery
from psycopg2 import errors as PsycopgError
from utils.constants import Common
from workflow_manager.endpoint.constants import (
    BigQuery,
    DBConnectionClass,
    TableColumns,
)
from workflow_manager.endpoint.exceptions import (
    BigQueryForbiddenException,
    BigQueryNotFoundException,
    BigQueryTableNotFound,
    FeatureNotSupportedException,
    InvalidSchemaException,
    InvalidSyntaxException,
    SnowflakeProgrammingException,
    UnderfinedTableException,
    UnstractDBException,
    ValueTooLongException,
)
from workflow_manager.workflow.enums import AgentName, ColumnModes

from unstract.connectors.databases import connectors as db_connectors
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
                type_x = column_types[col]
                if type_x == "VARIANT":
                    values[column] = values[column].replace("'", "\\'")
                    sql_values[column] = f"parse_json($${values[column]}$$)"
                else:
                    sql_values[column] = f"{values[column]}"
            elif cls_name == DBConnectionClass.BIGQUERY:
                col = column.lower()
                type_x = column_types[col]
                if type_x in BigQuery.COLUMN_TYPES:
                    sql_values[column] = f"{type_x}({values[column]})"
                else:
                    sql_values[column] = f"{values[column]}"
            else:
                # Default to Other SQL DBs
                # TODO: Handle numeric types with no quotes
                sql_values[column] = f"{values[column]}"
        if column_types.get("id"):
            uuid_id = str(uuid.uuid4())
            sql_values["id"] = f"{uuid_id}"
        return sql_values

    @staticmethod
    def get_column_types_util(columns_with_types: Any) -> dict[str, str]:
        """Converts db results columns_with_types to dict.

        Args:
            columns_with_types (Any): _description_

        Returns:
            dict[str, str]: _description_
        """
        column_types: dict[str, str] = {}
        for column_name, data_type in columns_with_types:
            column_types[column_name] = data_type
        return column_types

    @staticmethod
    def get_column_types(
        cls_name: Any,
        table_name: str,
        connector_id: str,
        connector_settings: dict[str, Any],
    ) -> Any:
        """Get db column name and types.

        Args:
            cls (Any): _description_
            table_name (str): _description_
            connector_id (str): _description_
            connector_settings (dict[str, Any]): _description_

        Raises:
            ValueError: _description_
            e: _description_

        Returns:
            Any: _description_
        """
        column_types: dict[str, str] = {}
        try:
            if cls_name == DBConnectionClass.SNOWFLAKE:
                query = f"describe table {table_name}"
                results = DatabaseUtils.execute_and_fetch_data(
                    connector_id=connector_id,
                    connector_settings=connector_settings,
                    query=query,
                )
                for column in results:
                    column_types[column[0].lower()] = column[1].split("(")[0]
            elif cls_name == DBConnectionClass.BIGQUERY:
                bigquery_table_name = str.lower(table_name).split(".")
                if len(bigquery_table_name) != BigQuery.TABLE_NAME_SIZE:
                    raise BigQueryTableNotFound()
                database = bigquery_table_name[0]
                schema = bigquery_table_name[1]
                table = bigquery_table_name[2]
                query = (
                    "SELECT column_name, data_type FROM "
                    f"{database}.{schema}.INFORMATION_SCHEMA.COLUMNS WHERE "
                    f"table_name = '{table}'"
                )
                results = DatabaseUtils.execute_and_fetch_data(
                    connector_id=connector_id,
                    connector_settings=connector_settings,
                    query=query,
                )
                column_types = DatabaseUtils.get_column_types_util(results)
            else:
                table_name = str.lower(table_name)
                query = (
                    "SELECT column_name, data_type FROM "
                    "information_schema.columns WHERE "
                    f"table_name = '{table_name}'"
                )
                results = DatabaseUtils.execute_and_fetch_data(
                    connector_id=connector_id,
                    connector_settings=connector_settings,
                    query=query,
                )
                column_types = DatabaseUtils.get_column_types_util(results)
        except Exception as e:
            logger.error(f"Error getting column types for {table_name}: {str(e)}")
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
    def get_sql_query_data(
        engine: Any,
        cls_name: str,
        connector_id: str,
        connector_settings: dict[str, Any],
        table_name: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate SQL columns and values for an insert query based on the
        provided values and table schema.

        Args:
            engine (Any): The database engine.
            connector_id: The connector id of the connector provided
            connector_settings: Connector settings provided by user
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
            cls_name=cls_name,
            table_name=table_name,
            connector_id=connector_id,
            connector_settings=connector_settings,
        )
        sql_columns_and_values = DatabaseUtils.get_sql_values_for_query(
            values=values,
            column_types=column_types,
            cls_name=cls_name,
        )
        return sql_columns_and_values

    @staticmethod
    def execute_write_query(
        engine: Any,
        cls_name: str,
        table_name: str,
        sql_keys: list[str],
        sql_values: Any,
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
        sql = DBConnectorQueryHelper.build_sql_insert_query(table_name, sql_keys)
        logger.debug(f"inserting into table {table_name} with: {sql} query")

        sql_values = DBConnectorQueryHelper.prepare_sql_values(cls_name, sql_values)
        logger.debug(f"sql_values: {sql_values}")

        try:
            if cls_name == DBConnectionClass.BIGQUERY:
                DBConnectorQueryHelper.execute_bigquery(
                    engine, table_name, sql_keys, sql_values
                )
            elif hasattr(engine, "cursor"):
                DBConnectorQueryHelper.execute_cursor_query(engine, sql, sql_values)
            else:
                DBConnectorQueryHelper.execute_generic_query(engine, sql, sql_values)
        except PsycopgError.UndefinedTable as e:
            logger.error(f"Undefined table in inserting: {e.pgerror}")
            raise UnderfinedTableException(code=e.pgcode, detail=e.pgerror)
        except PsycopgError.SyntaxError as e:
            logger.error(f"Invalid syntax in inserting data: {e.pgerror}")
            raise InvalidSyntaxException(code=e.pgcode, detail=e.pgerror)
        except PsycopgError.FeatureNotSupported as e:
            logger.error(f"feature not supported in inserting data: {e.pgerror}")
            raise FeatureNotSupportedException(code=e.pgcode, detail=e.pgerror)
        except PsycopgError.StringDataRightTruncation as e:
            logger.error(f"value too long for character datatype: {e.pgerror}")
            raise ValueTooLongException(code=e.pgcode, detail=e.pgerror)
        except SnowflakeError.ProgrammingError as e:
            logger.error(f"snowflake error in inserting table: {e.msg} {e.errno}")
            raise SnowflakeProgrammingException(code=e.errno, detail=e.msg)
        except (PyMssql.ProgrammingError, PyMssql.OperationalError) as e:
            error_code, error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(f"Invalid syntax in inserting mssql table: {error_details}")
            raise InvalidSyntaxException(code=error_code, detail=error_details)
        except MysqlError.ProgrammingError as e:
            error_code, error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(f"Invalid syntax in inserting mysql table: {error_details}")
            raise InvalidSyntaxException(code=error_code, detail=error_details)
        logger.debug(f"sucessfully inserted into table {table_name} with: {sql} query")

    @staticmethod
    def get_db_class(
        connector_id: str, connector_settings: dict[str, Any]
    ) -> UnstractDB:
        connector = db_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        connector_class: UnstractDB = connector(connector_settings)
        return connector_class

    @staticmethod
    def execute_and_fetch_data(
        connector_id: str, connector_settings: dict[str, Any], query: str
    ) -> Any:
        connector = db_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        connector_class: UnstractDB = connector(connector_settings)
        try:
            return connector_class.execute(query=query)
        except ConnectorError as e:
            raise UnstractDBException(detail=e.message)

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
            engine (Any): _description_
            table_name (str): _description_
            database_entry (dict[str, Any]): _description_

        Raises:
            e: _description_
        """
        sql = DBConnectorQueryHelper.create_table_query(
            conn_cls=db_class, table=table_name, database_entry=database_entry
        )
        logger.debug(f"creating table {table_name} with: {sql} query")
        try:
            if hasattr(engine, "cursor"):
                with engine.cursor() as cursor:
                    cursor.execute(sql)
                engine.commit()
            else:
                engine.query(sql)
        except PsycopgError.InvalidSchemaName as e:
            logger.error(f"Invalid schema in creating table: {e.pgerror}")
            raise InvalidSchemaException(code=e.pgcode, detail=e.pgerror)
        except PsycopgError.FeatureNotSupported as e:
            logger.error(f"feature not supported in creating table: {e.pgerror}")
            raise FeatureNotSupportedException(code=e.pgcode, detail=e.pgerror)
        except PsycopgError.SyntaxError as e:
            logger.error(f"Invalid syntax in creating table: {e.pgerror}")
            raise InvalidSyntaxException(code=e.pgcode, detail=e.pgerror)
        except SnowflakeError.ProgrammingError as e:
            logger.error(f"snowflake error in creating table: {e.msg} {e.errno}")
            raise SnowflakeProgrammingException(code=e.errno, detail=e.msg)
        except google.api_core.exceptions.Forbidden as e:
            logger.error(f"Forbidden exception in creating table: {str(e)}")
            raise BigQueryForbiddenException(code=e.code)
        except google.api_core.exceptions.NotFound as e:
            logger.error(f"Resource not found in creating table: {str(e)}")
            raise BigQueryNotFoundException(code=e.code)
        except (PyMssql.ProgrammingError, PyMssql.OperationalError) as e:
            error_code, error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(f"Invalid syntax in creating mssql table: {error_details}")
            raise InvalidSyntaxException(code=error_code, detail=error_details)
        except MysqlError.ProgrammingError as e:
            error_code, error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(f"Invalid syntax in creating mysql table: {error_details}")
            raise InvalidSyntaxException(code=error_code, detail=error_details)
        logger.debug(f"successfully created table {table_name} with: {sql} query")


class DBConnectorQueryHelper:
    """A class that helps to generate query for connector table operations."""

    @staticmethod
    def create_table_query(
        conn_cls: UnstractDB, table: str, database_entry: dict[str, Any]
    ) -> Any:
        sql_query = ""
        """Generate a SQL query to create a table, based on the provided
        database entry.

        Args:
            conn_cls (str): The database connector class.
                Should be one of 'BIGQUERY', 'SNOWFLAKE', or other.
            table (str): The name of the table to be created.
            database_entry (dict[str, Any]):
                A dictionary containing column names as keys
                and their corresponding values.

                These values are used to determine the data types,
                for the columns in the table.

        Returns:
            str: A SQL query string to create a table with the specified name,
            and column definitions.

        Note:
            - Each conn_cls have it's implementation for SQL create table query
            Based on the implementation, a base SQL create table query will be
            created containing Permanent columns
            - Each conn_cls also has a mapping to convert python datatype to
            corresponding column type (string, VARCHAR etc)
            - keys in database_entry will be converted to column type, and
            column values will be the valus in database_entry
            - base SQL create table will be appended based column type and
            values, and generates a complete SQL create table query
        """
        create_table_query = conn_cls.get_create_table_query(table=table)
        sql_query += create_table_query

        for key, val in database_entry.items():
            if key not in TableColumns.PERMANENT_COLUMNS:
                sql_type = conn_cls.sql_to_db_mapping(val)
                sql_query += f"{key} {sql_type}, "

        return sql_query.rstrip(", ") + ");"

    @staticmethod
    def build_sql_insert_query(table_name: str, sql_keys: list[str]) -> str:
        keys_str = ",".join(sql_keys)
        values_placeholder = ",".join(["%s" for _ in sql_keys])
        return f"INSERT INTO {table_name} ({keys_str}) VALUES ({values_placeholder})"

    @staticmethod
    def prepare_sql_values(cls_name: str, sql_values: Any) -> Any:
        if cls_name == DBConnectionClass.MSSQL:
            return tuple(sql_values)
        return sql_values

    @staticmethod
    def execute_cursor_query(engine: Any, sql: str, sql_values: tuple[Any]) -> None:
        with engine.cursor() as cursor:
            cursor.execute(sql, sql_values)
        engine.commit()

    @staticmethod
    def execute_bigquery(
        engine: Any, table_name: str, sql_keys: list[str], sql_values: list[Any]
    ) -> None:
        query = f"""
            INSERT INTO {table_name} ({', '.join(sql_keys)})
            VALUES ({', '.join(['@' + key for key in sql_keys])})
        """
        query_parameters = [
            bigquery.ScalarQueryParameter(key, "STRING", value)
            for key, value in zip(sql_keys, sql_values)
        ]
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        engine.query(query, job_config=job_config)

    @staticmethod
    def execute_generic_query(engine: Any, sql: str, sql_values: Any) -> None:
        engine.query(sql)


class ExceptionHelper:
    @staticmethod
    def extract_byte_exception(e: Exception) -> tuple[str, str]:
        error_message = str(e)
        error_code, error_details = eval(error_message)
        if isinstance(error_details, bytes):
            error_details = error_details.decode("utf-8")
        return error_code, error_message
