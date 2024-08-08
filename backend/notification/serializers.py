from rest_framework import serializers

from .enums import AuthorizationType, NotificationType, PlatformType
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    notification_type = serializers.ChoiceField(choices=NotificationType.choices())
    authorization_type = serializers.ChoiceField(choices=AuthorizationType.choices())
    platform = serializers.ChoiceField(choices=PlatformType.choices(), required=False)
    max_retries = serializers.IntegerField(
        max_value=4, min_value=0, default=0, required=False
    )

    class Meta:
        model = Notification
        fields = "__all__"

    def validate(self, data):
        """Validate the data for the NotificationSerializer."""
        # General validation for the relationship between api and pipeline
        self._validate_api_or_pipeline(data)
        return data

    def _validate_api_or_pipeline(self, data):
        """Ensure either 'api' or 'pipeline' is provided, but not both."""
        api = data.get("api", getattr(self.instance, "api", None))
        pipeline = data.get("pipeline", getattr(self.instance, "pipeline", None))
        if api and pipeline:
            raise serializers.ValidationError(
                "Only one of 'api' or 'pipeline' can be provided."
            )

        if not api and not pipeline:
            raise serializers.ValidationError(
                "Either 'api' or 'pipeline' must be provided."
            )

    def validate_platform(self, value):
        """Validate the platform field based on the notification_type."""
        notification_type = self.initial_data.get(
            "notification_type", getattr(self.instance, "notification_type", None)
        )
        if not notification_type:
            raise serializers.ValidationError("Notification type must be provided.")

        valid_platforms = NotificationType(notification_type).get_valid_platforms()
        if value and value not in valid_platforms:
            raise serializers.ValidationError(
                f"Invalid platform '{value}' for notification type "
                f"'{notification_type}'. "
                f"Valid options are: {', '.join(valid_platforms)}."
            )
        return value

    def validate_name(self, value):
        """Check uniqueness of the name with respect to either 'api' or
        'pipeline'."""
        api = self.initial_data.get("api", getattr(self.instance, "api", None))
        pipeline = self.initial_data.get(
            "pipeline", getattr(self.instance, "pipeline", None)
        )

        queryset = Notification.objects.filter(name=value)
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)

        if api and queryset.filter(api=api).exists():
            raise serializers.ValidationError(
                "A notification with this name and API already exists.",
                code="unique_api",
            )
        elif pipeline and queryset.filter(pipeline=pipeline).exists():
            raise serializers.ValidationError(
                "A notification with this name and pipeline already exists.",
                code="unique_pipeline",
            )
        return value
