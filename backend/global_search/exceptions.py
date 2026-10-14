from rest_framework import status
from rest_framework.exceptions import APIException


class SearchUnavailable(APIException):
    """Search cannot answer because the database is unreachable or the
    connection is unusable. The client may retry; never "no matches".
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Search is temporarily unavailable."
    default_code = "search_unavailable"


class SearchFailed(APIException):
    """Every searched type failed for a reason other than the database being
    unreachable -- most likely a bug, so retrying will not help.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Search failed."
    default_code = "search_failed"
