from connector_v2.constants import ConnectorInstanceKey as CIKey
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet

from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_processor.serializers import (
    ConnectorSchemaQuerySerializer,
    SupportedConnectorsQuerySerializer,
    TestConnectorSerializer,
)


class ConnectorViewSet(GenericViewSet):
    versioning_class = URLPathVersioning
    serializer_class = TestConnectorSerializer

    def get_serializer_class(self) -> Serializer:
        if self.action == "test":
            return TestConnectorSerializer
        elif self.action == "connector_schema":
            return ConnectorSchemaQuerySerializer
        elif self.action == "supported_connectors":
            return SupportedConnectorsQuerySerializer
        return super().get_serializer_class()

    def test(self, request: Request) -> Response:
        """Tests the connector against the credentials passed."""
        serializer: TestConnectorSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connector_id = serializer.validated_data.get(CIKey.CONNECTOR_ID)
        cred_string = serializer.validated_data.get(CIKey.CONNECTOR_METADATA)
        test_result = ConnectorProcessor.test_connectors(
            connector_id=connector_id, credentials=cred_string
        )
        return Response(
            {ConnectorKeys.IS_VALID: test_result},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def connector_schema(self, request: Request) -> Response:
        """Returns the JSON schema for a specific connector.

        Replaces the get_connector_schema function-based view.
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        connector_id = serializer.validated_data.get("id")
        json_schema = ConnectorProcessor.get_json_schema(connector_id=connector_id)

        return Response(data=json_schema, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def supported_connectors(self, request: Request) -> Response:
        """Retrieves a list of supported connectors based on the provided
        connector type and mode.

        Replaces the get_supported_connectors function-based view.
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        connector_type = serializer.validated_data.get("type")
        connector_mode = serializer.validated_data.get("connector_mode")

        # Convert connector_mode to the appropriate enum if provided
        if connector_mode:
            connector_mode = ConnectorProcessor.validate_connector_mode(connector_mode)

        json_schema = ConnectorProcessor.get_all_supported_connectors(
            type=connector_type, connector_mode=connector_mode
        )

        return Response(json_schema, status=status.HTTP_200_OK)
