from rest_framework.exceptions import APIException


class KeyCountExceeded(APIException):
    status_code = 400
    default_detail = "Maximum platform API key count exceeded."
