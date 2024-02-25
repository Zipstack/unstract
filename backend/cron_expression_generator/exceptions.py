from rest_framework.exceptions import APIException


class CronGenerationError(APIException):
    status_code = 424
    default_detail = "Error generating schedule."


class CronDescriptionError(APIException):
    status_code = 500
    default_detail = "Error while summarizing schedule."
