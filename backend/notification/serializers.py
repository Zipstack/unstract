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

        Checks if the `platform` field is valid for the selected `notification_type`.

        Args:
            data (dict): The data to validate, typically containing fields from the
                         `Notification` model.

        Raises:
            serializers.ValidationError: If the `platform` value is not valid for the
                                          selected `notification_type`.

        Returns:
            dict: The validated data

        Note:
            This internal method ensures data consistency and should not be removed
            or modified without understanding its impact.
        """
        notification_type = data.get("notification_type")
        platform = data.get("platform")

        valid_platforms = NotificationType(notification_type).get_valid_platforms()
        if platform and platform not in valid_platforms:
            raise serializers.ValidationError(
                f"Invalid platform '{platform}' for notification type "
                f"'{notification_type}'. "
                f"Valid options are: {', '.join(valid_platforms)}."
            )

        return data
