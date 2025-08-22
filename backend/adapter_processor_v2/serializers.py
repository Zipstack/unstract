import json
from typing import Any

from account_v2.serializer import UserSerializer
from cryptography.fernet import Fernet
from django.conf import settings
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.constants import AdapterKeys
from backend.constants import FieldLengthConstants as FLC
from backend.serializers import AuditSerializer
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import AdapterTypes
    from unstract.sdk1.constants import Common as common
else:
    from unstract.sdk.adapters.constants import Common as common
    from unstract.sdk.adapters.enums import AdapterTypes

from .models import AdapterInstance, UserDefaultAdapter


class TestAdapterSerializer(serializers.Serializer):
    adapter_id = serializers.CharField(max_length=FLC.ADAPTER_ID_LENGTH)
    adapter_metadata = serializers.JSONField()
    adapter_type = serializers.JSONField()


class BaseAdapterSerializer(AuditSerializer):
    class Meta:
        model = AdapterInstance
        fields = "__all__"


class DefaultAdapterSerializer(serializers.Serializer):
    llm_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)
    embedding_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)
    vector_db_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)


class AdapterInstanceSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for CRUD other than listing
    """

    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get(AdapterKeys.ADAPTER_METADATA, None):
            encryption_secret: str = settings.ENCRYPTION_KEY
            f: Fernet = Fernet(encryption_secret.encode("utf-8"))
            json_string: str = json.dumps(data.pop(AdapterKeys.ADAPTER_METADATA))

            data[AdapterKeys.ADAPTER_METADATA_B] = f.encrypt(json_string.encode("utf-8"))

        return data

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)

        rep.pop(AdapterKeys.ADAPTER_METADATA_B)
        adapter_metadata = instance.metadata

        # Hide unstract_key when use_platform_provided_unstract_key is True
        if (
            adapter_metadata.get("use_platform_provided_unstract_key") is True
            and "unstract_key" in adapter_metadata
        ):
            # Create a copy to avoid mutating the original metadata
            adapter_metadata = adapter_metadata.copy()
            # Set the unstract_key to an empty string instead of removing it
            adapter_metadata["unstract_key"] = ""

        rep[AdapterKeys.ADAPTER_METADATA] = adapter_metadata
        # Retrieve context window if adapter is a LLM
        # For other adapter types, context_window is not relevant.

        if instance.adapter_type == AdapterTypes.LLM.value:
            adapter_metadata[AdapterKeys.ADAPTER_CONTEXT_WINDOW_SIZE] = (
                instance.get_context_window_size()
            )

        rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
            instance.adapter_id, common.ICON
        )
        rep[AdapterKeys.ADAPTER_CREATED_BY] = instance.created_by.email

        return rep


class AdapterInfoSerializer(BaseAdapterSerializer):
    context_window_size = serializers.SerializerMethodField()

    class Meta(BaseAdapterSerializer.Meta):
        model = AdapterInstance
        fields = (
            "id",
            "adapter_id",
            "adapter_name",
            "adapter_type",
            "created_by",
            "context_window_size",
        )  # type: ignore

    def get_context_window_size(self, obj: AdapterInstance) -> int:
        return obj.get_context_window_size()


class AdapterListSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for listing adapters
    """

    class Meta(BaseAdapterSerializer.Meta):
        model = AdapterInstance
        fields = (
            "id",
            "adapter_id",
            "adapter_name",
            "adapter_type",
            "created_by",
            "description",
        )  # type: ignore

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)
        rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
            instance.adapter_id, common.ICON
        )
        model = instance.metadata.get("model")
        if model:
            rep["model"] = model

        if instance.is_friction_less:
            rep["created_by_email"] = "Unstract"
        else:
            rep["created_by_email"] = instance.created_by.email

        return rep


class SharedUserListSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for listing adapter users
    """

    shared_users = UserSerializer(many=True)
    created_by = UserSerializer()

    class Meta(BaseAdapterSerializer.Meta):
        model = AdapterInstance
        fields = (
            "id",
            "adapter_id",
            "adapter_name",
            "adapter_type",
            "created_by",
            "shared_users",
        )  # type: ignore


class UserDefaultAdapterSerializer(ModelSerializer):
    class Meta:
        model = UserDefaultAdapter
        fields = "__all__"
