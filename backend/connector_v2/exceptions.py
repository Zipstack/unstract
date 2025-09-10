from rest_framework.exceptions import APIException


class DeleteConnectorInUseError(APIException):
    status_code = 409

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        connector_name: str = "connector",
    ):
        if detail is None:
            if connector_name != "connector":
                connector_name = f"'{connector_name}'"
            detail = (
                f"Cannot delete {connector_name}. "
                "It is currently being used in one or more workflows"
            )
        super().__init__(detail, code)
