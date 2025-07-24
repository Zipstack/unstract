import logging

from connector_v2.models import ConnectorInstance
from connector_v2.serializers import ConnectorInstanceSerializer
from rest_framework import serializers
from rest_framework.serializers import (
    ModelSerializer,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

logger = logging.getLogger(__name__)


class WorkflowEndpointSerializer(ModelSerializer):
    connector_instance = ConnectorInstanceSerializer(read_only=True)
    connector_instance_id = serializers.PrimaryKeyRelatedField(
        queryset=ConnectorInstance.objects.all(),  # To not make DRF shout
        source="connector_instance",
        write_only=True,
        allow_null=True,
    )

    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"

    def get_fields(self):
        """Override get_fields to dynamically set the connector_instance_id queryset.

        This is needed to ensure that the queryset is set after the organization
        context is available.
        """
        fields = super().get_fields()
        fields["connector_instance_id"].queryset = ConnectorInstance.objects.all()
        return fields
