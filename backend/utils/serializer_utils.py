from typing import Any

from rest_framework.request import Request
from utils.constants import Account

from backend.constants import FeatureFlag
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    from account_v2.models import User
else:
    from account.models import User


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
