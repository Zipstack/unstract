import logging
from typing import Any

from connector_v2.models import ConnectorInstance
from connector_v2.serializers import ConnectorInstanceSerializer
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from workflow_manager.endpoint_v2.exceptions import (
    InvalidConfigurationError,  # TEMPORARY: Remove when save button is restored
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
    workflow_name = serializers.CharField(source="workflow.workflow_name", read_only=True)

    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"

    def get_fields(self) -> Any:
        """Override get_fields to dynamically set the connector_instance_id queryset.

        This is needed to ensure that the queryset is set after the organization
        context is available.
        """
        fields = super().get_fields()
        fields["connector_instance_id"].queryset = ConnectorInstance.objects.all()
        return fields

    # TEMPORARY: Remove when save button is restored
    # This validation prevents duplicate error messages by validating at serializer level
    # When proper form validation with save button returns, this can be removed
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Simple validation for reprocessInterval."""
        attrs = super().validate(attrs)

        configuration = attrs.get("configuration")
        if configuration and "reprocessInterval" in configuration:
            interval = configuration["reprocessInterval"]
            if not isinstance(interval, int) or interval <= 0:
                raise InvalidConfigurationError(
                    field="Duration", detail="must be a positive integer"
                )

        return attrs
