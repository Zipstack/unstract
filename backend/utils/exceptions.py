from enum import Enum

from rest_framework.exceptions import APIException


class InvalidEncryptionKey(APIException):
    status_code = 403
    default_detail = (
        "Platform encryption key for storing sensitive credentials has changed! "
        "All encrypted entities are inaccessible. Please inform the "
        "platform admin immediately."
    )

    class Entity(Enum):
        ADAPTER = "adapter"
        CONNECTOR = "connector"

    def __init__(
        self,
        entity: Entity | None = None,
        detail: str | None = None,
        code: str | None = None,
    ) -> None:
        if entity == self.Entity.ADAPTER:
            detail = self.default_detail.replace("sensitive", "adapter").replace(
                "encrypted entities", "adapters"
            )
        elif entity == self.Entity.CONNECTOR:
            detail = self.default_detail.replace("sensitive", "connector").replace(
                "encrypted entities", "connectors"
            )

        super().__init__(detail, code)
