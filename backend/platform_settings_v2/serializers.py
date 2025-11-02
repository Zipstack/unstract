from account_v2.models import PlatformKey
from adapter_processor_v2.models import AdapterInstance
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from backend.serializers import AuditSerializer
from platform_settings_v2.models import PlatformSettings
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.adapters.enums import AdapterTypes
else:
    from unstract.sdk.adapters.enums import AdapterTypes


class PlatformKeySerializer(AuditSerializer):
    class Meta:
        model = PlatformKey
        fields = "__all__"


class PlatformKeyGenerateSerializer(serializers.Serializer):
    # Adjust these fields based on your actual serializer
    is_active = serializers.BooleanField()

    key_name = serializers.CharField()


class PlatformKeyIDSerializer(serializers.Serializer):
    id = serializers.CharField()
    key_name = serializers.CharField()
    key = serializers.CharField()
    is_active = serializers.BooleanField()


class PlatformSettingsSerializer(AuditSerializer):
    """Serializer for PlatformSettings model."""

    system_llm_adapter = serializers.PrimaryKeyRelatedField(
        queryset=AdapterInstance.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PlatformSettings
        fields = [
            "id",
            "organization",
            "system_llm_adapter",
            "created_at",
            "modified_at",
        ]
        read_only_fields = ["id", "organization", "created_at", "modified_at"]

    def validate_system_llm_adapter(self, value):
        """Validate that the adapter type is LLM and is accessible to the user."""
        if value is None:
            return value

        # Check if user has access to this adapter
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            try:
                adapter = AdapterInstance.objects.for_user(request.user).get(id=value.id)
                # Validate that the adapter type is LLM
                if adapter.adapter_type != AdapterTypes.LLM.value:
                    raise ValidationError("Only LLM adapters are allowed for system LLM")

                # Validate that adapter is usable and active
                if not adapter.is_usable:
                    raise ValidationError("Selected LLM adapter is not usable")

                if not adapter.is_active:
                    raise ValidationError("Selected LLM adapter is not active")

            except AdapterInstance.DoesNotExist:
                raise ValidationError("Selected LLM adapter not found or not accessible")

        return value
