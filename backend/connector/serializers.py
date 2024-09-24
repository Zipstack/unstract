import json
import logging
from collections import OrderedDict
from typing import Any, Optional

from connector.constants import ConnectorInstanceKey as CIKey
from connector_auth.models import ConnectorAuth
from connector_auth.pipeline.common import ConnectorAuthHelper
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_processor.exceptions import OAuthTimeOut
from cryptography.fernet import Fernet
from django.conf import settings
from utils.serializer_utils import SerializerUtils

from backend.serializers import AuditSerializer
from unstract.connectors.filesystems.ucs import UnstractCloudStorage

from .models import ConnectorInstance

logger = logging.getLogger(__name__)


class ConnectorInstanceSerializer(AuditSerializer):
    class Meta:
        model = ConnectorInstance
        fields = "__all__"

    def save(self, **kwargs):  # type: ignore
        user = self.context.get("request").user or None
        connector_id: str = kwargs[CIKey.CONNECTOR_ID]
        connector_oauth: Optional[ConnectorAuth] = None
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
                logger.error(f"Error while obtaining ConnectorAuth: {exc}")
                raise OAuthTimeOut

        connector_mode = ConnectorProcessor.get_connector_data_with_key(
            connector_id, CIKey.CONNECTOR_MODE
        )
        kwargs[CIKey.CONNECTOR_MODE] = connector_mode.value

        encryption_secret: str = settings.ENCRYPTION_KEY
        f: Fernet = Fernet(encryption_secret.encode("utf-8"))
        json_string: str = json.dumps(kwargs.pop(CIKey.CONNECTOR_METADATA))
        if self.validated_data:
            self.validated_data.pop(CIKey.CONNECTOR_METADATA)

        kwargs[CIKey.CONNECTOR_METADATA_B] = f.encrypt(json_string.encode("utf-8"))

        instance = super().save(**kwargs)
        return instance

    def to_representation(self, instance: ConnectorInstance) -> dict[str, str]:
        # to remove the sensitive fields being returned
        rep: OrderedDict[str, Any] = super().to_representation(instance)
        if instance.connector_id == UnstractCloudStorage.get_id():
            rep[CIKey.CONNECTOR_METADATA] = {}
        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            rep.pop(CIKey.CONNECTOR_AUTH)
            # set icon fields for UI
            rep[ConnectorKeys.ICON] = ConnectorProcessor.get_connector_data_with_key(
                instance.connector_id, ConnectorKeys.ICON
            )

        rep.pop(CIKey.CONNECTOR_METADATA_B)
        if instance.connector_metadata_b:
            rep[CIKey.CONNECTOR_METADATA] = instance.metadata
        return rep
