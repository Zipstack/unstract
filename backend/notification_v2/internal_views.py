"""Internal API Views for Webhook Operations
Handles webhook notification related endpoints for internal services.
"""

import logging
import uuid
from typing import Any

from celery import current_app as celery_app
from celery.result import AsyncResult
from django.utils import timezone
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
    WebhookBatchRequestSerializer,
    WebhookBatchResponseSerializer,
    WebhookConfigurationSerializer,
    WebhookNotificationRequestSerializer,
    WebhookNotificationResponseSerializer,
    WebhookStatusSerializer,
    WebhookTestSerializer,
)
from notification_v2.models import Notification
from notification_v2.provider.webhook.webhook import send_webhook_notification

logger = logging.getLogger(__name__)

# Constants
APPLICATION_JSON = "application/json"


class WebhookInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Webhook/Notification operations."""

    serializer_class = NotificationSerializer
    lookup_field = "id"

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


class WebhookSendAPIView(APIView):
    """Internal API endpoint for sending webhook notifications."""

    def post(self, request):
        """Send a webhook notification."""
        try:
            serializer = WebhookNotificationRequestSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Build headers based on authorization type
            headers = self._build_headers(validated_data)

            # Send webhook notification task
            task = send_webhook_notification.delay(
                url=validated_data["url"],
                payload=validated_data["payload"],
                headers=headers,
                timeout=validated_data["timeout"],
                max_retries=validated_data["max_retries"],
                retry_delay=validated_data["retry_delay"],
            )

            # Prepare response
            response_data = {
                "task_id": task.id,
                "notification_id": validated_data.get("notification_id"),
                "url": validated_data["url"],
                "status": "queued",
                "queued_at": timezone.now(),
            }

            response_serializer = WebhookNotificationResponseSerializer(response_data)

            logger.info(
                f"Queued webhook notification task {task.id} for URL {validated_data['url']}"
            )

            return Response(response_serializer.data, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {str(e)}")
            return Response(
                {"error": "Failed to send webhook notification", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _build_headers(self, validated_data: dict[str, Any]) -> dict[str, str]:
        """Build headers based on authorization configuration."""
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


class WebhookStatusAPIView(APIView):
    """Internal API endpoint for checking webhook delivery status."""

    def get(self, request, task_id):
        """Get webhook delivery status by task ID."""
        try:
            task_result = AsyncResult(task_id, app=celery_app)

            status_data = {
                "task_id": task_id,
                "status": task_result.status,
                "url": "unknown",
                "attempts": 0,
                "success": task_result.successful(),
                "error_message": None,
            }

            if task_result.failed():
                status_data["error_message"] = str(task_result.result)
            elif task_result.successful():
                status_data["attempts"] = getattr(task_result.result, "attempts", 1)

            serializer = WebhookStatusSerializer(status_data)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Failed to get webhook status for task {task_id}: {str(e)}")
            return Response(
                {"error": "Failed to get webhook status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WebhookBatchAPIView(APIView):
    """Internal API endpoint for sending batch webhook notifications."""

    def post(self, request):
        """Send multiple webhook notifications in batch."""
        try:
            serializer = WebhookBatchRequestSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            webhooks = validated_data["webhooks"]
            delay_between = validated_data.get("delay_between_requests", 0)

            batch_id = str(uuid.uuid4())
            queued_webhooks = []
            failed_webhooks = []

            for i, webhook_data in enumerate(webhooks):
                try:
                    headers = self._build_headers(webhook_data)
                    countdown = i * delay_between if delay_between > 0 else 0

                    task = send_webhook_notification.apply_async(
                        args=[
                            webhook_data["url"],
                            webhook_data["payload"],
                            headers,
                            webhook_data["timeout"],
                        ],
                        kwargs={
                            "max_retries": webhook_data["max_retries"],
                            "retry_delay": webhook_data["retry_delay"],
                        },
                        countdown=countdown,
                    )

                    queued_webhooks.append(
                        {
                            "task_id": task.id,
                            "notification_id": webhook_data.get("notification_id"),
                            "url": webhook_data["url"],
                            "status": "queued",
                            "queued_at": timezone.now(),
                        }
                    )

                except Exception as e:
                    failed_webhooks.append({"url": webhook_data["url"], "error": str(e)})

            response_data = {
                "batch_id": batch_id,
                "batch_name": validated_data.get("batch_name", f"Batch-{batch_id[:8]}"),
                "total_webhooks": len(webhooks),
                "queued_webhooks": queued_webhooks,
                "failed_webhooks": failed_webhooks,
            }

            response_serializer = WebhookBatchResponseSerializer(response_data)

            logger.info(
                f"Queued batch {batch_id} with {len(queued_webhooks)} webhooks, {len(failed_webhooks)} failed"
            )

            return Response(response_serializer.data, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"Failed to send webhook batch: {str(e)}")
            return Response(
                {"error": "Failed to send webhook batch", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _build_headers(self, webhook_data: dict[str, Any]) -> dict[str, str]:
        """Build headers for webhook request."""
        headers = {"Content-Type": APPLICATION_JSON}

        auth_type = webhook_data.get("authorization_type", AuthorizationType.NONE.value)
        auth_key = webhook_data.get("authorization_key")
        auth_header = webhook_data.get("authorization_header")

        if webhook_data.get("headers"):
            headers.update(webhook_data["headers"])

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


class WebhookBatchStatusAPIView(APIView):
    """Internal API endpoint for checking batch webhook delivery status."""

    def get(self, request):
        """Get batch webhook delivery status."""
        try:
            batch_id = request.query_params.get("batch_id")
            task_ids = request.query_params.get("task_ids", "").split(",")

            if not batch_id and not task_ids:
                return Response(
                    {"error": "Either batch_id or task_ids parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            batch_results = []

            if task_ids and task_ids[0]:  # task_ids is not empty
                for task_id in task_ids:
                    if task_id.strip():
                        try:
                            task_result = AsyncResult(task_id.strip(), app=celery_app)

                            batch_results.append(
                                {
                                    "task_id": task_id.strip(),
                                    "status": task_result.status,
                                    "success": task_result.successful(),
                                    "error_message": str(task_result.result)
                                    if task_result.failed()
                                    else None,
                                }
                            )
                        except Exception as e:
                            batch_results.append(
                                {
                                    "task_id": task_id.strip(),
                                    "status": "ERROR",
                                    "success": False,
                                    "error_message": f"Failed to get task status: {str(e)}",
                                }
                            )

            response_data = {
                "batch_id": batch_id,
                "total_tasks": len(batch_results),
                "results": batch_results,
                "summary": {
                    "completed": sum(
                        1 for r in batch_results if r["status"] == "SUCCESS"
                    ),
                    "failed": sum(1 for r in batch_results if r["status"] == "FAILURE"),
                    "pending": sum(1 for r in batch_results if r["status"] == "PENDING"),
                    "running": sum(1 for r in batch_results if r["status"] == "STARTED"),
                },
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Failed to get batch webhook status: {str(e)}")
            return Response(
                {"error": "Failed to get batch webhook status", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
