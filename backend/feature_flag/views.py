"""
    Feature Flag view file
Returns:
    evaluate response
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from utils.request.feature_flag import check_feature_flag_status, list_all_flags

logger = logging.getLogger(__name__)


@api_view(["POST"])
def evaluate_feature_flag(request: Request) -> Response:
    """Function to evaluate the feature flag.

    To-Do: Refactor to a class based view, use serializers (DRF).

    Args:
        request: request object

    Returns:
        evaluate response
    """
    try:
        flag_key = request.data.get("flag_key")

        if not flag_key:
            return Response(
                {"message": "Request paramteres are missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        flag_enabled = check_feature_flag_status(flag_key)
        return Response({"flag_status": flag_enabled}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("No response from server: %s", e)
        return Response(
            {"message": "No response from server"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
def list_feature_flags(request: Request) -> Response:
    """Function to list the feature flags.

    Args:
        request: request object

    Returns:
        list of feature flags
    """
    try:
        namespace_key = request.data.get("namespace") or "default"
        feature_flags = list_all_flags(namespace_key)
        return Response({"feature_flags": feature_flags}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("No response from server: %s", e)
        return Response(
            {"message": "No response from server"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
