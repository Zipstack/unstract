from rest_framework.exceptions import APIException


class InvalidDateRange(APIException):
    status_code = 400
    default_detail = "Invalid date range"


class InvalidDatetime(APIException):
    status_code = 400
    default_detail = "Invalid datetime format"
