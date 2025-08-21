"""Internal API Serializers for Webhook Operations
Handles serialization for webhook notification related endpoints.
"""

from notification_v2.enums import AuthorizationType, NotificationType, PlatformType
from notification_v2.models import Notification
from rest_framework import serializers


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model for internal API."""

    pipeline_id = serializers.CharField(source="pipeline.id", read_only=True)
    api_deployment_id = serializers.CharField(source="api.id", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "name",
            "url",
            "authorization_key",
            "authorization_header",
            "authorization_type",
            "max_retries",
            "platform",
            "notification_type",
            "is_active",
            "pipeline_id",
            "api_deployment_id",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "created_at", "modified_at"]


class WebhookNotificationRequestSerializer(serializers.Serializer):
    """Serializer for webhook notification requests."""

    notification_id = serializers.UUIDField(required=False, allow_null=True)
    url = serializers.URLField()
    payload = serializers.DictField()
    headers = serializers.DictField(required=False, allow_null=True)
    timeout = serializers.IntegerField(default=10, min_value=1, max_value=300)
    max_retries = serializers.IntegerField(default=0, min_value=0, max_value=10)
    retry_delay = serializers.IntegerField(default=10, min_value=1, max_value=3600)

    # Authentication options
    authorization_type = serializers.ChoiceField(
        choices=AuthorizationType.choices(), default=AuthorizationType.NONE.value
    )
    authorization_key = serializers.CharField(required=False, allow_blank=True)
    authorization_header = serializers.CharField(required=False, allow_blank=True)


class WebhookNotificationResponseSerializer(serializers.Serializer):
    """Serializer for webhook notification response."""

    task_id = serializers.CharField()
    notification_id = serializers.UUIDField(required=False, allow_null=True)
    url = serializers.URLField()
    status = serializers.CharField()
    queued_at = serializers.DateTimeField()


class WebhookStatusSerializer(serializers.Serializer):
    """Serializer for webhook delivery status."""

    task_id = serializers.CharField()
    status = serializers.CharField()
    url = serializers.URLField()
    attempts = serializers.IntegerField(default=0)
    last_attempt_at = serializers.DateTimeField(required=False, allow_null=True)
    success = serializers.BooleanField()
    error_message = serializers.CharField(required=False, allow_blank=True)
    response_status_code = serializers.IntegerField(required=False, allow_null=True)
    response_data = serializers.DictField(required=False, allow_null=True)


class WebhookRetryConfigSerializer(serializers.Serializer):
    """Serializer for webhook retry configuration."""

    max_retries = serializers.IntegerField(min_value=0, max_value=10)
    retry_delay = serializers.IntegerField(min_value=1, max_value=3600)
    exponential_backoff = serializers.BooleanField(default=False)
    max_retry_delay = serializers.IntegerField(default=300, min_value=1, max_value=3600)


class WebhookBatchRequestSerializer(serializers.Serializer):
    """Serializer for batch webhook notification requests."""

    webhooks = WebhookNotificationRequestSerializer(many=True)
    batch_name = serializers.CharField(max_length=255, required=False)
    delay_between_requests = serializers.IntegerField(
        default=0, min_value=0, max_value=60
    )


class WebhookBatchResponseSerializer(serializers.Serializer):
    """Serializer for batch webhook notification response."""

    batch_id = serializers.CharField()
    batch_name = serializers.CharField(required=False)
    total_webhooks = serializers.IntegerField()
    queued_webhooks = WebhookNotificationResponseSerializer(many=True)
    failed_webhooks = serializers.ListField(required=False)


class WebhookConfigurationSerializer(serializers.Serializer):
    """Serializer for webhook configuration."""

    notification_id = serializers.UUIDField()
    url = serializers.URLField()
    authorization_type = serializers.ChoiceField(choices=AuthorizationType.choices())
    authorization_key = serializers.CharField(required=False, allow_blank=True)
    authorization_header = serializers.CharField(required=False, allow_blank=True)
    max_retries = serializers.IntegerField(default=0, min_value=0, max_value=10)
    is_active = serializers.BooleanField(default=True)

    def validate(self, data):
        """Custom validation for webhook configuration."""
        auth_type = data.get("authorization_type")
        auth_key = data.get("authorization_key")
        auth_header = data.get("authorization_header")

        # Validate authorization requirements
        if auth_type == AuthorizationType.CUSTOM_HEADER.value:
            if not auth_header or not auth_key:
                raise serializers.ValidationError(
                    "Custom header and key are required for custom authorization type"
                )
        elif auth_type in [
            AuthorizationType.BEARER.value,
            AuthorizationType.API_KEY.value,
        ]:
            if not auth_key:
                raise serializers.ValidationError(
                    f"Authorization key is required for {auth_type} authorization type"
                )

        return data


class NotificationListSerializer(serializers.Serializer):
    """Serializer for notification list requests."""

    pipeline_id = serializers.UUIDField(required=False, allow_null=True)
    api_deployment_id = serializers.UUIDField(required=False, allow_null=True)
    notification_type = serializers.ChoiceField(
        choices=NotificationType.choices(), required=False
    )
    platform = serializers.ChoiceField(choices=PlatformType.choices(), required=False)
    is_active = serializers.BooleanField(required=False)
    organization_id = serializers.CharField(required=False)


class WebhookTestSerializer(serializers.Serializer):
    """Serializer for webhook test requests."""

    url = serializers.URLField()
    payload = serializers.DictField(default=dict)
    headers = serializers.DictField(required=False, allow_null=True)
    timeout = serializers.IntegerField(default=10, min_value=1, max_value=60)
    authorization_type = serializers.ChoiceField(
        choices=AuthorizationType.choices(), default=AuthorizationType.NONE.value
    )
    authorization_key = serializers.CharField(required=False, allow_blank=True)
    authorization_header = serializers.CharField(required=False, allow_blank=True)
