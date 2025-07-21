import logging
from collections import OrderedDict
from typing import Any

from connector_auth_v2.models import ConnectorAuth
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_processor.exceptions import OAuthTimeOut
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

    def save(self, **kwargs):  # type: ignore
        user = self.context.get("request").user or None
        connector_id: str = kwargs[CIKey.CONNECTOR_ID]
        connector_oauth: ConnectorAuth | None = None
        if (
            ConnectorInstance.supportsOAuth(connector_id=connector_id)
            and CIKey.CONNECTOR_METADATA in kwargs
        ):
            try:
                connector_oauth = ConnectorAuthHelper.get_or_create_connector_auth(
                    user=user,  # type: ignore
                    oauth_credentials=kwargs[CIKey.CONNECTOR_METADATA],
                )
                kwargs[CIKey.CONNECTOR_AUTH] = connector_oauth
                (
                    kwargs[CIKey.CONNECTOR_METADATA],
                    refresh_status,
                ) = connector_oauth.get_and_refresh_tokens()
            except Exception as exc:
                logger.error(
                    "Error while obtaining ConnectorAuth for connector id "
                    f"{connector_id}: {exc}"
                )
                raise OAuthTimeOut

        connector_mode = ConnectorProcessor.get_connector_data_with_key(
            connector_id, CIKey.CONNECTOR_MODE
        )
        kwargs[CIKey.CONNECTOR_MODE] = connector_mode.value

        instance = super().save(**kwargs)
        return instance

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
