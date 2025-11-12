import logging

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
from connector_processor.exceptions import InvalidConnectorID
from connector_processor.serializers import (
    ConnectorSchemaQuerySerializer,
    SupportedConnectorsQuerySerializer,
    TestConnectorSerializer,
)

logger = logging.getLogger(__name__)


class ConnectorViewSet(GenericViewSet):  # type: ignore[misc]
    versioning_class = URLPathVersioning
    serializer_class = TestConnectorSerializer

    def _extract_metadata_from_form_data(self, request: Request) -> dict[str, str]:
        """Extract metadata from FormData, handling both regular fields and file uploads."""
        import json

        connector_metadata = {}
        excluded_fields = {
            "connector_id",
            "connector_name",
            "created_by",
            "modified_by",
        }

        # Extract non-file form fields as metadata
        for key, value in request.data.items():
            if key not in excluded_fields:
                try:
                    # Try to parse as JSON for complex values
                    connector_metadata[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # Store as string for simple values
                    connector_metadata[key] = value

        # Handle file uploads
        for field_name, uploaded_file in request.FILES.items():
            connector_metadata[field_name] = uploaded_file

        return connector_metadata

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
        # Handle FormData requests (with file uploads) similar to connector creation
        if request.content_type and "multipart/form-data" in request.content_type:
            connector_id = request.data.get(CIKey.CONNECTOR_ID)
            if not connector_id:
                return Response(
                    {"error": "connector_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Extract metadata from FormData (similar to connector_v2/views.py)
            cred_string = self._extract_metadata_from_form_data(request)
        else:
            # Handle JSON requests (original behavior)
            serializer: TestConnectorSerializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            connector_id = serializer.validated_data.get(CIKey.CONNECTOR_ID)
            cred_string = serializer.validated_data.get(CIKey.CONNECTOR_METADATA)

        # Debug logging
        logger.info(
            f"Test connector request - ID: {connector_id}, credentials type: {type(cred_string)}"
        )
        logger.info(f"Connector ID repr: {repr(connector_id)}")

        try:
            test_result = ConnectorProcessor.test_connectors(
                connector_id=connector_id, credentials=cred_string
            )
        except (IndexError, InvalidConnectorID) as e:
            logger.error(f"Failed to find connector with ID '{connector_id}': {e}")
            return Response(
                {"error": f"Invalid connector ID: {connector_id}"},
                status=status.HTTP_400_BAD_REQUEST,
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
