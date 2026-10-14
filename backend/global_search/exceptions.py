from rest_framework import status
from rest_framework.exceptions import APIException


class SearchUnavailable(APIException):
    """Search cannot answer at all: every searched type failed, or the
    database connection is unusable. A dependency failure the client may
    retry, never a "no matches" result.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Search is temporarily unavailable."
    default_code = "search_unavailable"
