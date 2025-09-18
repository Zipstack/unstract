"""Internal API URL Configuration - OSS Base.

Base internal URL patterns for OSS deployment. This file contains
the foundational internal APIs available in all deployments.

Cloud deployments extend this via cloud_internal_urls.py following
the same pattern as base_urls.py / cloud_base_urls.py.
"""

from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_http_methods
from utils.websocket_views import emit_websocket


@require_http_methods(["GET"])
def internal_api_root(request):
    """Internal API root endpoint with comprehensive documentation."""
    return JsonResponse(
        {
            "message": "Unstract Internal API",
            "version": "1.0.0",
            "description": "Internal service-to-service API for Celery workers",
            "documentation": "https://docs.unstract.com/internal-api",
            "endpoints": {
                "description": "Various v1 endpoints for workflow execution, pipeline, organization, and other services",
                "base_path": "/internal/v1/",
            },
            "authentication": {
                "type": "Bearer Token",
                "header": "Authorization: Bearer <internal_service_api_key>",
                "organization": "X-Organization-ID header (optional for scoped requests)",
                "requirements": [
                    "All requests must include Authorization header",
                    "API key must match INTERNAL_SERVICE_API_KEY setting",
                    "Organization ID header required for org-scoped operations",
                ],
            },
            "response_format": {
                "success": {"status": "success", "data": "..."},
                "error": {"error": "Error message", "detail": "Additional details"},
            },
            "rate_limits": {
                "default": "No rate limits for internal services",
                "note": "Monitor usage through application logs",
            },
        }
    )


@require_http_methods(["GET"])
def internal_health_check(request):
    """Health check endpoint for internal API."""
    try:
        # Debug information
        debug_info = {
            "has_internal_service": hasattr(request, "internal_service"),
            "internal_service_value": getattr(request, "internal_service", None),
            "auth_header": request.META.get("HTTP_AUTHORIZATION", "None"),
            "path": request.path,
            "method": request.method,
        }

        # Check authentication - first check middleware, then fallback to direct key check
        authenticated = False

        if hasattr(request, "internal_service") and request.internal_service:
            authenticated = True
        else:
            # Fallback: check API key directly if middleware didn't run
            from django.conf import settings

            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]  # Remove 'Bearer ' prefix
                internal_api_key = getattr(settings, "INTERNAL_SERVICE_API_KEY", None)
                if internal_api_key and api_key == internal_api_key:
                    authenticated = True
                    # Set the flag manually since middleware didn't run
                    request.internal_service = True

        if not authenticated:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Not authenticated as internal service",
                    "debug": debug_info,
                },
                status=401,
            )

        # Basic health checks
        health_data = {
            "status": "healthy",
            "service": "internal_api",
            "version": "1.0.0",
            "timestamp": request.META.get("HTTP_DATE"),
            "authenticated": True,
            "organization_id": getattr(request, "organization_id", None),
            "debug": debug_info,
        }

        return JsonResponse(health_data)

    except Exception as e:
        return JsonResponse(
            {
                "status": "error",
                "message": "Health check failed",
                "error": str(e),
                "debug": {
                    "has_internal_service": hasattr(request, "internal_service"),
                    "auth_header": request.META.get("HTTP_AUTHORIZATION", "None"),
                    "path": request.path,
                },
            },
            status=500,
        )


# Test endpoint to debug middleware
@require_http_methods(["GET"])
def test_middleware_debug(request):
    """Debug endpoint to check middleware execution."""
    from django.conf import settings

    return JsonResponse(
        {
            "middleware_debug": {
                "path": request.path,
                "method": request.method,
                "auth_header": request.META.get("HTTP_AUTHORIZATION", "None"),
                "has_internal_service": hasattr(request, "internal_service"),
                "internal_service_value": getattr(request, "internal_service", None),
                "authenticated_via": getattr(request, "authenticated_via", None),
                "organization_id": getattr(request, "organization_id", None),
                "internal_api_key_configured": bool(
                    getattr(settings, "INTERNAL_SERVICE_API_KEY", None)
                ),
                "internal_api_key_length": len(
                    getattr(settings, "INTERNAL_SERVICE_API_KEY", "")
                )
                if getattr(settings, "INTERNAL_SERVICE_API_KEY", None)
                else 0,
            }
        }
    )


# Internal API URL patterns - OSS Base
urlpatterns = [
    # Internal API root and utilities
    path("", internal_api_root, name="internal_api_root"),
    path("debug/", test_middleware_debug, name="test_middleware_debug"),
    path("v1/health/", internal_health_check, name="internal_health"),
    # WebSocket emission endpoint for workers
    path("emit-websocket/", emit_websocket, name="emit_websocket"),
    # ========================================
    # CORE OSS INTERNAL API MODULES
    # ========================================
    # Workflow execution management APIs
    path(
        "v1/workflow-execution/",
        include("workflow_manager.workflow_execution_internal_urls"),
        name="workflow_execution_internal",
    ),
    # Workflow management and pipeline APIs
    path(
        "v1/workflow-manager/",
        include("workflow_manager.internal_urls"),
        name="workflow_manager_internal",
    ),
    # Pipeline APIs
    path(
        "v1/pipeline/",
        include("pipeline_v2.internal_urls"),
        name="pipeline_internal",
    ),
    # Organization context and management APIs
    path(
        "v1/organization/",
        include("account_v2.organization_internal_urls"),
        name="organization_internal",
    ),
    # File execution and batch processing APIs
    path(
        "v1/file-execution/",
        include("workflow_manager.file_execution.internal_urls"),
        name="file_execution_internal",
    ),
    # Tool instance execution APIs
    path(
        "v1/tool-execution/",
        include("tool_instance_v2.internal_urls"),
        name="tool_execution_internal",
    ),
    # File processing history and caching APIs
    path(
        "v1/file-history/",
        include("workflow_manager.workflow_v2.file_history_internal_urls"),
        name="file_history_internal",
    ),
    # Execution finalization and cleanup APIs
    path(
        "v1/execution/",
        include("workflow_manager.execution.internal_urls"),
        name="execution_internal",
    ),
    # Webhook notification APIs
    path(
        "v1/webhook/",
        include("notification_v2.internal_urls"),
        name="webhook_internal",
    ),
    # API deployment data APIs for type-aware worker optimization
    path(
        "v1/api-deployments/",
        include("api_v2.internal_urls"),
        name="api_deployments_internal",
    ),
    # Platform configuration and settings APIs
    path(
        "v1/platform-settings/",
        include("platform_settings_v2.internal_urls"),
        name="platform_settings_internal",
    ),
    # Execution log management and cache operations APIs
    path(
        "v1/execution-logs/",
        include("workflow_manager.workflow_v2.execution_log_internal_urls"),
        name="execution_logs_internal",
    ),
    # Organization configuration management APIs
    path(
        "v1/configuration/",
        include("configuration.internal_urls"),
        name="configuration_internal",
    ),
    # Usage data and token count APIs
    path(
        "v1/usage/",
        include("usage_v2.internal_urls"),
        name="usage_internal",
    ),
]
