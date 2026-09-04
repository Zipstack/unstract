import json
from typing import Any

from account_v2.serializer import UserSerializer
from cryptography.fernet import Fernet
from django.conf import settings
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, ValidationError
from tenant_account_v2.sharing_helpers import (
    serialize_group_refs,
    serialize_owner_refs,
)
from utils.input_sanitizer import validate_name_field, validate_no_html_tags

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.constants import AdapterKeys
from adapter_processor_v2.deprecated_adapters import (
    get_deprecation_message,
    get_deprecation_metadata,
    is_adapter_deprecated,
)
from backend.constants import FieldLengthConstants as FLC
from backend.serializers import AuditSerializer
from unstract.sdk1.constants import AdapterTypes
from unstract.sdk1.constants import Common as common

from .models import AdapterInstance, UserDefaultAdapter


class TestAdapterSerializer(serializers.Serializer):
    adapter_id = serializers.CharField(max_length=FLC.ADAPTER_ID_LENGTH)
    adapter_metadata = serializers.JSONField()
    adapter_type = serializers.JSONField()


def _add_deprecation_info(rep: dict[str, Any], instance: AdapterInstance) -> bool:
    """Stamp availability keys onto ``rep``; returns whether the adapter is usable.

    The registry is consulted alongside the stored flag so a newly deprecated
    adapter reads as deprecated before its backfill migration has run.
    """
    is_available = instance.is_available and not is_adapter_deprecated(
        instance.adapter_id
    )
    rep[AdapterKeys.IS_AVAILABLE] = is_available
    rep[AdapterKeys.IS_DEPRECATED] = not is_available
    if not is_available:
        metadata = (
            get_deprecation_metadata(instance.adapter_id) or instance.deprecation_metadata
        )
        if metadata:
            rep[AdapterKeys.DEPRECATION_METADATA] = metadata
    return is_available


class BaseAdapterSerializer(AuditSerializer):
    # ``shared_groups`` is no longer an M2M on AdapterInstance — declare it
    # explicitly so ``fields = "__all__"`` continues to expose it. Share
    # mutations go through ``POST /adapter/{id}/share/`` (UN-2977 plan §B).
    shared_groups = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = AdapterInstance
        fields = "__all__"
        # View owns uniqueness (IntegrityError->DuplicateData); drop the DRF
        # auto-validator that 400s on re-save before the view can handle it.
        validators = []
        extra_kwargs = {
            "shared_to_org": {"read_only": True},
        }

    def validate(self, data):
        data = super().validate(data)
        adapter_name = data.get("adapter_name")
        if adapter_name is not None:
            data["adapter_name"] = validate_name_field(
                adapter_name, field_name="Adapter name"
            )
        description = data.get("description")
        if description is not None:
            data["description"] = validate_no_html_tags(
                description, field_name="Description"
            )
        return data


class DefaultAdapterSerializer(serializers.Serializer):
    llm_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)
    embedding_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)
    vector_db_default = serializers.CharField(max_length=FLC.UUID_LENGTH, required=False)


class AdapterInstanceSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for CRUD other than listing
    """

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a deprecated adapter_id.

        Sits on the serializer rather than the create view because
        ``adapter_id`` is writable, so update/partial_update reach it too.
        """
        adapter_id = attrs.get(AdapterKeys.ADAPTER_ID)
        if is_adapter_deprecated(adapter_id):
            raise ValidationError(
                {AdapterKeys.ADAPTER_ID: get_deprecation_message(adapter_id)}
            )
        return attrs

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

        is_available = _add_deprecation_info(rep, instance)

        # Only retrieve context window and icon for available adapters
        # Avoid SDK calls for deprecated adapters
        if is_available:
            # Retrieve context window if adapter is a LLM
            # For other adapter types, context_window is not relevant.
            if instance.adapter_type == AdapterTypes.LLM.value:
                adapter_metadata[AdapterKeys.ADAPTER_CONTEXT_WINDOW_SIZE] = (
                    instance.get_context_window_size()
                )

            try:
                rep[common.ICON] = AdapterProcessor.get_adapter_data_with_key(
                    instance.adapter_id, common.ICON
                )
            except Exception as e:
                # Log error but don't fail serialization
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Failed to retrieve icon for adapter {instance.adapter_id}: {e}"
                )
                rep[common.ICON] = None
        else:
            # For deprecated adapters, use generic warning icon
            rep[common.ICON] = "🚫"
            adapter_metadata[AdapterKeys.ADAPTER_CONTEXT_WINDOW_SIZE] = 0

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
            "created_at",
            "modified_at",
            "description",
        )  # type: ignore

    def to_representation(self, instance: AdapterInstance) -> dict[str, str]:
        rep: dict[str, str] = super().to_representation(instance)

        _add_deprecation_info(rep, instance)

        rep[common.ICON] = AdapterProcessor.get_icon(instance)

        model = instance.metadata.get("model")
        if model:
            rep["model"] = model

        # Frictionless (Unstract-provisioned) adapters mask the owner org-wide;
        # mask owner_emails too, else the Owned By column leaks the real owner.
        if instance.is_friction_less:
            rep["created_by_email"] = "Unstract"
            rep["owner_emails"] = ["Unstract"]
        else:
            rep["created_by_email"] = instance.created_by.email
            rep["owner_emails"] = instance.owner_emails()

        request = self.context.get("request")
        rep["is_owner"] = instance.is_owner(request.user) if request else False
        rep["co_owners_count"] = instance.co_owners_count()

        return rep


class SharedUserListSerializer(BaseAdapterSerializer):
    """Inherits BaseAdapterSerializer.

    Used for listing adapter users
    """

    shared_users = serializers.SerializerMethodField()
    shared_groups = serializers.SerializerMethodField()
    co_owners = serializers.SerializerMethodField()
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
            "shared_to_org",
            "shared_groups",
            "co_owners",
        )  # type: ignore

    def get_shared_users(self, obj):
        viewers = [u for u in obj.viewers() if not u.is_service_account]
        return UserSerializer(viewers, many=True).data

    def get_shared_groups(self, obj):
        return serialize_group_refs(obj)

    def get_co_owners(self, obj):
        return serialize_owner_refs(obj)


class UserDefaultAdapterSerializer(ModelSerializer):
    class Meta:
        model = UserDefaultAdapter
        fields = "__all__"
