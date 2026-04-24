"""Internal API views for Usage access by workers."""

import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView
from utils.user_context import UserContext

from unstract.core.data_models import UsageResponseData

from .helper import UsageHelper
from .models import Usage

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


class PagesProcessedInternalView(APIView):
    """Internal API view for workers to access aggregated pages processed.

    This endpoint allows workers to get aggregated pages processed
    for a specific file execution without direct database access.
    """

    def get(self, request: Request, file_execution_id: str) -> JsonResponse:
        """Get aggregated pages processed for a file execution.

        Args:
            request: HTTP request
            file_execution_id: File execution ID to get pages data for

        Returns:
            JSON response with aggregated pages processed count
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

            total_pages = UsageHelper.get_aggregated_pages_processed(
                run_id=file_execution_id
            )

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "file_execution_id": file_execution_id,
                        "total_pages_processed": total_pages,
                    },
                }
            )

        except Exception as e:
            logger.error(
                f"Error getting pages processed for file_execution_id {file_execution_id}: {e}",
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


class UsageBatchCreateView(APIView):
    """Bulk create usage records from worker finalization."""

    def post(self, request: Request) -> JsonResponse:
        records = request.data.get("records", [])
        if not records:
            return JsonResponse({"created": 0}, status=200)

        organization = UserContext.get_organization()
        if organization is None:
            logger.error(
                "UsageBatchCreateView received %d records with no organization; "
                "refusing to write rows that would be invisible to tenant dashboards",
                len(records),
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Organization context missing. "
                    "Worker must send X-Organization-ID.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        usage_objects = []
        for r in records:
            usage_objects.append(
                Usage(
                    organization=organization,
                    workflow_id=r.get("workflow_id", ""),
                    execution_id=r.get("execution_id", ""),
                    adapter_instance_id=r.get("adapter_instance_id", ""),
                    run_id=r.get("run_id"),
                    usage_type=r.get("usage_type", "llm"),
                    llm_usage_reason=r.get("llm_usage_reason", ""),
                    model_name=r.get("model_name", ""),
                    embedding_tokens=r.get("embedding_tokens", 0),
                    prompt_tokens=r.get("prompt_tokens", 0),
                    completion_tokens=r.get("completion_tokens", 0),
                    total_tokens=r.get("total_tokens", 0),
                    cost_in_dollars=r.get("cost_in_dollars", 0.0),
                    reference_id=r.get("reference_id"),
                    reference_type=r.get("reference_type"),
                    execution_time_ms=r.get("execution_time_ms"),
                    status=r.get("status"),
                    error_message=r.get("error_message"),
                )
            )
        created = Usage.objects.bulk_create(usage_objects)
        return JsonResponse({"created": len(created)}, status=201)
