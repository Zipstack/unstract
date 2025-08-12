"""Internal API URL Configuration
Base URL configuration for internal service-to-service APIs.

This file uses a registry system to dynamically load internal URLs based on
Django settings. Cloud features are automatically included when cloud settings
are active, without requiring code changes to this file.
"""

from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_http_methods

from .internal_url_registry import (
    get_base_endpoints,
    get_cloud_url_documentation,
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

    # Get base endpoints from shared configuration
    base_endpoints = get_base_endpoints()

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


# Base internal API URL patterns - Core endpoints only
base_urlpatterns = [
    # Internal API root and utilities
    path("", internal_api_root, name="internal_api_root"),
    path("debug/", test_middleware_debug, name="test_middleware_debug"),
    path("v1/health/", internal_health_check, name="internal_health"),
    # All other URLs loaded dynamically from INTERNAL_URL_MODULES settings
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
    # cloud_patterns = get_cloud_url_patterns()  # COMMENTED OUT: Redundant with INTERNAL_URL_MODULES

    # Combine all patterns: base + dynamic (cloud modules loaded via INTERNAL_URL_MODULES)
    return base_urlpatterns + dynamic_patterns


# URL patterns - will include dynamic patterns based on settings
urlpatterns = get_urlpatterns()
