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

CREATE_TABLE_IF_NOT_EXISTS = "CREATE TABLE IF NOT EXISTS"


def _is_create_table_if_not_exists(sql_query: str) -> bool:
    """Check if query is a CREATE TABLE IF NOT EXISTS statement."""
    return sql_query.strip().upper().startswith(CREATE_TABLE_IF_NOT_EXISTS)


def _is_pg_type_race_condition(sql_query: str, constraint: str | None) -> bool:
    """Check if UniqueViolation is due to pg_type race during concurrent table creation.

    Args:
        sql_query: The SQL query that caused the error.
        constraint: The constraint name from the exception diagnostics.

    Returns:
        True if this is the pg_type race condition that should be suppressed.
    """
    return (
        _is_create_table_if_not_exists(sql_query)
        and constraint == "pg_type_typname_nsp_index"
    )


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
        except PsycopgError.DuplicateTable as e:
            engine.rollback()  # Always rollback - transaction is in failed state
            if _is_create_table_if_not_exists(sql_query):
                logger.info(
                    f"Table '{table_name}' was created by concurrent process. "
                    f"Continuing with existing table. (pg_type race condition)"
                )
                return
            logger.exception(f"DuplicateTable error: {e.pgerror}")
            raise
        except PsycopgError.UniqueViolation as e:
            engine.rollback()  # Always rollback - transaction is in failed state
            constraint = getattr(getattr(e, "diag", None), "constraint_name", None)
            if _is_pg_type_race_condition(sql_query, constraint):
                logger.info(
                    f"Table '{table_name}' race condition detected (UniqueViolation, "
                    f"constraint={constraint}). Continuing with existing table."
                )
                return
            logger.exception(
                f"UniqueViolation error (constraint={constraint}): {e.pgerror}"
            )
            raise
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
            logger.error(f"feature not supported in creating/inserting data: {e.pgerror}")
            raise FeatureNotSupportedException(detail=e.pgerror, database=database) from e
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
