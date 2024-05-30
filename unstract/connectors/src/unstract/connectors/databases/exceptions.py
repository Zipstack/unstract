from typing import Any

from rest_framework.exceptions import APIException


class UnstractDBConnectorException(APIException):
    status_code = 400
    default_detail = "Error creating/inserting to database. "

    def __init__(self, code: Any = status_code, detail: str = default_detail) -> None:
        super().__init__(code=code, detail=detail)


class InvalidSyntaxException(UnstractDBConnectorException):
    def __init__(self, code: Any, detail: Any, database: Any) -> None:
        default_detail = (
            f"Error creating/writing to {database}. Syntax incorrect. "
            f"Please check your table-name or schema. "
        )
        super().__init__(code=code, detail=default_detail + detail)


class InvalidSchemaException(UnstractDBConnectorException):
    def __init__(self, code: Any, detail: Any, database: str) -> None:
        default_detail = f"Error creating/writing to {database}. Schema not valid. "
        super().__init__(code=code, detail=default_detail + detail)


class UnderfinedTableException(UnstractDBConnectorException):
    def __init__(self, code: Any, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. Undefined table. "
            f"Please check your table-name or schema. "
        )
        super().__init__(code=code, detail=default_detail + detail)


class ValueTooLongException(UnstractDBConnectorException):
    def __init__(self, code: Any, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. "
            f"Size of the inserted data exceeds the limit provided by the database. "
        )
        super().__init__(code=code, detail=default_detail + detail)


class FeatureNotSupportedException(UnstractDBConnectorException):

    def __init__(self, code: Any, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. "
            f"Feature not supported sql error. "
        )
        super().__init__(code=code, detail=default_detail + detail)


class SnowflakeProgrammingException(UnstractDBConnectorException):

    def __init__(self, code: Any, detail: Any, database: str) -> None:
        default_detail = (
            f"Error creating/writing to {database}. "
            f"Please check your snowflake credentials. "
        )
        super().__init__(code, default_detail + detail)


class BigQueryForbiddenException(UnstractDBConnectorException):

    def __init__(self, code: Any, detail: Any, table_name: str) -> None:
        default_detail = (
            f"Error creating/writing to {table_name}. "
            f"Access forbidden in bigquery. Please check your permissions. "
        )
        super().__init__(code=code, detail=default_detail + detail)


class BigQueryNotFoundException(UnstractDBConnectorException):

    def __init__(self, code: Any, detail: str, table_name: str) -> None:
        default_detail = (
            f"Error creating/writing to {table_name}. "
            f"The requested resource was not found. "
        )
        super().__init__(code=code, detail=default_detail + detail)
