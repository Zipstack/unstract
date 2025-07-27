import logging
import uuid
from typing import Any

from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import APINotFound
from celery import current_app as celery_app
from celery.result import AsyncResult
from django.utils import timezone
from pipeline_v2.exceptions import PipelineNotFound
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from notification_v2.constants import NotificationUrlConstant
from notification_v2.enums import AuthorizationType
from notification_v2.internal_serializers import (
    NotificationListSerializer,
    WebhookBatchRequestSerializer,
    WebhookBatchResponseSerializer,
    WebhookConfigurationSerializer,
    WebhookNotificationRequestSerializer,
    WebhookNotificationResponseSerializer,
    WebhookStatusSerializer,
    WebhookTestSerializer,
)
from notification_v2.provider.webhook.webhook import send_webhook_notification

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        queryset = Notification.objects.all()
        pipeline_uuid = self.kwargs.get(NotificationUrlConstant.PIPELINE_UID)
        api_uuid = self.kwargs.get(NotificationUrlConstant.API_UID)

        if pipeline_uuid:
            try:
                pipeline = PipelineProcessor.fetch_pipeline(
                    pipeline_id=pipeline_uuid, check_active=False
                )
                queryset = queryset.filter(pipeline=pipeline)
            except Pipeline.DoesNotExist:
                raise PipelineNotFound()

        elif api_uuid:
            api = DeploymentHelper.get_api_by_id(api_id=api_uuid)
            if not api:
                raise APINotFound()
            queryset = queryset.filter(api=api)

        return queryset


# =============================================================================
# INTERNAL API VIEWS - Used by Celery workers for service-to-service communication
# =============================================================================


logger = logging.getLogger(__name__)


class WebhookInternalViewSet(viewsets.ReadOnlyModelViewSet):
    """Internal API ViewSet for Webhook/Notification operations."""

    serializer_class = NotificationSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Get notifications filtered by organization context."""
        org_id = getattr(self.request, "organization_id", None)
        if org_id:
            return Notification.objects.filter(organization=org_id)
        return Notification.objects.all()

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
        headers = {"Content-Type": "application/json"}

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
        headers = {"Content-Type": "application/json"}

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
        headers = {"Content-Type": "application/json"}

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
