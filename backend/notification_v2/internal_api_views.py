"""Internal API views for notification data access by workers.

These endpoints provide notification configuration data to workers
without exposing full Django models or requiring Django dependencies.

Security Note:
- CSRF protection is disabled for internal service-to-service communication
- Authentication is handled by InternalAPIAuthMiddleware using Bearer tokens
- These endpoints are not accessible from browsers and don't use session cookies
"""

import logging

from api_v2.models import APIDeployment
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pipeline_v2.models import Pipeline
from utils.organization_utils import filter_queryset_by_organization

from notification_v2.models import Notification

logger = logging.getLogger(__name__)

# Constants for error messages
INTERNAL_SERVER_ERROR_MSG = "Internal server error"


# CSRF exemption is safe here because:
# 1. This is service-to-service communication (workers → backend)
# 2. Authentication uses Bearer tokens (INTERNAL_SERVICE_API_KEY)
# 3. No browser sessions or cookies involved
# 4. InternalAPIAuthMiddleware provides adequate protection
@csrf_exempt
@require_http_methods(["GET"])
def get_pipeline_notifications(request, pipeline_id):
    """Get active notifications for a pipeline or API deployment.

    Used by callback worker to fetch notification configuration.
    """
    try:
        # Try to find the pipeline ID in Pipeline model first
        pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
        pipeline_queryset = filter_queryset_by_organization(
            pipeline_queryset, request, "organization"
        )

        if pipeline_queryset.exists():
            pipeline = pipeline_queryset.first()

            # Get active notifications for this pipeline
            notifications = Notification.objects.filter(pipeline=pipeline, is_active=True)

            notifications_data = []
            for notification in notifications:
                notifications_data.append(
                    {
                        "id": str(notification.id),
                        "notification_type": notification.notification_type,
                        "url": notification.url,
                        "authorization_type": notification.authorization_type,
                        "authorization_key": notification.authorization_key,
                        "authorization_header": notification.authorization_header,
                        "max_retries": notification.max_retries,
                        "is_active": notification.is_active,
                    }
                )

            return JsonResponse(
                {
                    "status": "success",
                    "pipeline_id": str(pipeline.id),
                    "pipeline_name": pipeline.pipeline_name,
                    "pipeline_type": pipeline.pipeline_type,
                    "notifications": notifications_data,
                }
            )
        else:
            # If not found in Pipeline, try APIDeployment model
            api_queryset = APIDeployment.objects.filter(id=pipeline_id)
            api_queryset = filter_queryset_by_organization(
                api_queryset, request, "organization"
            )

            if api_queryset.exists():
                api = api_queryset.first()

                # Get active notifications for this API deployment
                notifications = Notification.objects.filter(api=api, is_active=True)

                notifications_data = []
                for notification in notifications:
                    notifications_data.append(
                        {
                            "id": str(notification.id),
                            "notification_type": notification.notification_type,
                            "url": notification.url,
                            "authorization_type": notification.authorization_type,
                            "authorization_key": notification.authorization_key,
                            "authorization_header": notification.authorization_header,
                            "max_retries": notification.max_retries,
                            "is_active": notification.is_active,
                        }
                    )

                return JsonResponse(
                    {
                        "status": "success",
                        "pipeline_id": str(api.id),
                        "pipeline_name": api.api_name,
                        "pipeline_type": "API",
                        "notifications": notifications_data,
                    }
                )
            else:
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


# CSRF exemption is safe for internal service-to-service communication
# Protected by InternalAPIAuthMiddleware Bearer token authentication
@csrf_exempt
@require_http_methods(["GET"])
def get_api_notifications(request, api_id):
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

        # Get active notifications for this API
        notifications = Notification.objects.filter(api=api, is_active=True)

        notifications_data = []
        for notification in notifications:
            notifications_data.append(
                {
                    "id": str(notification.id),
                    "notification_type": notification.notification_type,
                    "url": notification.url,
                    "authorization_type": notification.authorization_type,
                    "authorization_key": notification.authorization_key,
                    "authorization_header": notification.authorization_header,
                    "max_retries": notification.max_retries,
                    "is_active": notification.is_active,
                }
            )

        return JsonResponse(
            {
                "status": "success",
                "api_id": str(api.id),
                "api_name": api.api_name,
                "display_name": api.display_name,
                "notifications": notifications_data,
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


# CSRF exemption is safe for internal service-to-service communication
# Protected by InternalAPIAuthMiddleware Bearer token authentication
@csrf_exempt
@require_http_methods(["GET"])
def get_pipeline_data(request, pipeline_id):
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


# CSRF exemption is safe for internal service-to-service communication
# Protected by InternalAPIAuthMiddleware Bearer token authentication
@csrf_exempt
@require_http_methods(["GET"])
def get_api_data(request, api_id):
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
