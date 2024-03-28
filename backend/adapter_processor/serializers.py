import json
from typing import Any

from account.models import User
from adapter_processor.adapter_processor import AdapterProcessor
from adapter_processor.constants import AdapterKeys
from cryptography.fernet import Fernet
from django.conf import settings
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from unstract.adapters.adapterkit import Adapterkit
from unstract.adapters.constants import Common as common

from backend.constants import FieldLengthConstants as FLC
from backend.serializers import AuditSerializer
from unstract.adapters.llm.llm_adapter import LLMAdapter

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
    llm_default = serializers.CharField(
        max_length=FLC.UUID_LENGTH, required=False
    )
    embedding_default = serializers.CharField(
        max_length=FLC.UUID_LENGTH, required=False
    )
    vector_db_default = serializers.CharField(
        max_length=FLC.UUID_LENGTH, required=False
    )


class AdapterInstanceSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for CRUD other than listing
    """

    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get(AdapterKeys.ADAPTER_METADATA, None):
            encryption_secret: str = settings.ENCRYPTION_KEY
            f: Fernet = Fernet(encryption_secret.encode("utf-8"))
            json_string: str = json.dumps(
                data.pop(AdapterKeys.ADAPTER_METADATA)
            )

            data[AdapterKeys.ADAPTER_METADATA_B] = f.encrypt(
                json_string.encode("utf-8")
            )

        return data

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)

        encryption_secret: str = settings.ENCRYPTION_KEY
        f: Fernet = Fernet(encryption_secret.encode("utf-8"))

        rep.pop(AdapterKeys.ADAPTER_METADATA_B)
        adapter_metadata = json.loads(
            f.decrypt(bytes(instance.adapter_metadata_b).decode("utf-8"))
        )
        # Get the adapter_instance
        adapter_class = Adapterkit().get_adapter_class_by_adapter_id(
            instance.adapter_id
        )
        adapter_instance = adapter_class(adapter_metadata)
        #If adapter_instance is a LLM send additional parameter of context_window
        if isinstance(adapter_instance, LLMAdapter):
            adapter_metadata["context_window_size"] = adapter_instance.get_context_window_size()

        rep[AdapterKeys.ADAPTER_METADATA] = adapter_metadata

        rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
            instance.adapter_id, common.ICON
        )
        rep["created_by_email"] = instance.created_by.email

        return rep


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
        )  # type: ignore

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)
        rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
            instance.adapter_id, common.ICON
        )
        rep["created_by_email"] = instance.created_by.email

        return rep


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class SharedUserListSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for listing adapters
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
