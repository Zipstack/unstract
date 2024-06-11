import logging
from typing import Any

import pymysql.err as MysqlError

from unstract.connectors.databases.exceptions import InvalidSyntaxException
from unstract.connectors.databases.exceptions_helper import ExceptionHelper

logger = logging.getLogger(__name__)


class MysqlHandler:
    @staticmethod
    def execute_query(
        engine: Any, sql_query: str, sql_values: Any, database: Any
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
