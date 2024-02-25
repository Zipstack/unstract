import json
from typing import Any

from account.models import EncryptionSecret
from adapter_processor.adapter_processor import AdapterProcessor
from adapter_processor.constants import AdapterKeys
from cryptography.fernet import Fernet
from rest_framework import serializers
from unstract.adapters.constants import Common as common
from utils.serializer_utils import SerializerUtils

from backend.constants import FieldLengthConstants as FLC
from backend.serializers import AuditSerializer

from .models import AdapterInstance


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

    Used for GET/POST request for adapter
    """

    class Meta(BaseAdapterSerializer.Meta):
        pass

    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        encryption_secret: EncryptionSecret = EncryptionSecret.objects.get()
        f: Fernet = Fernet(encryption_secret.key.encode("utf-8"))
        json_string: str = json.dumps(data.pop(AdapterKeys.ADAPTER_METADATA))

        data[AdapterKeys.ADAPTER_METADATA_B] = f.encrypt(
            json_string.encode("utf-8")
        )

        return data

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)

        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
                instance.adapter_id, common.ICON
            )
            rep.pop(AdapterKeys.ADAPTER_METADATA_B)
        return rep


class AdapterDetailSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for GET/UPDATE/DELETE request for adapter/<uuid:pk>
    """

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)

        encryption_secret: EncryptionSecret = EncryptionSecret.objects.get()
        f: Fernet = Fernet(encryption_secret.key.encode("utf-8"))

        rep.pop(AdapterKeys.ADAPTER_METADATA_B)
        adapter_metadata = json.loads(
            f.decrypt(bytes(instance.adapter_metadata_b).decode("utf-8"))
        )
        rep[AdapterKeys.ADAPTER_METADATA] = adapter_metadata

        return rep
