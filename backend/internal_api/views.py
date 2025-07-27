"""Internal API Views
Base views for internal service APIs.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class InternalAPIRootView(APIView):
    """Root endpoint for Internal API.
    Provides API version information and available endpoints.
    """

    def get(self, request):
        """Return API root information."""
        return Response(
            {
                "message": "Unstract Internal API",
                "version": "1.0.0",
                "description": "Internal service-to-service API for Celery workers",
                "documentation": "https://docs.unstract.com/internal-api",
                "endpoints": {
                    "v1": {
                        # Health & Utilities
                        "health": "/internal/api/v1/health/",
                        # Workflow Execution APIs
                        "workflow_execution_list": "/internal/api/v1/workflow-execution/",
                        "workflow_execution_detail": "/internal/api/v1/workflow-execution/{id}/",
                        "workflow_execution_status_update": "/internal/api/v1/workflow-execution/{id}/update_status/",
                        "create_file_batch": "/internal/api/v1/workflow-execution/create-file-batch/",
                        # File Execution APIs
                        "file_execution_list": "/internal/api/v1/file-execution/",
                        "file_execution_detail": "/internal/api/v1/file-execution/{id}/",
                        "file_execution_status_update": "/internal/api/v1/file-execution/{id}/update_status/",
                        # Webhook APIs
                        "webhook_list": "/internal/api/v1/webhook/",
                        "webhook_detail": "/internal/api/v1/webhook/{id}/",
                        "webhook_configuration": "/internal/api/v1/webhook/{id}/configuration/",
                        "webhook_send": "/internal/api/v1/webhook/send/",
                        "webhook_batch": "/internal/api/v1/webhook/batch/",
                        "webhook_test": "/internal/api/v1/webhook/test/",
                        "webhook_status": "/internal/api/v1/webhook/status/{task_id}/",
                        # Organization Context
                        "organization_context": "/internal/api/v1/organization/{org_id}/context/",
                    }
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


class InternalAPIHealthView(APIView):
    """Health check endpoint for Internal API.
    Used by workers to verify API connectivity.
    """

    def get(self, request):
        """Return health status."""
        try:
            # Check if request is properly authenticated
            if not hasattr(request, "internal_service") or not request.internal_service:
                return Response(
                    {
                        "status": "error",
                        "message": "Not authenticated as internal service",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Basic health checks
            health_data = {
                "status": "healthy",
                "service": "internal_api",
                "version": "1.0.0",
                "timestamp": request.META.get("HTTP_DATE"),
                "authenticated": True,
                "organization_id": getattr(request, "organization_id", None),
            }

            return Response(health_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Internal API health check failed: {str(e)}")
            return Response(
                {"status": "error", "message": "Health check failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
