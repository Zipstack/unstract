from rest_framework.exceptions import APIException


class PlatformServiceError(APIException):
    status_code = 400
    default_detail = "Seems an error occured in Platform Service."
