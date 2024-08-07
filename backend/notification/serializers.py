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
        """Validate the data for the NotificationSerializer.

        Ensures that either 'api' or 'pipeline' is provided, but not both,
        and that one of them is mandatory. Also verifies that the 'platform'
        value is valid for the selected 'notification_type'. Checks for
        uniqueness of the combination of 'name' with either 'api' or 'pipeline'.

        Args:
            data (dict): The data to validate, typically containing fields from the
                         `Notification` model.

        Raises:
            serializers.ValidationError: If the `platform` value is invalid for the
                selected `notification_type`, or if the uniqueness constraint for
                the combination of `name` with `api` or `pipeline` is violated

        Returns:
            dict: The validated data.

        Note:
            This method ensures data consistency by checking the validity of
            platform values and uniqueness constraints before the data is saved.
        """
        notification_type = data.get("notification_type")
        platform = data.get("platform")
        name = data.get("name", "Notification")
        pipeline = data.get("pipeline")
        api = data.get("api")

        # Ensure only one of 'api' or 'pipeline' is provided
        if api and pipeline:
            raise serializers.ValidationError(
                "Only one of 'api' or 'pipeline' can be provided."
            )

        if not api and not pipeline:
            raise serializers.ValidationError(
                "Either 'api' or 'pipeline' must be provided."
            )

        valid_platforms = NotificationType(notification_type).get_valid_platforms()
        if platform and platform not in valid_platforms:
            raise serializers.ValidationError(
                f"Invalid platform '{platform}' for notification type "
                f"'{notification_type}'. "
                f"Valid options are: {', '.join(valid_platforms)}."
            )
        # Check uniqueness for name with respect to either api or pipeline
        if api:
            if Notification.objects.filter(name=name, api=api).exists():
                raise serializers.ValidationError(
                    "A notification with this name and API already exists.",
                    code="unique",
                )
        elif pipeline:
            if Notification.objects.filter(name=name, pipeline=pipeline).exists():
                raise serializers.ValidationError(
                    "A notification with this name and pipeline already exists.",
                    code="unique",
                )
        return data
