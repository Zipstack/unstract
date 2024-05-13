from logs_helper.constants import LogsHelperExceptionMessages
from rest_framework.exceptions import APIException


class MissingFieldsKeyError(APIException):
    status_code = 400
    default_detail = LogsHelperExceptionMessages.MISSING_FIELDS


class InvalidValueError(APIException):
    status_code = 400
    default_detail = LogsHelperExceptionMessages.INVALID_VALUE
