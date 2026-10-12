"""Internal API Serializers for Notification/Webhook Operations
Used by Celery workers for service-to-service communication.
"""

from rest_framework import serializers

from notification_v2.enums import AuthorizationType, NotificationType, PlatformType
from notification_v2.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "url",
            "authorization_type",
            "authorization_key",
            "authorization_header",
            "notification_type",
            "platform",
            "max_retries",
            "is_active",
            "created_at",
            "modified_at",
            "pipeline",
            "api",
        ]


class WebhookConfigurationSerializer(serializers.Serializer):
    """Serializer for webhook configuration."""

    notification_id = serializers.UUIDField()
    url = serializers.URLField()
    authorization_type = serializers.ChoiceField(choices=AuthorizationType.choices())
    authorization_key = serializers.CharField(required=False, allow_blank=True)
    authorization_header = serializers.CharField(required=False, allow_blank=True)
    max_retries = serializers.IntegerField()
    is_active = serializers.BooleanField()


class NotificationListSerializer(serializers.Serializer):
    """Serializer for notification list filters."""

    pipeline_id = serializers.UUIDField(required=False)
    api_deployment_id = serializers.UUIDField(required=False)
    notification_type = serializers.ChoiceField(
        choices=NotificationType.choices(), required=False
    )
    platform = serializers.ChoiceField(choices=PlatformType.choices(), required=False)
    is_active = serializers.BooleanField(required=False)


class WebhookTestSerializer(serializers.Serializer):
    """Serializer for webhook testing."""

    url = serializers.URLField(required=True)
    payload = serializers.JSONField(required=True)
    authorization_type = serializers.ChoiceField(
        choices=AuthorizationType.choices(), default=AuthorizationType.NONE.value
    )
    authorization_key = serializers.CharField(required=False, allow_blank=True)
    authorization_header = serializers.CharField(required=False, allow_blank=True)
    headers = serializers.DictField(required=False, default=dict)
    timeout = serializers.IntegerField(default=30, min_value=1, max_value=300)
