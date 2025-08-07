"""Internal API URL Configuration
Base URL configuration for internal service-to-service APIs.

This file uses a registry system to dynamically load internal URLs based on
Django settings. Cloud features are automatically included when cloud settings
are active, without requiring code changes to this file.
"""

from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_http_methods

from .internal_url_registry import (
    get_cloud_url_documentation,
    get_cloud_url_patterns,
    get_internal_url_documentation,
    get_internal_url_patterns,
    initialize_internal_urls_from_settings,
)


@require_http_methods(["GET"])
def internal_api_root(request):
    """Internal API root endpoint with comprehensive documentation."""
    # Initialize dynamic URLs from settings
    initialize_internal_urls_from_settings()

    # Get dynamic endpoint documentation
    dynamic_endpoints = get_internal_url_documentation()

    # Get cloud endpoint documentation if available
    cloud_endpoints = get_cloud_url_documentation()

    base_endpoints = {
        # Health & Utilities
        "health": "/internal/v1/health/",
        # Workflow Execution APIs (workflow_manager app)
        "workflow_execution": "/internal/v1/workflow/",
        "workflow_execution_detail": "/internal/v1/workflow/{id}/",
        "workflow_execution_status": "/internal/v1/workflow/{id}/status/",
        "file_batch_create": "/internal/v1/workflow/file-batch/",
        "file_execution": "/internal/v1/file-execution/",
        "file_execution_status": "/internal/v1/file-execution/{id}/status/",
        # Tool Execution APIs (tool_instance_v2 app)
        "tool_execution": "/internal/v1/tool-execution/",
        "tool_execution_execute": "/internal/v1/tool-execution/{id}/execute/",
        "tool_execution_status": "/internal/v1/tool-execution/status/{execution_id}/",
        "tool_instances_by_workflow": "/internal/v1/tool-execution/workflow/{workflow_id}/instances/",
        # File History APIs (workflow_manager.workflow_v2 app)
        "file_history_by_cache_key": "/internal/v1/file-history/cache-key/{cache_key}/",
        "file_history_create": "/internal/v1/file-history/create/",
        "file_history_status": "/internal/v1/file-history/status/{file_history_id}/",
        # Execution Finalization APIs (workflow_manager.execution app)
        "execution_finalize": "/internal/v1/execution/finalize/{execution_id}/",
        "execution_cleanup": "/internal/v1/execution/cleanup/",
        "execution_finalization_status": "/internal/v1/execution/finalization-status/{execution_id}/",
        # Webhook APIs (notification_v2 app)
        "webhook_config": "/internal/v1/webhook/",
        "webhook_send": "/internal/v1/webhook/send/",
        "webhook_batch": "/internal/v1/webhook/batch/",
        "webhook_test": "/internal/v1/webhook/test/",
        "webhook_status": "/internal/v1/webhook/status/{task_id}/",
        # Organization Context (account_v2 app)
        "organization": "/internal/v1/organization/{org_id}/",
        # Platform Settings APIs
        "platform_key": "/internal/v1/platform-settings/platform-key/",
    }

    # Merge all endpoints (base + dynamic + cloud)
    all_endpoints = {**base_endpoints, **dynamic_endpoints, **cloud_endpoints}

    return JsonResponse(
        {
            "message": "Unstract Internal API",
            "version": "1.0.0",
            "description": "Internal service-to-service API for Celery workers",
            "documentation": "https://docs.unstract.com/internal-api",
            "features": {
                "registered_modules": list(dynamic_endpoints.keys())
                if dynamic_endpoints
                else [],
                "cloud_modules": list(cloud_endpoints.keys()) if cloud_endpoints else [],
            },
            "endpoints": {"v1": all_endpoints},
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


# Base internal API URL patterns
base_urlpatterns = [
    # Internal API root
    path("", internal_api_root, name="internal_api_root"),
    # Debug endpoint
    path("debug/", test_middleware_debug, name="test_middleware_debug"),
    # Health check
    path("v1/health/", internal_health_check, name="internal_health"),
    # Workflow execution APIs (from workflow_manager app)
    path("api/v1/", include("workflow_manager.workflow_execution_internal_urls")),
    # Workflow manager APIs (includes workflow endpoint detection)
    path("workflow-manager/", include("workflow_manager.internal_urls")),
    # Organization APIs (from account_v2 app)
    path("api/v1/organization/", include("account_v2.organization_internal_urls")),
    # Legacy internal APIs (keep existing ones that haven't been moved yet)
    path("v1/file-execution/", include("workflow_manager.file_execution.internal_urls")),
    path("v1/tool-execution/", include("tool_instance_v2.internal_urls")),
    path(
        "v1/file-history/",
        include("workflow_manager.workflow_v2.file_history_internal_urls"),
    ),
    path("v1/execution/", include("workflow_manager.execution.internal_urls")),
    path("v1/webhook/", include("notification_v2.internal_urls")),
    # Platform settings APIs
    path("v1/platform-settings/", include("platform_settings_v2.internal_urls")),
    # Workflow manager APIs
    path("v1/workflow-manager/", include("workflow_manager.internal_urls")),
]


def get_urlpatterns():
    """Get URL patterns including dynamically registered and cloud modules.

    This function ensures that URLs are loaded fresh each time, allowing
    cloud deployments to automatically include additional URLs without
    code changes to this file.
    """
    # Initialize dynamic URLs from settings
    initialize_internal_urls_from_settings()

    # Get dynamic URL patterns from registry
    dynamic_patterns = get_internal_url_patterns()

    # Get cloud URL patterns if available
    cloud_patterns = get_cloud_url_patterns()

    # Combine all patterns: base + dynamic + cloud
    return base_urlpatterns + dynamic_patterns + cloud_patterns


# URL patterns - will include dynamic patterns based on settings
urlpatterns = get_urlpatterns()
