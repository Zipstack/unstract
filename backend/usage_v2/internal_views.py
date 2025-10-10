"""Internal API views for Usage access by workers."""

import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView

from unstract.core.data_models import UsageResponseData

from .helper import UsageHelper

logger = logging.getLogger(__name__)


class UsageInternalView(APIView):
    """Internal API view for workers to access usage data.

    This endpoint allows workers to get aggregated token usage data
    for a specific file execution without direct database access.
    """

    def get(self, request: Request, file_execution_id: str) -> JsonResponse:
        """Get aggregated token usage for a file execution.

        Args:
            request: HTTP request (no additional parameters needed)
            file_execution_id: File execution ID to get usage data for

        Returns:
            JSON response with aggregated usage data using core data models
        """
        try:
            if not file_execution_id:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "file_execution_id parameter is required",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get aggregated token count using the existing helper
            result = UsageHelper.get_aggregated_token_count(run_id=file_execution_id)

            # Create UsageResponseData for type safety and consistency
            usage_data = UsageResponseData(
                file_execution_id=file_execution_id,
                embedding_tokens=result.get("embedding_tokens"),
                prompt_tokens=result.get("prompt_tokens"),
                completion_tokens=result.get("completion_tokens"),
                total_tokens=result.get("total_tokens"),
                cost_in_dollars=result.get("cost_in_dollars"),
            )

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "file_execution_id": file_execution_id,
                        "usage": usage_data.to_dict(),
                    },
                }
            )

        except Exception as e:
            logger.error(
                f"Error getting usage data for file_execution_id {file_execution_id}: {e}",
                exc_info=True,
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Internal server error",
                    "file_execution_id": file_execution_id,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
