from typing import Any


class UnstractFSConnectorException(Exception):
    """Base class for database-related exceptions from Unstract connectors."""

    def __init__(self, *args: object, detail: Any, status_code: Any = 500) -> None:
        super().__init__(*args)
        self.detail = detail
        self.status_code = status_code


class AccessDeniedException(UnstractFSConnectorException):

    def __init__(self, detail: Any) -> None:
        default_detail = "Permission denied. Please check your credentials. "
        status_code = 403
        super().__init__(detail=default_detail, status_code=status_code)
