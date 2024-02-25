import logging

from apps.exceptions import FetchAppListFailed
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(("GET",))
def get_app_list(request: Request) -> Response:
    """API to fetch List of Apps."""
    if request.method == "GET":
        try:
            return Response(data=[], status=status.HTTP_200_OK)
        # Refactored dated: 19/12/2023
        # ( Removed -> backend/apps/app_processor.py )
        except Exception as exe:
            logger.error(f"Error occured while fetching app list {exe}")
            raise FetchAppListFailed()
