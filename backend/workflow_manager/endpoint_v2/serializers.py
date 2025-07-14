import logging

from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_v2.models import ConnectorInstance
from connector_v2.serializers import ConnectorInstanceSerializer
from rest_framework import serializers
from rest_framework.serializers import CharField, ModelSerializer, SerializerMethodField
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

logger = logging.getLogger(__name__)


class WorkflowEndpointSerializer(ModelSerializer):
    # Added connector information fields for backward compatibility
    connector_name = SerializerMethodField()
    connector_id = SerializerMethodField()
    connector_type = SerializerMethodField()
    connector_icon = SerializerMethodField()
    connector_metadata = SerializerMethodField()
    workflow_name = CharField(source="workflow.workflow_name", read_only=True)

    # Nested serializer for reading ConnectorInstance data
    connector_instance = ConnectorInstanceSerializer(read_only=True)

    # Field for creating ConnectorInstance
    connector_instance_data = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"

    def create(self, validated_data):
        """Create WorkflowEndpoint and optionally create ConnectorInstance."""
        connector_instance_data = validated_data.pop("connector_instance_data", None)

        # Create the WorkflowEndpoint
        workflow_endpoint = super().create(validated_data)

        # Create ConnectorInstance if data provided
        if connector_instance_data:
            connector_instance = ConnectorInstance.objects.create(
                connector_id=connector_instance_data.get("connector_id"),
                connector_name=connector_instance_data.get("connector_name"),
                metadata=connector_instance_data.get("connector_metadata", {}),
                created_by_id=connector_instance_data.get("created_by"),
            )
            # Link the connector instance to the workflow endpoint
            workflow_endpoint.connector_instance = connector_instance
            workflow_endpoint.save()

        return workflow_endpoint

    def update(self, instance, validated_data):
        """Update WorkflowEndpoint and create/update ConnectorInstance."""
        connector_instance_data = validated_data.pop("connector_instance_data", None)

        # Update the WorkflowEndpoint
        workflow_endpoint = super().update(instance, validated_data)

        # Create or update ConnectorInstance if data provided
        if connector_instance_data:
            if workflow_endpoint.connector_instance:
                # Update existing ConnectorInstance
                connector_instance = workflow_endpoint.connector_instance
                connector_instance.connector_id = connector_instance_data.get(
                    "connector_id", connector_instance.connector_id
                )
                connector_instance.connector_name = connector_instance_data.get(
                    "connector_name", connector_instance.connector_name
                )
                connector_instance.metadata = connector_instance_data.get(
                    "connector_metadata", connector_instance.metadata
                )
                connector_instance.save()
            else:
                # Create new ConnectorInstance
                connector_instance = ConnectorInstance.objects.create(
                    connector_id=connector_instance_data.get("connector_id"),
                    connector_name=connector_instance_data.get("connector_name"),
                    metadata=connector_instance_data.get("connector_metadata", {}),
                    created_by_id=connector_instance_data.get("created_by"),
                )
                # Link the connector instance to the workflow endpoint
                workflow_endpoint.connector_instance = connector_instance
                workflow_endpoint.save()

        return workflow_endpoint

    def get_connector_name(self, obj):
        """Get connector name from related ConnectorInstance."""
        if obj.connector_instance:
            return obj.connector_instance.connector_name
        # Fallback for legacy data or when connector_instance is not set
        return "Connector not configured"

    def get_connector_id(self, obj):
        """Get connector ID from related ConnectorInstance."""
        if obj.connector_instance:
            return obj.connector_instance.connector_id
        return None

    def get_connector_type(self, obj):
        """Map endpoint_type to connector_type for backward compatibility."""
        if obj.endpoint_type == WorkflowEndpoint.EndpointType.SOURCE:
            return "INPUT"
        elif obj.endpoint_type == WorkflowEndpoint.EndpointType.DESTINATION:
            return "OUTPUT"
        return None

    def get_connector_icon(self, obj):
        """Get connector icon from ConnectorProcessor."""
        if obj.connector_instance and obj.connector_instance.connector_id:
            icon_path = ConnectorProcessor.get_connector_data_with_key(
                obj.connector_instance.connector_id, ConnectorKeys.ICON
            )
            # Ensure icon path is properly formatted for frontend
            if icon_path and not icon_path.startswith("/"):
                return f"/{icon_path}"
            return icon_path
        # Return a default icon if no connector is configured
        return "/icons/connector-icons/default.png"

    def get_connector_metadata(self, obj):
        """Get connector metadata from related ConnectorInstance."""
        if obj.connector_instance:
            return obj.connector_instance.metadata
        return {}
