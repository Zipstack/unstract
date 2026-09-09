"""Internal API Views for Webhook Operations
Handles webhook notification related endpoints for internal services.
"""

import logging
from typing import Any

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.organization_utils import organization_from_request

from notification_v2.enums import AuthorizationType, NotificationType, PlatformType

# Import serializers from notification_v2 internal API
from notification_v2.internal_serializers import (
    NotificationListSerializer,
    NotificationSerializer,
    WebhookConfigurationSerializer,
    WebhookTestSerializer,
)
from notification_v2.models import Notification

logger = logging.getLogger(__name__)

# Constants
APPLICATION_JSON = "application/json"


def notifications_for_organization(request):
    """Notifications belonging to the request's organization, failing closed.

    ``Notification`` carries no organization column of its own — it reaches one
    through whichever of ``pipeline`` and ``api`` is set, and both parents get
    ``organization`` from ``DefaultOrganizationMixin``. Routing it through
    ``filter_queryset_by_organization`` would build ``.filter(organization=...)``
    and raise ``FieldError``, so the boundary is drawn across both FKs instead.
    This mirrors what ``internal_api_views`` already does for the same model,
    where the parent is scoped first and its notifications read off it.

    A notification with neither FK set belongs to no organization and is served
    to nobody, which is the fail-closed direction.
    """
    organization = organization_from_request(request)
    if organization is None:
        return Notification.objects.none()
    return Notification.objects.filter(
        Q(pipeline__organization=organization) | Q(api__organization=organization)
    )


class WebhookInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Webhook/Notification operations."""

    serializer_class = NotificationSerializer
    lookup_field = "id"
    # OrganizationFilterBackend is off here; get_queryset() scopes instead, via
    # notifications_for_organization. That fails closed, so a caller without
    # X-Organization-ID gets zero rows.
    skip_org_filter = True

    def get_queryset(self):
        """Get notifications filtered by organization context."""
        return notifications_for_organization(self.request)

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
            # Membership in query_params, not filters.get(): request.query_params
            # is a QueryDict, and DRF's BooleanField reports HTML-form input as
            # False when the key is absent rather than leaving it out of
            # validated_data. So filters["is_active"] is False on every request
            # that omits it, and this filtered an unfiltered list down to the
            # inactive notifications only. Unreachable until now — the org
            # filter above raised FieldError before this line ran.
            if "is_active" in request.query_params:
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

            import requests

            try:
                response = requests.post(
                    url=validated_data["url"],
                    json=validated_data["payload"],
                    headers=headers,
                    timeout=validated_data["timeout"],
                )

                test_result = {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "response_headers": dict(response.headers),
                    "response_body": response.text[:1000],
                    "url": validated_data["url"],
                    "request_headers": headers,
                    "request_payload": validated_data["payload"],
                }

                logger.info(
                    f"Webhook test to {validated_data['url']} completed with status {response.status_code}"
                )

                return Response(test_result)

            except requests.exceptions.RequestException as e:
                test_result = {
                    "success": False,
                    "error": str(e),
                    "url": validated_data["url"],
                    "request_headers": headers,
                    "request_payload": validated_data["payload"],
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
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")

            # Get base queryset
            queryset = notifications_for_organization(request)

            # The organization comes from X-Organization-ID, which is what
            # WebhookAPIClient.get_webhook_metrics sends and what the boundary
            # above reads. An organization_id query parameter was also read
            # here and filtered on, but Notification has no such column, so any
            # caller passing one got a FieldError; accepting it would also let
            # one organization ask for another's counts.
            organization_id = getattr(request, "organization_id", None)

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
