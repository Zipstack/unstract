from backend.constants import FieldLengthConstants as FLC
from rest_framework import serializers


class TestConnectorSerializer(serializers.Serializer):
    connector_id = serializers.CharField(max_length=FLC.CONNECTOR_ID_LENGTH)
    connector_metadata = serializers.JSONField()
