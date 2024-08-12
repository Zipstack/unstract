from typing import Any

from unstract.connectors.exceptions import ConnectorBaseException


class UnstractFSConnectorException(ConnectorBaseException):
    """Base class for database-related exceptions from Unstract connectors."""

    def __init__(
        self,
        detail: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        default_detail = "Error creating/inserting to database. "
        user_message = default_detail if not detail else detail
        super().__init__(*args, user_message=user_message, **kwargs)
        self.detail = user_message


class GoogleDriveAccessDeniedException(UnstractFSConnectorException):

    def __init__(self, detail: Any) -> None:
        default_detail = (
            "Access denied for Google Drive. Please check if the env variables are "
            "correctly configured for your app and they include all the necessary "
            "permissions."
        )
        super().__init__(detail=default_detail)
