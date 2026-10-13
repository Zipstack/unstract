"""Key-management serializers, mirroring ``platform_api.serializers``.

Four serializers rather than two, and the split is the point: **the list
endpoint must not hand back plaintext keys.** It backs a table that shows every
key in the organization at once, so returning the real value there puts the
whole set on screen (and into any screenshot, support ticket or browser cache)
to read one of them. ``platform_api`` already settled this -- list masks, and
the full value comes from create, rotate and an explicit per-key retrieve, each
of which is a deliberate request for one key.

The earlier single ``AgentKVKeySerializer`` returned the real key everywhere.
That was survivable only while nothing called the endpoint; it stopped being so
the moment the keys page shipped.
"""

from rest_framework import serializers
from utils.input_sanitizer import validate_safe_text
from utils.user_context import UserContext

from agent_kv.models import AgentKVKey


def _masked(key) -> str:
    """Last four characters only -- enough to tell two keys apart, useless to a
    reader. Same shape as ``PlatformApiKeyListSerializer.get_key``.
    """
    return f"****-{str(key)[-4:]}"


class AgentKVKeyListSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = AgentKVKey
        fields = [
            "id",
            "name",
            "description",
            "key",
            "is_active",
            "created_at",
            "modified_at",
            "created_by_email",
        ]

    def get_key(self, obj):
        return _masked(obj.key)

    def get_created_by_email(self, obj):
        # The FK is `on_delete=SET_NULL`, so a key outlives the admin who made
        # it. "Deleted user" rather than blank: an empty cell reads as a bug.
        return obj.created_by.email if obj.created_by else "Deleted user"


class AgentKVKeyDetailSerializer(serializers.ModelSerializer):
    """Create / rotate / retrieve -- the responses that show the full key.

    Each is a request for ONE key the caller already has a reason to hold:
    they just minted it, just replaced it, or clicked copy on a row.
    """

    class Meta:
        model = AgentKVKey
        fields = ["id", "name", "key", "is_active"]


class AgentKVKeyCreateSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=True, max_length=512)

    class Meta:
        model = AgentKVKey
        fields = ["name", "description"]

    def validate_name(self, value):
        value = validate_safe_text(value)
        # The model has a unique constraint on (name, organization), which
        # would surface as an IntegrityError-shaped 500 or an opaque
        # "unique_agent_kv_key_name_per_org" string. Checked here so the admin
        # is told what to change.
        organization = UserContext.get_organization()
        if AgentKVKey.objects.filter(name=value, organization=organization).exists():
            raise serializers.ValidationError(
                "A key with this name already exists in your organization."
            )
        return value

    def validate_description(self, value):
        return validate_safe_text(value)


class AgentKVKeyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentKVKey
        fields = ["description", "is_active"]
        extra_kwargs = {
            "description": {"required": False},
            "is_active": {"required": False},
        }

    def validate_description(self, value):
        return validate_safe_text(value)
