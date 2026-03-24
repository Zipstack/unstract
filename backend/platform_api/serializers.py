import re

from rest_framework import serializers
from utils.user_context import UserContext

from backend.serializers import AuditSerializer
from platform_api.models import PlatformApiKey

# Alphanumeric, spaces, hyphens, underscores, periods, commas, colons,
# parentheses, forward slashes. No HTML tags or angle brackets.
SAFE_TEXT_PATTERN = re.compile(r"^[a-zA-Z0-9 \-_.,:()/]+$")
SAFE_TEXT_ERROR = (
    "Only alphanumeric characters, spaces, hyphens, underscores, "
    "periods, commas, colons, parentheses, and forward slashes are allowed."
)


def validate_safe_text(value):
    """Reject HTML tags and restrict to safe characters."""
    stripped = value.strip()
    if not stripped:
        raise serializers.ValidationError("This field cannot be empty.")
    if not SAFE_TEXT_PATTERN.match(stripped):
        raise serializers.ValidationError(SAFE_TEXT_ERROR)
    return stripped


class PlatformApiKeyListSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = PlatformApiKey
        fields = [
            "id",
            "name",
            "description",
            "key",
            "is_active",
            "created_at",
            "modified_at",
            "permission",
            "created_by_email",
        ]

    def get_key(self, obj):
        key_str = str(obj.key)
        return f"****-{key_str[-4:]}"

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else "Deleted user"


class PlatformApiKeyCreateSerializer(AuditSerializer):
    description = serializers.CharField(required=True, max_length=512)

    class Meta:
        model = PlatformApiKey
        fields = ["name", "description", "permission"]

    def validate_name(self, value):
        value = validate_safe_text(value)
        organization = UserContext.get_organization()
        if PlatformApiKey.objects.filter(name=value, organization=organization).exists():
            raise serializers.ValidationError(
                "A key with this name already exists in your organization."
            )
        return value

    def validate_description(self, value):
        return validate_safe_text(value)


class PlatformApiKeyUpdateSerializer(AuditSerializer):
    class Meta:
        model = PlatformApiKey
        fields = ["description", "is_active", "permission"]
        extra_kwargs = {
            "description": {"required": False},
            "is_active": {"required": False},
            "permission": {"required": False},
        }

    def validate_description(self, value):
        return validate_safe_text(value)


class PlatformApiKeyDetailSerializer(serializers.ModelSerializer):
    """Used for create/rotate responses where the full key is shown once."""

    class Meta:
        model = PlatformApiKey
        fields = ["id", "name", "key", "is_active"]
