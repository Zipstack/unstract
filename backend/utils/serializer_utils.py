from typing import Any

from account_v2.models import User
from rest_framework.request import Request
from utils.constants import Account


class SerializerUtils:
    @staticmethod
    def check_context_for_GET_or_POST(context: dict[str, Any]) -> bool:
        """Checks the context.

        Args:
            context (str): _description_

        Returns:
            bool: _description_
        """
        request: Request = context.get("request")
        if request and request.method in ("GET", "POST"):
            return True
        else:
            return False

    @staticmethod
    def update_created_and_modified_fields(
        validated_data: dict[str, Any], user: User, created_by: bool = False
    ) -> None:
        if created_by:
            validated_data.update({Account.CREATED_BY: user})
        validated_data.update({Account.MODIFIED_BY: user})
