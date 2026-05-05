"""Internal API views for notification data access by workers.

These endpoints provide notification configuration data to workers
without exposing full Django models or requiring Django dependencies.

Security Note:
- CSRF protection is disabled for internal service-to-service communication
- Authentication is handled by InternalAPIAuthMiddleware using Bearer tokens
- These endpoints are not accessible from browsers and don't use session cookies
"""

import logging
from typing import Any, cast

from api_v2.models import APIDeployment
from django.db.models import QuerySet
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pipeline_v2.models import Pipeline
from utils.organization_utils import filter_queryset_by_organization
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from notification_v2.models import Notification

logger = logging.getLogger(__name__)

# Constants for error messages
INTERNAL_SERVER_ERROR_MSG = "Internal server error"

_FAILURE_STATUSES = {ExecutionStatus.ERROR.value, ExecutionStatus.STOPPED.value}


def _load_execution(execution_id: str | None) -> WorkflowExecution | None:
    """Best-effort lookup; returns None on missing id or unknown row."""
    if not execution_id:
        return None
    try:
        return cast(WorkflowExecution, WorkflowExecution.objects.get(id=execution_id))
    except WorkflowExecution.DoesNotExist:
        logger.warning("WorkflowExecution %s not found", execution_id)
        return None


def _apply_failure_filter(
    notifications_qs: QuerySet[Notification],
    execution: WorkflowExecution | None,
) -> QuerySet[Notification]:
    """Drop notify_on_failures=True rows on success runs.

    Mirrors the dispatch-side rule in backend/api_v2/notification.py and
    backend/pipeline_v2/notification.py so both code paths agree on what
    counts as a failure (status ∈ {ERROR, STOPPED} OR any file errored).

    No execution → no filter, preserving legacy "return every active row"
    behavior for callers that don't pass execution_id.
    """
    if execution is None:
        return notifications_qs
    failed_files = execution.failed_files or 0
    is_failure = execution.status in _FAILURE_STATUSES or failed_files > 0
    if not is_failure:
        notifications_qs = notifications_qs.filter(notify_on_failures=False)
    return notifications_qs


def _execution_counts(execution: WorkflowExecution | None) -> dict[str, int]:
    """File counts surfaced into webhook payloads. Empty dict on no execution."""
    if execution is None:
        return {}
    return {
        "total_files": execution.total_files or 0,
        "successful_files": execution.successful_files or 0,
        "failed_files": execution.failed_files or 0,
    }


def _serialize_notification(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "notification_type": n.notification_type,
        "platform": n.platform,
        "url": n.url,
        "authorization_type": n.authorization_type,
        "authorization_key": n.authorization_key,
        "authorization_header": n.authorization_header,
        "max_retries": n.max_retries,
        "is_active": n.is_active,
        "notify_on_failures": n.notify_on_failures,
    }


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_pipeline_notifications(request: HttpRequest, pipeline_id: str) -> JsonResponse:
    """Get active notifications for a pipeline or API deployment.

    Used by callback worker to fetch notification configuration.
    """
    try:
        # Try to find the pipeline ID in Pipeline model first
        pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
        pipeline_queryset = filter_queryset_by_organization(
            pipeline_queryset, request, "organization"
        )

        execution = _load_execution(request.GET.get("execution_id"))
        counts = _execution_counts(execution)

        if pipeline_queryset.exists():
            pipeline = pipeline_queryset.first()
            notifications = Notification.objects.filter(pipeline=pipeline, is_active=True)
            notifications = _apply_failure_filter(notifications, execution)
            serialized = [_serialize_notification(n) for n in notifications]
            return JsonResponse(
                {
                    "status": "success",
                    "pipeline_id": str(pipeline.id),
                    "pipeline_name": pipeline.pipeline_name,
                    "pipeline_type": pipeline.pipeline_type,
                    "notifications": serialized,
                    "execution_counts": counts,
                }
            )

        # If not found in Pipeline, try APIDeployment model
        api_queryset = APIDeployment.objects.filter(id=pipeline_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        if api_queryset.exists():
            api = api_queryset.first()
            notifications = Notification.objects.filter(api=api, is_active=True)
            notifications = _apply_failure_filter(notifications, execution)
            serialized = [_serialize_notification(n) for n in notifications]
            return JsonResponse(
                {
                    "status": "success",
                    "pipeline_id": str(api.id),
                    "pipeline_name": api.api_name,
                    "pipeline_type": "API",
                    "notifications": serialized,
                    "execution_counts": counts,
                }
            )

        return JsonResponse(
            {
                "status": "error",
                "message": "Pipeline or API deployment not found",
            },
            status=404,
        )
    except Exception as e:
        logger.error(f"Error getting pipeline notifications for {pipeline_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_api_notifications(request: HttpRequest, api_id: str) -> JsonResponse:
    """Get active notifications for an API deployment.

    Used by callback worker to fetch notification configuration.
    """
    try:
        # Get API deployment with organization filtering
        api_queryset = APIDeployment.objects.filter(id=api_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        api = get_object_or_404(api_queryset)

        execution = _load_execution(request.GET.get("execution_id"))
        notifications = Notification.objects.filter(api=api, is_active=True)
        notifications = _apply_failure_filter(notifications, execution)

        return JsonResponse(
            {
                "status": "success",
                "api_id": str(api.id),
                "api_name": api.api_name,
                "display_name": api.display_name,
                "notifications": [_serialize_notification(n) for n in notifications],
                "execution_counts": _execution_counts(execution),
            }
        )

    except APIDeployment.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "API deployment not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting API notifications for {api_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_pipeline_data(request: HttpRequest, pipeline_id: str) -> JsonResponse:
    """Get basic pipeline data for notification purposes.

    Used by callback worker to determine pipeline type and name.
    """
    try:
        # Get pipeline with organization filtering
        pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
        pipeline_queryset = filter_queryset_by_organization(
            pipeline_queryset, request, "organization"
        )
        pipeline = get_object_or_404(pipeline_queryset)

        return JsonResponse(
            {
                "status": "success",
                "pipeline_id": str(pipeline.id),
                "pipeline_name": pipeline.pipeline_name,
                "pipeline_type": pipeline.pipeline_type,
                "last_run_status": pipeline.last_run_status,
            }
        )

    except Pipeline.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Pipeline not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting pipeline data for {pipeline_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_api_data(request: HttpRequest, api_id: str) -> JsonResponse:
    """Get basic API deployment data for notification purposes.

    Used by callback worker to determine API name and details.
    """
    try:
        # Get API deployment with organization filtering
        api_queryset = APIDeployment.objects.filter(id=api_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        api = get_object_or_404(api_queryset)

        return JsonResponse(
            {
                "status": "success",
                "api_id": str(api.id),
                "api_name": api.api_name,
                "display_name": api.display_name,
                "is_active": api.is_active,
            }
        )

    except APIDeployment.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "API deployment not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting API data for {api_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )
