from typing import Any


class FSConnectorError(Exception):
    """Base class for database-related exceptions from Unstract connectors."""

    def __init__(self, *args: object, detail: Any, status_code: Any = 500) -> None:
        super().__init__(*args)
        self.detail = detail
        self.status_code = status_code


class InvalidDirectoryPathException(FSConnectorError):

    def __init__(self, detail: Any) -> None:
        default_detail = (
            "Invalid directory. "
            "Please only include letter or number and hyphen for nested directory. "
        )
        status_code = 404
        super().__init__(detail=default_detail, status_code=status_code)
