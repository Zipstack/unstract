import datetime
import logging
from typing import Any

import pymysql.err as MysqlError

from unstract.connectors.constants import DatabaseTypeConstants
from unstract.connectors.databases.exceptions import (
    ColumnMissingException,
    InvalidSyntaxException,
)
from unstract.connectors.databases.exceptions_helper import ExceptionHelper

logger = logging.getLogger(__name__)

# MySQL/MariaDB connection error codes mapping
CONNECTION_ERROR_MESSAGES = {
    1045: "Authentication failed. Please check your username, password and ssl settings.",
    2003: "Cannot connect to server. Please check the host, port, and network connectivity.",
    1049: "Unknown database. Please verify the database name exists.",
    2005: "Unknown host. Please check the host address.",
    2006: "MySQL server has gone away. Connection was lost.",
    2013: "Lost connection to MySQL server during query.",
}


class MysqlHandler:
    @staticmethod
    def sql_to_db_mapping(value: Any, column_name: str | None = None) -> str:
        """Function to generate information schema of the corresponding table.

        Args:
            value (str): python datatype
            column_name (str | None): name of the column being mapped

        Returns:
            str: database columntype
        """
        data_type = type(value)

        if data_type in (dict, list):
            if column_name and column_name.endswith("_v2"):
                return str(DatabaseTypeConstants.MYSQL_JSON)
            else:
                return str(DatabaseTypeConstants.MYSQL_LONGTEXT)

        mapping = {
            str: DatabaseTypeConstants.MYSQL_LONGTEXT,
            int: DatabaseTypeConstants.MYSQL_BIGINT,
            float: DatabaseTypeConstants.MYSQL_FLOAT,
            datetime.datetime: DatabaseTypeConstants.MYSQL_TIMESTAMP,
        }
        return str(mapping.get(data_type, DatabaseTypeConstants.MYSQL_LONGTEXT))

    @staticmethod
    def execute_query(
        engine: Any,
        sql_query: str,
        sql_values: Any,
        database: Any,
        host: Any,
        table_name: str,
    ) -> None:
        try:
            with engine.cursor() as cursor:
                if sql_values:
                    cursor.execute(sql_query, sql_values)
                else:
                    cursor.execute(sql_query)
            engine.commit()
        except MysqlError.ProgrammingError as e:
            error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(
                f"Invalid syntax in creating/inserting mysql data: {error_details}"
            )
            raise InvalidSyntaxException(detail=error_details, database=database) from e
        except MysqlError.OperationalError as e:
            error_details = ExceptionHelper.extract_byte_exception(e=e)
            logger.error(f"Column missing in inserting data: {error_details}")
            raise ColumnMissingException(
                detail=error_details,
                database=database,
                table_name=table_name,
            ) from e

    @staticmethod
    def handle_connection_error(
        e: MysqlError.OperationalError, host: str, port: int, ssl_enabled: bool
    ) -> str:
        """Handle MySQL/MariaDB connection errors with user-friendly messages.

        Args:
            e: The OperationalError from pymysql
            host: Database host
            port: Database port
            ssl_enabled: Whether SSL is enabled

        Returns:
            str: User-friendly error message for UI display
        """
        error_code, original_message = e.args
        user_message = CONNECTION_ERROR_MESSAGES.get(error_code, original_message)

        ssl_context = ""
        if ssl_enabled is not None:
            ssl_context = f" (SSL {'enabled' if ssl_enabled else 'disabled'})"

        return (
            f"{user_message} Connection: '{host}:{port}'{ssl_context} \n"
            f"```\n{original_message}\n```"
        )
