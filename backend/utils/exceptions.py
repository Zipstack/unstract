from enum import Enum
from typing import Optional

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
        entity: Optional[Entity] = None,
        detail: Optional[str] = None,
        code: Optional[str] = None,
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
