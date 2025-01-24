from rest_framework.exceptions import APIException


class InvalidDatetime(APIException):
    status_code = 400
    default_detail = "Invalid datetime format"


class InvalidDateRange(APIException):
    status_code = 400
    default_detail = "Invalid date range"
