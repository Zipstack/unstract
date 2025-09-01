from rest_framework import serializers

from backend.constants import FieldLengthConstants as FLC
from connector_processor.constants import ConnectorKeys


class TestConnectorSerializer(serializers.Serializer):
    connector_id = serializers.CharField(max_length=FLC.CONNECTOR_ID_LENGTH)
    connector_metadata = serializers.JSONField()


class ConnectorSchemaQuerySerializer(serializers.Serializer):
    """Serializer for validating connector schema query parameters."""

    id = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={"required": "ID is mandatory.", "blank": "ID cannot be empty."},
    )


class SupportedConnectorsQuerySerializer(serializers.Serializer):
    """Serializer for validating supported connectors query parameters."""

    type = serializers.ChoiceField(
        choices=[ConnectorKeys.INPUT, ConnectorKeys.OUTPUT],
        required=False,
        help_text="Optional filter by connector type. If not provided, returns all connectors.",
    )
    connector_mode = serializers.CharField(
        required=False, allow_blank=True, help_text="Optional connector mode filter"
    )
