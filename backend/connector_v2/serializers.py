import logging
from collections import OrderedDict
from typing import Any

from connector_auth_v2.constants import OAUTH_TOKEN_KEYS
from connector_auth_v2.models import ConnectorAuth
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_processor.exceptions import InvalidConnectorID, OAuthTimeOut
from rest_framework.serializers import CharField, SerializerMethodField, ValidationError
from utils.fields import EncryptedBinaryFieldSerializer
from utils.input_sanitizer import validate_name_field

from backend.serializers import AuditSerializer
from connector_v2.constants import ConnectorInstanceKey as CIKey
from unstract.connectors.filesystems.ucs import UnstractCloudStorage

from .models import ConnectorInstance

logger = logging.getLogger(__name__)


class ConnectorInstanceSerializer(AuditSerializer):
    connector_metadata = EncryptedBinaryFieldSerializer(required=False, allow_null=True)
    icon = SerializerMethodField()
    created_by_email = CharField(source="created_by.email", read_only=True)

    class Meta:
        model = ConnectorInstance
        fields = "__all__"
        extra_kwargs = {"connector_name": {"required": False}}

    def validate_connector_name(self, value: str) -> str:
        return validate_name_field(value, field_name="Connector name")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Backfill ``connector_name`` from the JSON schema default when absent.

        Defense-in-depth: the frontend RJSF form seeds ``connector_name`` from
        the schema default, but callers (including staging OAuth flows) have
        been observed to POST without it. If the connector schema declares a
        default name, use it. Otherwise raise a 400 explicitly rather than
        letting the missing value reach the DB and surface as an
        ``IntegrityError`` (the model enforces ``null=False``).

        Skipped entirely on partial updates (PATCH): the existing DB row
        already has a valid name, and backfilling would overwrite a
        user-renamed connector with the schema default.
        """
        attrs = super().validate(attrs)
        if attrs.get(CIKey.CONNECTOR_NAME) or self.partial:
            return attrs

        connector_id = attrs.get(CIKey.CONNECTOR_ID)
        default_name = (
            self._get_schema_default_connector_name(connector_id)
            if connector_id
            else None
        )
        if not default_name:
            raise ValidationError({CIKey.CONNECTOR_NAME: "This field is required."})
        attrs[CIKey.CONNECTOR_NAME] = default_name
        logger.info(
            "Filled missing connector_name with schema default for %s",
            connector_id,
        )
        return attrs

    @staticmethod
    def _get_schema_default_connector_name(connector_id: str) -> str | None:
        try:
            schema_details = ConnectorProcessor.get_json_schema(connector_id=connector_id)
        except InvalidConnectorID:
            return None
        return (
            schema_details.get(ConnectorKeys.JSON_SCHEMA, {})
            .get("properties", {})
            .get("connectorName", {})
            .get("default")
        )

    def save(self, **kwargs):  # type: ignore
        user = self.context.get("request").user or None
        connector_id: str = kwargs[CIKey.CONNECTOR_ID]
        connector_oauth: ConnectorAuth | None = None
        # Check if OAuth tokens are actually present in metadata
        connector_metadata = kwargs.get(CIKey.CONNECTOR_METADATA) or {}
        has_oauth_tokens = bool(
            connector_metadata.get("access_token")
            or connector_metadata.get("refresh_token")
        )
        if (
            ConnectorInstance.supportsOAuth(connector_id=connector_id)
            and CIKey.CONNECTOR_METADATA in kwargs
            and has_oauth_tokens
        ):
            try:
                connector_oauth = ConnectorAuthHelper.get_or_create_connector_auth(
                    user=user,  # type: ignore
                    oauth_credentials=kwargs[CIKey.CONNECTOR_METADATA],
                )
                kwargs[CIKey.CONNECTOR_AUTH] = connector_oauth
                # Merge refreshed token fields (whitelist) back into this
                # connector's metadata so ``super().save(**kwargs)`` does not
                # overwrite the fresh token the sibling-loop just persisted.
                # Whitelisting preserves per-connector form fields (site_url,
                # drive_id) that must not be leaked across connectors sharing
                # the same (provider, uid).
                refreshed_metadata, _ = connector_oauth.get_and_refresh_tokens()
                token_updates = {
                    key: refreshed_metadata[key]
                    for key in OAUTH_TOKEN_KEYS
                    if refreshed_metadata.get(key) is not None
                }
                kwargs[CIKey.CONNECTOR_METADATA] = {
                    **(kwargs.get(CIKey.CONNECTOR_METADATA) or {}),
                    **token_updates,
                }
            except Exception as exc:
                logger.error(
                    "Error while obtaining ConnectorAuth for connector id "
                    f"{connector_id}: {exc}"
                )
                raise OAuthTimeOut

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

        connector_mode = ConnectorProcessor.get_connector_data_with_key(
            instance.connector_id, CIKey.CONNECTOR_MODE
        )
        rep[CIKey.CONNECTOR_MODE] = connector_mode.value

        # Remove sensitive connector auth from the response
        rep.pop(CIKey.CONNECTOR_AUTH)

        return rep
