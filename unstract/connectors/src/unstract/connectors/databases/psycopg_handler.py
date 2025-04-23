import logging
from typing import Any

from psycopg2 import errors as PsycopgError

from unstract.connectors.databases.exceptions import (
    ColumnMissingException,
    FeatureNotSupportedException,
    InvalidSchemaException,
    InvalidSyntaxException,
    OperationalException,
    UnderfinedTableException,
    ValueTooLongException,
)

logger = logging.getLogger(__name__)


class PsycoPgHandler:
    @staticmethod
    def execute_query(
        engine: Any,
        sql_query: str,
        sql_values: Any,
        database: Any,
        schema: str,
        table_name: str,
    ) -> None:
        try:
            with engine.cursor() as cursor:
                if sql_values:
                    cursor.execute(sql_query, sql_values)
                else:
                    cursor.execute(sql_query)
            engine.commit()
        except PsycopgError.InvalidSchemaName as e:
            logger.error(f"Invalid schema in creating table: {e.pgerror}")
            raise InvalidSchemaException(detail=e.pgerror, database=database) from e
        except PsycopgError.UndefinedTable as e:
            logger.error(f"Undefined table in inserting: {e.pgerror}")
            raise UnderfinedTableException(detail=e.pgerror, database=database) from e
        except PsycopgError.SyntaxError as e:
            logger.error(f"Invalid syntax in creating/inserting data: {e.pgerror}")
            raise InvalidSyntaxException(detail=e.pgerror, database=database) from e
        except PsycopgError.FeatureNotSupported as e:
            logger.error(
                f"feature not supported in creating/inserting data: {e.pgerror}"
            )
            raise FeatureNotSupportedException(
                detail=e.pgerror, database=database
            ) from e
        except (
            PsycopgError.StringDataRightTruncation,
            PsycopgError.InternalError_,
        ) as e:
            logger.error(f"value too long for datatype: {e.pgerror}")
            raise ValueTooLongException(detail=e.pgerror, database=database) from e
        except PsycopgError.UndefinedColumn as e:
            logger.error(f"Column missing in inserting data: {e.pgerror}")
            raise ColumnMissingException(
                detail=e.pgerror,
                database=database,
                schema=schema,
                table_name=table_name,
            ) from e
        except PsycopgError.OperationalError as e:
            logger.error(f"Operational error in creating/inserting data: {e.pgerror}")
            raise OperationalException(detail=e.pgerror, database=database) from e
