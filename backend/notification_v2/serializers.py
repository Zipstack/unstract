from rest_framework import serializers
from utils.input_sanitizer import validate_name_field

from unstract.core.network.ssrf import is_safe_webhook_url

from .enums import AuthorizationType, NotificationType, PlatformType
from .models import Notification


class NotificationSettingsSerializer(serializers.Serializer):
    """Org-scoped notification batching settings."""

    # Bounds (1 min – 2 h) mirror ConfigKey.NOTIFICATION_CLUB_INTERVAL so DRF
    # returns a structured 400 before ConfigKey.cast_value re-raises.
    club_interval_seconds = serializers.IntegerField(min_value=60, max_value=7200)


class NotificationSerializer(serializers.ModelSerializer):
    notification_type = serializers.ChoiceField(choices=NotificationType.choices())
    authorization_type = serializers.ChoiceField(choices=AuthorizationType.choices())
    platform = serializers.ChoiceField(choices=PlatformType.choices(), required=False)
    max_retries = serializers.IntegerField(
        max_value=4, min_value=0, default=0, required=False
    )
    notify_on_failures = serializers.BooleanField(default=False, required=False)

    class Meta:
        model = Notification
        fields = "__all__"
        # Custom validate_name already enforces uniqueness with friendly per-field
        # errors; drop the redundant DRF auto-validator (fragile on partial PATCH).
        validators = []

    def validate(self, data):
        """Validate the data for the NotificationSerializer."""
        # General validation for the relationship between api and pipeline
        self._validate_api_or_pipeline(data)
        self._validate_authorization(data)
        self._validate_url(data)
        return data

    def _validate_url(self, data):
        """Reject a URL that can never be dialled, at save time.

        is_safe_webhook_url refuses a disallowed scheme, credentials in the URL,
        a host the two parsers disagree on, and an internal address literal —
        not only the last of those. The sink is still the real control.

        resolve=False keeps DNS off the request thread — getaddrinfo takes no
        timeout. A hostname pointing inward is accepted here and refused at the
        sink, which resolves. Only a URL the caller actually sent is checked;
        re-checking the stored one would 400 an unrelated PATCH on a legacy row.
        """
        notification_type = data.get(
            "notification_type", getattr(self.instance, "notification_type", None)
        )
        url = data.get("url", getattr(self.instance, "url", None))

        if not url:
            if notification_type == NotificationType.WEBHOOK.value:
                raise serializers.ValidationError(
                    {"url": "A webhook notification requires a URL."}
                )
            return

        if "url" in data and not is_safe_webhook_url(url, resolve=False):
            raise serializers.ValidationError(
                {"url": "URL must not be an internal or ambiguous address."}
            )

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

    def _validate_authorization(self, data):
        """Ensure required authorization fields are provided based on the
        authorization type.

        Getting existing data in the case of PATCH request
        """
        authorization_type = data.get(
            "authorization_type", getattr(self.instance, "authorization_type", None)
        )
        authorization_key = data.get(
            "authorization_key", getattr(self.instance, "authorization_key", None)
        )
        authorization_header = data.get(
            "authorization_header", getattr(self.instance, "authorization_header", None)
        )

        try:
            authorization_type_enum = AuthorizationType(authorization_type)
        except ValueError:
            raise serializers.ValidationError(
                f"Invalid authorization type '{authorization_type}'."
            )

        if authorization_type_enum in [
            AuthorizationType.BEARER,
            AuthorizationType.API_KEY,
            AuthorizationType.CUSTOM_HEADER,
        ]:
            if not authorization_key:
                raise serializers.ValidationError(
                    {
                        "authorization_key": (
                            "Authorization key is required for authorization "
                            f"type '{authorization_type_enum.value}'."
                        )
                    }
                )

            if (
                authorization_type_enum == AuthorizationType.CUSTOM_HEADER
                and not authorization_header
            ):
                raise serializers.ValidationError(
                    {
                        "authorization_header": (
                            "Authorization header is required when using "
                            "CUSTOM_HEADER authorization type."
                        )
                    }
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
        'pipeline'.
        """
        value = validate_name_field(value, field_name="Notification name")

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
