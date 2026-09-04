"""Internal API Views for Webhook Operations
Handles webhook notification related endpoints for internal services.
"""

import logging
from typing import Any

import requests
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.organization_utils import filter_queryset_by_organization

from notification_v2.enums import AuthorizationType, NotificationType, PlatformType

# Import serializers from notification_v2 internal API
from notification_v2.internal_serializers import (
    NotificationListSerializer,
    NotificationSerializer,
    WebhookConfigurationSerializer,
    WebhookTestSerializer,
)
from notification_v2.models import Notification
from unstract.core.network.ssrf import is_safe_webhook_url

logger = logging.getLogger(__name__)

# Constants
APPLICATION_JSON = "application/json"


class WebhookInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Webhook/Notification operations."""

    serializer_class = NotificationSerializer
    lookup_field = "id"
    # Backward compat: remove once all workers pass X-Organization-ID.
    skip_org_filter = True

    def get_queryset(self):
        """Get notifications filtered by organization context."""
        queryset = Notification.objects.all()
        return filter_queryset_by_organization(queryset, self.request)

    def list(self, request, *args, **kwargs):
        """List notifications with filtering options."""
        try:
            serializer = NotificationListSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            filters = serializer.validated_data
            queryset = self.get_queryset()

            # Apply filters
            if filters.get("pipeline_id"):
                queryset = queryset.filter(pipeline_id=filters["pipeline_id"])
            if filters.get("api_deployment_id"):
                queryset = queryset.filter(api_id=filters["api_deployment_id"])
            if filters.get("notification_type"):
                queryset = queryset.filter(notification_type=filters["notification_type"])
            if filters.get("platform"):
                queryset = queryset.filter(platform=filters["platform"])
            if filters.get("is_active") is not None:
                queryset = queryset.filter(is_active=filters["is_active"])

            notifications = NotificationSerializer(queryset, many=True).data

            return Response({"count": len(notifications), "notifications": notifications})

        except Exception as e:
            logger.error(f"Failed to list notifications: {str(e)}")
            return Response(
                {"error": "Failed to list notifications", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def configuration(self, request, id=None):
        """Get webhook configuration for a notification."""
        try:
            notification = self.get_object()

            config_data = {
                "notification_id": notification.id,
                "url": notification.url,
                "authorization_type": notification.authorization_type,
                "authorization_key": notification.authorization_key,
                "authorization_header": notification.authorization_header,
                "max_retries": notification.max_retries,
                "is_active": notification.is_active,
            }

            serializer = WebhookConfigurationSerializer(config_data)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Failed to get webhook configuration {id}: {str(e)}")
            return Response(
                {"error": "Failed to get webhook configuration", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WebhookTestAPIView(APIView):
    """Internal API endpoint for testing webhook configurations."""

    def post(self, request):
        """Test a webhook configuration without queuing."""
        try:
            serializer = WebhookTestSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            headers = self._build_headers(validated_data)

            # Same guard as the delivery sinks. This endpoint is behind
            # INTERNAL_SERVICE_API_KEY and not tenant-reachable, but it takes
            # an arbitrary URL and so gets the same treatment.
            if not is_safe_webhook_url(validated_data["url"]):
                return Response(
                    {"error": "URL must resolve to a public address."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                response = requests.post(
                    url=validated_data["url"],
                    json=validated_data["payload"],
                    headers=headers,
                    timeout=validated_data["timeout"],
                    allow_redirects=False,
                )

                # Status only. The response body and headers are not the
                # caller's to read, and `headers` (built above) carries the
                # Authorization value built from authorization_key, so it is
                # not echoed back either.
                test_result = {
                    # 2xx only: redirects are not followed, so a 301/302 means
                    # the payload never reached the final destination.
                    "success": 200 <= response.status_code < 300,
                    "status_code": response.status_code,
                    "url": validated_data["url"],
                }

                logger.info(
                    f"Webhook test to {validated_data['url']} completed with status {response.status_code}"
                )

                return Response(test_result)

            except requests.exceptions.RequestException as e:
                # Same rule as the success branch above: `headers` carries the
                # Authorization value built from authorization_key, so it is not
                # echoed back. A target that times out or refuses the connection
                # is the most common way to get here.
                test_result = {
                    "success": False,
                    "error": str(e),
                    "url": validated_data["url"],
                }

                return Response(test_result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Failed to test webhook: {str(e)}")
            return Response(
                {"error": "Failed to test webhook", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _build_headers(self, validated_data: dict[str, Any]) -> dict[str, str]:
        """Build headers for webhook test."""
        headers = {"Content-Type": APPLICATION_JSON}

        auth_type = validated_data.get("authorization_type", AuthorizationType.NONE.value)
        auth_key = validated_data.get("authorization_key")
        auth_header = validated_data.get("authorization_header")

        if validated_data.get("headers"):
            headers.update(validated_data["headers"])

        if auth_type == AuthorizationType.BEARER.value and auth_key:
            headers["Authorization"] = f"Bearer {auth_key}"
        elif auth_type == AuthorizationType.API_KEY.value and auth_key:
            headers["Authorization"] = auth_key
        elif (
            auth_type == AuthorizationType.CUSTOM_HEADER.value
            and auth_header
            and auth_key
        ):
            headers[auth_header] = auth_key

        return headers


class WebhookMetricsAPIView(APIView):
    """Internal API endpoint for webhook delivery metrics."""

    def get(self, request):
        """Get webhook delivery metrics."""
        try:
            # Get query parameters
            organization_id = request.query_params.get("organization_id")
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")

            # Get base queryset
            queryset = Notification.objects.all()
            queryset = filter_queryset_by_organization(queryset, request)

            # Apply filters
            if organization_id:
                queryset = queryset.filter(organization_id=organization_id)

            if start_date:
                from datetime import datetime

                try:
                    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                    queryset = queryset.filter(created_at__gte=start_dt)
                except ValueError:
                    return Response(
                        {"error": "Invalid start_date format. Use ISO format."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if end_date:
                from datetime import datetime

                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    queryset = queryset.filter(created_at__lte=end_dt)
                except ValueError:
                    return Response(
                        {"error": "Invalid end_date format. Use ISO format."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Calculate metrics
            total_webhooks = queryset.count()
            active_webhooks = queryset.filter(is_active=True).count()
            inactive_webhooks = queryset.filter(is_active=False).count()

            # Group by notification type
            type_breakdown = {}
            for notification_type in NotificationType:
                count = queryset.filter(notification_type=notification_type.value).count()
                if count > 0:
                    type_breakdown[notification_type.value] = count

            # Group by platform
            platform_breakdown = {}
            for platform_type in PlatformType:
                count = queryset.filter(platform=platform_type.value).count()
                if count > 0:
                    platform_breakdown[platform_type.value] = count

            # Group by authorization type
            auth_breakdown = {}
            for auth_type in AuthorizationType:
                count = queryset.filter(authorization_type=auth_type.value).count()
                if count > 0:
                    auth_breakdown[auth_type.value] = count

            metrics = {
                "total_webhooks": total_webhooks,
                "active_webhooks": active_webhooks,
                "inactive_webhooks": inactive_webhooks,
                "type_breakdown": type_breakdown,
                "platform_breakdown": platform_breakdown,
                "authorization_breakdown": auth_breakdown,
                "filters_applied": {
                    "organization_id": organization_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            }

            return Response(metrics)

        except Exception as e:
            logger.error(f"Failed to get webhook metrics: {str(e)}")
            return Response(
                {"error": "Failed to get webhook metrics", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
