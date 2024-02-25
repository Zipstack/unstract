from rest_framework.exceptions import APIException


class FetchAppListFailed(APIException):
    status_code = 400
    default_detail = "Failed to fetch App list."