import logging
from collections import OrderedDict
from typing import Any

from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from rest_framework.serializers import SerializerMethodField
from utils.fields import EncryptedBinaryFieldSerializer
from utils.serializer_utils import SerializerUtils

from backend.serializers import AuditSerializer
from connector_v2.constants import ConnectorInstanceKey as CIKey
from unstract.connectors.filesystems.ucs import UnstractCloudStorage

from .models import ConnectorInstance

logger = logging.getLogger(__name__)


class ConnectorInstanceSerializer(AuditSerializer):
    connector_metadata = EncryptedBinaryFieldSerializer(required=False, allow_null=True)
    icon = SerializerMethodField()

    class Meta:
        model = ConnectorInstance
        fields = "__all__"

    def get_icon(self, obj: ConnectorInstance) -> str:
        """Get connector icon from ConnectorProcessor."""
        icon_path = ConnectorProcessor.get_connector_data_with_key(
            obj.connector_id, ConnectorKeys.ICON
        )
        # Ensure icon path is properly formatted for frontend
        if icon_path and not icon_path.startswith("/"):
            return f"/{icon_path}"
        return icon_path

    def to_representation(self, instance: ConnectorInstance) -> dict[str, str]:
        # to remove the sensitive fields being returned
        rep: OrderedDict[str, Any] = super().to_representation(instance)
        if instance.connector_id == UnstractCloudStorage.get_id():
            rep[CIKey.CONNECTOR_METADATA] = {}
        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            rep.pop(CIKey.CONNECTOR_AUTH)
            rep[ConnectorKeys.ICON] = self.get_icon(instance)

        return rep
