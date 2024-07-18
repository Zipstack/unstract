from rest_framework.exceptions import APIException


class InternalError(APIException):
    status_code = 400
    default_detail = "Internal service error."
