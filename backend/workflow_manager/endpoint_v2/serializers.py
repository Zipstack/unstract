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
        queryset=ConnectorInstance.objects.all(),
        source="connector_instance",
        write_only=True,
        allow_null=True,
    )

    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"
