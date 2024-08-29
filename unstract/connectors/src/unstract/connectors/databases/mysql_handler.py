import datetime
import logging
from typing import Any

import pymysql.err as MysqlError

from unstract.connectors.databases.exceptions import (
    ColumnMissingException,
    InvalidSyntaxException,
)
from unstract.connectors.databases.exceptions_helper import ExceptionHelper

logger = logging.getLogger(__name__)


class MysqlHandler:
    @staticmethod
    def sql_to_db_mapping(value: str) -> str:
        """
        Gets the python datatype of value and converts python datatype
        to corresponding DB datatype
        Args:
            value (str): _description_

        Returns:
            str: _description_
        """
        python_type = type(value)
        mapping = {
            str: "LONGTEXT",
            int: "BIGINT",
            float: "FLOAT",
            datetime.datetime: "TIMESTAMP",
        }
        return mapping.get(python_type, "LONGTEXT")

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
