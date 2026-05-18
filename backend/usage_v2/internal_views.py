"""Internal API views for Usage access by workers.

Mounted under ``/internal/`` and gated by ``InternalAPIAuthMiddleware``.
"""

import logging

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.user_context import UserContext

from unstract.core.data_models import UsageResponseData

from .helper import UsageHelper
from .hooks import run_post_write_hooks
from .models import Usage
from .serializers import UsageBatchCreateSerializer

logger = logging.getLogger(__name__)


class UsagePersistError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to persist usage records."
    default_code = "usage_persist_failed"


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

    def post(self, request: Request) -> Response:
        input_serializer = UsageBatchCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        records = input_serializer.validated_data["records"]
        if not records:
            return Response({"created": 0}, status=status.HTTP_200_OK)

        organization = UserContext.get_organization()
        if organization is None:
            logger.error(
                "UsageBatchCreateView received %d records with no organization; "
                "refusing to write rows that would be invisible to tenant dashboards",
                len(records),
            )
            raise ValidationError(
                "Organization context missing. Worker must send X-Organization-ID."
            )

        usage_objects = [
            Usage(
                organization=organization,
                workflow_id=r.get("workflow_id", ""),
                execution_id=r.get("execution_id", ""),
                adapter_instance_id=r.get("adapter_instance_id", ""),
                run_id=r.get("run_id"),
                usage_type=r.get("usage_type", "llm"),
                # Coerce "" to None so the cross-field CheckConstraint passes.
                llm_usage_reason=r.get("llm_usage_reason") or None,
                model_name=r.get("model_name", ""),
                embedding_tokens=r.get("embedding_tokens", 0),
                prompt_tokens=r.get("prompt_tokens", 0),
                completion_tokens=r.get("completion_tokens", 0),
                total_tokens=r.get("total_tokens", 0),
                cost_in_dollars=r.get("cost_in_dollars", 0.0),
                project_id=r.get("project_id"),
                prompt_id=r.get("prompt_id"),
                execution_time_ms=r.get("execution_time_ms"),
                status=r.get("status"),
                error_message=r.get("error_message"),
            )
            for r in records
        ]

        try:
            # Atomic with hooks: orphan Usage rows are worse than retrying.
            with transaction.atomic():
                created = Usage.objects.bulk_create(usage_objects, batch_size=500)
                run_post_write_hooks(records, created)
        except Exception as e:
            logger.error(
                "bulk_create failed for %d usage records (org=%s): %s",
                len(usage_objects),
                organization.organization_id,
                e,
                exc_info=True,
            )
            raise UsagePersistError() from e
        return Response({"created": len(created)}, status=status.HTTP_201_CREATED)
