"""Feature Flag view file
Returns:
    evaluate response
"""

import logging

from rest_framework import status, viewsets
from rest_framework.response import Response

from feature_flag.helper import FeatureFlagHelper

logger = logging.getLogger(__name__)


class FeatureFlagViewSet(viewsets.ViewSet):
    """A simple ViewSet for evaluating feature flag."""

    def evaluate(self, request):
        try:
            flag_key = request.data.get("flag_key")

            if not flag_key:
                return Response(
                    {"message": "Request parameters are missing."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            flag_enabled = FeatureFlagHelper.check_flag_status(flag_key)
            return Response({"flag_status": flag_enabled}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("No response from server: %s", e)
            return Response(
                {"message": "No response from server"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def list(self, request):
        try:
            namespace_key = request.query_params.get("namespace", "default")
            feature_flags = FeatureFlagHelper.list_all_flags(namespace_key)
            return Response({"feature_flags": feature_flags}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("No response from server: %s", e)
            return Response(
                {"message": "No response from server"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
