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
