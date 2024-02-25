from rest_framework.exceptions import APIException


class MethodNotImplemented(APIException):
    status_code = 501
    default_detail = "Method Not Implemented"
