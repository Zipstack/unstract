from rest_framework.exceptions import APIException

from platform_api.constants import PLATFORM_API_KEY_MAX_COUNT


class KeyCountExceeded(APIException):
    status_code = 400
    default_detail = (
        f"Maximum platform API key limit of {PLATFORM_API_KEY_MAX_COUNT} exceeded."
    )
