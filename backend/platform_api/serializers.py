from rest_framework import serializers
from utils.input_sanitizer import validate_safe_text
from utils.user_context import UserContext

from backend.serializers import AuditSerializer
from platform_api.models import PlatformApiKey


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
