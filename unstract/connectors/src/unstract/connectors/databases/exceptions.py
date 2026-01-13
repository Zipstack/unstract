from typing import Any

from unstract.connectors.exceptions import ConnectorBaseException


class UnstractDBConnectorException(ConnectorBaseException):
    """Base class for database-related exceptions from Unstract connectors."""

    def __init__(self, detail: Any, *args: Any, **kwargs: Any) -> None:
        default_detail = "Error creating/inserting to database. "
        user_message = default_detail if not detail else detail
        super().__init__(*args, user_message=user_message, **kwargs)
        self.detail = user_message


class InvalidSyntaxException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: Any) -> None:
        default_detail = (
            f"Error creating/writing to `{database}`. Syntax incorrect. "
            f"Please check your table-name or schema. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class InvalidSchemaException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str) -> None:
        default_detail = f"Error creating/writing to {database}. Schema not valid. "
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class UnderfinedTableException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. Undefined table. "
            f"Please check your table-name or schema. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class ValueTooLongException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. "
            f"Size of the inserted data exceeds the limit provided by the database. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class FeatureNotSupportedException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. Feature not supported sql error. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class SnowflakeProgrammingException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str, table_name: str, schema: str) -> None:
        default_detail = (
            f"Error creating/writing to `{database}.{schema}.{table_name}' \n"
            f"Please make sure all the columns exist in your table as per destination "
            f"DB configuration \n and snowflake credentials are correct.\n"
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class BigQueryForbiddenException(UnstractDBConnectorException):
    def __init__(self, detail: Any, table_name: str) -> None:
        default_detail = (
            f"Error creating/writing to {table_name}. "
            f"Access forbidden in bigquery. Please check your permissions. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class BigQueryNotFoundException(UnstractDBConnectorException):
    def __init__(self, detail: str, table_name: str) -> None:
        default_detail = (
            f"Error creating/writing to {table_name}. "
            f"The requested resource was not found. "
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class ColumnMissingException(UnstractDBConnectorException):
    def __init__(
        self,
        detail: Any,
        database: Any,
        table_name: str,
        schema: str | None = None,
    ) -> None:
        schema_part = f".{schema}" if schema else ""
        default_detail = (
            f"Error writing to '{database}{schema_part}.{table_name}'. \n"
            f"Please make sure all the columns exist in your table "
            f"as per the destination DB configuration.\n"
        )
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


class OperationalException(UnstractDBConnectorException):
    def __init__(self, detail: Any, database: str) -> None:
        default_detail = f"Error creating/writing to {database}. Operational error. "
        final_detail = _format_exception_detail(default_detail, detail)
        super().__init__(detail=final_detail)


def _format_exception_detail(base_error: str, library_error: Any) -> str:
    """Format exception detail by combining base error with library-specific details.

    Args:
        base_error: The base error message describing the error type
        library_error: The actual error detail from the database library

    Returns:
        Formatted error message combining both if library_error exists,
        otherwise just the base_error
    """
    return f"{base_error}\nDetails: {library_error}" if library_error else base_error
