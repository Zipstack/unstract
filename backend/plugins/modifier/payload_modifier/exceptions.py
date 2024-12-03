from rest_framework.exceptions import APIException


class StartPageIndexError(APIException):
    status_code = 400
    default_detail = (
        "The start page value must not be less "
        "than the end page value. Please verify your values"
    )


class PageRangeError(APIException):
    status_code = 400
    default_detail = (
        "Page numbers must be positive values. "
        " Please review and correct your input."
    )
